"""
Portable Stanza NLP core for docops.

Pure, framework-agnostic pieces used by the StanzaNlpMutator:

  - TEXT_FIELDS:   which DocObject types carry annotatable prose, and the
                   ``props`` field that holds each type's text.
  - object_text:   project one DocObject to its sentence-ready source string
                   (per-type field + ListItem marker folding).
  - clean_text:    strip LaTeX / TiddlyWiki-like markup so Stanza sees prose.
  - StanzaAnnotator: a lazily-built Stanza pipeline producing per-sentence
                   annotation dicts. Missing library/model -> StanzaUnavailable.

Kept independent of docops.base / docmodel so the markup and annotation logic
stay unit-testable in isolation (no Stanza needed for the pure functions).
"""
from __future__ import annotations

import re
from typing import Any

# Object types carrying prose worth annotating, mapped to the `props` field
# that holds their text. Text lives in different fields per type: Paragraph and
# Abstract use `text`, Section uses its heading `caption`, ListItem and Footnote
# use `content`.
TEXT_FIELDS: dict[str, str] = {
    "Paragraph": "text",
    "Abstract": "text",
    "Section": "caption",
    "ListItem": "content",
    "Footnote": "content",
}

DEFAULT_PROCESSORS = "tokenize,mwt,pos,lemma,depparse,ner"
DEFAULT_LANG = "en"

MATH_PLACEHOLDER = "⟨math⟩"


# --------------------------------------------------------------------------
# Text projection
# --------------------------------------------------------------------------

def object_text(obj: Any) -> str:
    """Return the sentence-ready source string for a DocObject.

    Reads the per-type field from ``TEXT_FIELDS``. For ``ListItem`` the
    separate ``props.marker`` (e.g. ``A.``, ``2025.``) is folded onto the front
    so the annotated sentence reads as written. Returns ``""`` for types not in
    ``TEXT_FIELDS`` or when the field is empty.
    """
    field = TEXT_FIELDS.get(obj.type)
    if field is None:
        return ""
    props = obj.props or {}
    text = props.get(field) or ""
    if obj.type == "ListItem":
        marker = (props.get("marker") or "").strip()
        if marker:
            text = f"{marker} {text}".strip()
    return text


# --------------------------------------------------------------------------
# Markup cleaning (pure)
# --------------------------------------------------------------------------

_INLINE_MATH = re.compile(r"\\\((.*?)\\\)|\\\[(.*?)\\\]|\$(.+?)\$", re.DOTALL)
_TW_TRANSCLUSION = re.compile(r"\{\{([^{}]*)\}\}")
_TW_MACRO = re.compile(r"<<[^<>]*>>")
_TW_LINK = re.compile(r"\[\[([^\]|]*?)(?:\|[^\]]*)?\]\]")  # [[label|target]] -> label
_CITE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")  # [3] or [3, 4]
_LATEX_CMD_ARG = re.compile(r"\\[a-zA-Z@]+\*?\s*\{([^{}]*)\}")
_LATEX_CMD_BARE = re.compile(r"\\[a-zA-Z@]+\*?|\\\\")
_BRACES = re.compile(r"[{}]")
_WS = re.compile(r"\s+")

# Map a TiddlyWiki transclusion template to a natural-language surface form.
# Stanza tokenizes/parses the raw string, so an opaque `{{Bibkey_FO0139||FO}}`
# distorts sentence boundaries and POS/dependency parsing; a real noun phrase
# like "formula 139" behaves like ordinary text in context. Each template maps
# the extracted reference number to a STABLE phrase (same transclusion always
# rewrites to the same text). See the tiddlywiki projector for the title
# formats: FO<NNNN>, EQ<NNNN>_p<NNN>, PIC_<NNNN>, DIA_<NNNN>, <citekey>.
_TRANSCLUSION_PHRASE = {
    "FO":   (lambda n: f"formula {n}" if n else "a formula"),
    "FREF": (lambda n: f"referenced formula number {n}" if n else "a referenced formula"),
    "PIC":  (lambda n: f"picture {n}" if n else "a picture"),
    "DIA":  (lambda n: f"diagram {n}" if n else "a diagram"),
    "CIT":  (lambda n: "a citation"),
}

_PAGE_SUFFIX = re.compile(r"_p\d+$")
_DIGITS = re.compile(r"\d+")


def _num_from_title(title: str) -> str:
    """Extract the reference number from a transclusion title.

    ``Bibkey_FO0139`` -> ``"139"``, ``Bibkey_EQ0264_p003`` -> ``"264"``. Strips a
    trailing ``_p<page>`` first, then takes the last digit run with leading
    zeros dropped. Returns ``""`` when the title carries no number.
    """
    base = _PAGE_SUFFIX.sub("", title or "")
    groups = _DIGITS.findall(base)
    return str(int(groups[-1])) if groups else ""


def _rewrite_transclusion(match: "re.Match") -> str:
    """Rewrite one ``{{title||TEMPLATE}}`` into a natural-language phrase.

    Unknown / template-less transclusions (e.g. ``{{X}}``) are dropped to a
    space, so the tokenizer never sees stray braces or opaque IDs.
    """
    title, _, template = match.group(1).rpartition("||")
    if not template:
        return " "
    phrase = _TRANSCLUSION_PHRASE.get(template.strip())
    return f" {phrase(_num_from_title(title))} " if phrase else " "


def clean_text(raw: str) -> str:
    """Return sentence-ready prose derived from a raw paragraph string.

    ``\\cmd{...}`` is unwrapped to its inner text, inline math becomes a single
    ``⟨math⟩`` placeholder (so a formula doesn't split a sentence), TiddlyWiki
    transclusions are rewritten to natural-language phrases ("formula 139",
    "referenced formula number 264", "a citation") so Stanza parses them like
    ordinary noun phrases instead of opaque IDs, numeric ``[n]`` citations are
    dropped, and whitespace is collapsed. Author-year textual citations are
    deliberately kept. Returns ``""`` for markup-only or empty input.
    """
    if not raw:
        return ""

    text = _INLINE_MATH.sub(" " + MATH_PLACEHOLDER + " ", raw)
    text = _TW_TRANSCLUSION.sub(_rewrite_transclusion, text)
    text = _TW_MACRO.sub(" ", text)
    text = _TW_LINK.sub(lambda m: m.group(1), text)
    text = _CITE.sub("", text)

    prev = None
    while prev != text:
        prev = text
        text = _LATEX_CMD_ARG.sub(lambda m: m.group(1), text)

    text = _LATEX_CMD_BARE.sub(" ", text)
    text = _BRACES.sub(" ", text)
    text = _WS.sub(" ", text).strip()
    return text


# --------------------------------------------------------------------------
# Stanza wrapper
# --------------------------------------------------------------------------

class StanzaUnavailable(RuntimeError):
    """Raised when the Stanza library or language model is not available."""


class StanzaAnnotator:
    """Lazily-built Stanza pipeline producing per-sentence annotation dicts.

    The pipeline is constructed on first use with ``download_method=None`` so a
    missing model fails loudly instead of triggering a silent network download.
    Empty / whitespace-only input returns ``[]`` without loading the pipeline.
    """

    def __init__(self, lang: str = DEFAULT_LANG, processors: str = DEFAULT_PROCESSORS):
        self.lang = lang
        self.processors = processors
        self._pipeline = None

    @property
    def pipeline(self):
        if self._pipeline is None:
            try:
                import stanza
            except ImportError as exc:
                raise StanzaUnavailable(
                    "Stanza is not installed. Install the optional extra: "
                    "pip install 'pdfdrill[nlp]'"
                ) from exc
            try:
                self._pipeline = stanza.Pipeline(
                    lang=self.lang,
                    processors=self.processors,
                    download_method=None,
                    verbose=False,
                )
            except Exception as exc:
                raise StanzaUnavailable(
                    f"Could not load Stanza '{self.lang}' model ({exc}). Run: "
                    f"python -c \"import stanza; stanza.download('{self.lang}')\""
                ) from exc
        return self._pipeline

    def annotate(self, clean: str) -> list[dict]:
        """Return a list of sentence annotation dicts for ``clean`` text."""
        if not clean or not clean.strip():
            return []
        doc = self.pipeline(clean)
        return [_sentence_dict(i, s) for i, s in enumerate(doc.sentences)]


def _sentence_dict(index: int, sent) -> dict:
    tokens = [
        {
            "id": w.id,
            "text": w.text,
            "lemma": w.lemma,
            "upos": w.upos,
            "xpos": w.xpos,
            "feats": w.feats,
            "head": w.head,
            "deprel": w.deprel,
        }
        for w in sent.words
    ]
    entities = [
        {
            "text": e.text,
            "type": e.type,
            "start_char": e.start_char,
            "end_char": e.end_char,
        }
        for e in sent.ents
    ]
    return {"index": index, "text": sent.text, "tokens": tokens, "entities": entities}
