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
_TW_TRANSCLUSION = re.compile(r"\{\{[^{}]*\}\}")
_TW_MACRO = re.compile(r"<<[^<>]*>>")
_TW_LINK = re.compile(r"\[\[([^\]|]*?)(?:\|[^\]]*)?\]\]")  # [[label|target]] -> label
_CITE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")  # [3] or [3, 4]
_LATEX_CMD_ARG = re.compile(r"\\[a-zA-Z@]+\*?\s*\{([^{}]*)\}")
_LATEX_CMD_BARE = re.compile(r"\\[a-zA-Z@]+\*?|\\\\")
_BRACES = re.compile(r"[{}]")
_WS = re.compile(r"\s+")


def clean_text(raw: str) -> str:
    """Return sentence-ready prose derived from a raw paragraph string.

    ``\\cmd{...}`` is unwrapped to its inner text, inline math becomes a single
    ``⟨math⟩`` placeholder (so a formula doesn't split a sentence), numeric
    ``[n]`` citations are dropped, and whitespace is collapsed. Author-year
    textual citations are deliberately kept. Returns ``""`` for markup-only or
    empty input.
    """
    if not raw:
        return ""

    text = _INLINE_MATH.sub(" " + MATH_PLACEHOLDER + " ", raw)
    text = _TW_TRANSCLUSION.sub(" ", text)
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
