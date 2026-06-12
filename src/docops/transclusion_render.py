"""
Transclusion render policies — the stratum contract over canonical text.

The canonical paragraph representation carries TiddlyWiki transclusion
placeholders (``{{Heim1979_FO0012||FO}}``); it is THE pivotal artifact: the
wiki renders it for free, and modules parse it trivially. Modules never touch
the raw template ad hoc — each stratum consumes it through a NAMED render
policy (declared in the module's config):

  * ``detranscluded`` — placeholders become natural-language phrases
    ("formula 12", "a citation"). For transclusion-BLIND modules (stratum 2:
    Stanza NLP, claim wording analysis) whose tokenizers need real noun
    phrases, never opaque IDs. This is exactly what `nlp_stanza` has always
    produced — the implementation moved here, behavior unchanged.
  * ``typed_gloss`` — placeholders become typed brackets ("[FORMULA 12]",
    or with a semantic `lookup` "[FORMULA: mass eigenvalue relation]"). For
    transclusion-AWARE modules (stratum 3: LLM prompts that should see typed
    semantics instead of raw LaTeX or lossy plaintext).

``render(text, policy, lookup=None)`` — `lookup(title, template) -> gloss|None`
lets a module supply per-document semantics (e.g. the referenced Formula's
caption); on a miss the default numbered form is used.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

TW_TRANSCLUSION = re.compile(r"\{\{([^{}]*)\}\}")

_PAGE_SUFFIX = re.compile(r"_p\d+$")
_DIGITS = re.compile(r"\d+")

# detranscluded: template -> natural-language phrase (stable per transclusion).
TRANSCLUSION_PHRASE = {
    "FO":   (lambda n: f"formula {n}" if n else "a formula"),
    "FREF": (lambda n: f"referenced formula number {n}" if n else "a referenced formula"),
    "PIC":  (lambda n: f"picture {n}" if n else "a picture"),
    "DIA":  (lambda n: f"diagram {n}" if n else "a diagram"),
    "TAB":  (lambda n: f"table {n}" if n else "a table"),
    "FN":   (lambda n: f"footnote {n}" if n else "a footnote"),
    "CIT":  (lambda n: "a citation"),
}

# typed_gloss: template -> the typed bracket label.
TYPED_LABEL = {
    "FO": "FORMULA", "FREF": "FORMULA-REF", "PIC": "PICTURE", "DIA": "DIAGRAM",
    "TAB": "TABLE", "FN": "FOOTNOTE", "CIT": "CITATION",
}


def num_from_title(title: str) -> str:
    """``Bibkey_FO0139`` -> ``"139"``; ``Bibkey_EQ0264_p003`` -> ``"264"``."""
    base = _PAGE_SUFFIX.sub("", title or "")
    groups = _DIGITS.findall(base)
    return str(int(groups[-1])) if groups else ""


def _detranscluded_one(title: str, template: str) -> str:
    phrase = TRANSCLUSION_PHRASE.get(template)
    return f" {phrase(num_from_title(title))} " if phrase else " "


def _typed_one(title: str, template: str,
               lookup: Optional[Callable[[str, str], Optional[str]]]) -> str:
    label = TYPED_LABEL.get(template)
    if not label:
        return " "
    gloss = lookup(title, template) if lookup else None
    if gloss:
        return f" [{label}: {gloss}] "
    n = num_from_title(title)
    if label == "CITATION" or not n:
        return f" [{label}] "
    return f" [{label} {n}] "


def render(text: str, policy: str = "detranscluded",
           lookup: Optional[Callable[[str, str], Optional[str]]] = None) -> str:
    """Replace every ``{{title||TEMPLATE}}`` per the named policy. Unknown
    templates and bare ``{{X}}`` transclusions drop to a single space (no
    module ever sees stray braces or opaque IDs)."""
    if policy not in ("detranscluded", "typed_gloss"):
        raise ValueError(f"unknown render policy: {policy!r}")

    def _sub(m: "re.Match") -> str:
        title, _, template = m.group(1).rpartition("||")
        if not template:
            return " "
        template = template.strip()
        if policy == "detranscluded":
            return _detranscluded_one(title, template)
        return _typed_one(title, template, lookup)

    return TW_TRANSCLUSION.sub(_sub, text)


def rewrite_transclusion_match(match: "re.Match") -> str:
    """Back-compat shim for nlp_stanza's regex-callback style (detranscluded)."""
    title, _, template = match.group(1).rpartition("||")
    if not template:
        return " "
    return _detranscluded_one(title, template.strip())
