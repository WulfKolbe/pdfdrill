r"""One language view over a loaded Document — the German under the English.

OWNER, 2026-11-12: "I need the original German version."

WHAT WAS WRONG
--------------
`pdfdrill translate` writes the target language IN PLACE and keeps the original
under `<field>_source`, so every prose object of a translated model holds both
languages. MEASURED: not one command could emit the original. `md` takes
`--pages` and `--image-base`; `latex` takes `--force`, `--compile`,
`--dump-stages`, `--no-transclude`. The only consumer in the repo that could
reach the German was the JavaScript inside `docinspect`, which reads the twin
fields itself.

So the answer to "I need the original German version" was an HTML inspector and
nothing else: no Markdown, no LaTeX, no PDF, in the language the document was
actually printed in. The model had both languages the whole time; the projection
layer had no word for the question.

THE TWIN RULE IS ONE RULE
-------------------------
An identical twin is NOT a second language. Transclusion materialisation also
writes `text_source`, and counting that as a translation would put a language on
every materialised paragraph in the library — on BH2 it is the difference
between 818 real twins and 824 counted. `docinspect.element_translations`
already knew this. A projector that learned it separately would be a SECOND
OPINION about what a language is, and the two would drift the first time either
was fixed. The predicate lives here and both read it.

NOTHING ON DISK IS TOUCHED
--------------------------
`original_in_place` swaps the fields of an ALREADY-LOADED Document, in memory,
for one projection to read. `model_io.save_model` is the model's only writer,
and a projection that edited the model would be editing the producer's record —
the same rule that keeps `latex_raw` / `latex_original` / `latex_author`
verbatim. The swap KEEPS THE PAIR (`<field>_source` ends up holding the
translation), so it is its own inverse: a view, not a destructive edit.
"""
from __future__ import annotations

from typing import Any

#: Prose fields `translate` replaces in place, each with a `<field>_source`
#: twin. `content` is here because `docinspect._ALT_FIELDS` has always had it;
#: the two lists must not diverge, which is the point of this module.
PROSE_FIELDS: tuple[str, ...] = ("text", "caption", "content", "raw_text")

#: Suffix `translate` gives the field holding the untranslated string.
SOURCE_SUFFIX = "_source"


def is_second_language(current: Any, source: Any) -> bool:
    """True when `source` is a real other-language twin of `current`.

    Both must be non-empty strings and they must DIFFER. An identical pair is
    materialisation, not translation (see the module docstring).
    """
    if not isinstance(source, str) or not source.strip():
        return False
    if not isinstance(current, str) or current == source:
        return False
    return True


def twins(props: dict) -> dict[str, str]:
    """field -> the ORIGINAL-language string, for each prose field with a real
    twin. `{}` for a monolingual object."""
    out: dict[str, str] = {}
    if not isinstance(props, dict):
        return out
    for field in PROSE_FIELDS:
        src = props.get(field + SOURCE_SUFFIX)
        if is_second_language(props.get(field), src):
            out[field] = src
    return out


def original_in_place(doc) -> int:
    """Swap every twinned prose field of `doc` to its original language.

    Returns the number of FIELDS swapped (not objects) — a caller reports it,
    and a count of 0 is how a projection learns the document is monolingual
    before it writes a file claiming a language.

    In place, on a Document already in memory, and never saved. Its own
    inverse: calling it twice restores the starting state.
    """
    n = 0
    for obj in getattr(doc, "objects", {}).values():
        props = getattr(obj, "props", None)
        if not isinstance(props, dict):
            continue
        for field, original in twins(props).items():
            props[field + SOURCE_SUFFIX] = props[field]
            props[field] = original
            n += 1
    return n


def is_translated(doc) -> bool:
    """Whether any object carries a real second-language twin."""
    for obj in getattr(doc, "objects", {}).values():
        if twins(getattr(obj, "props", {}) or {}):
            return True
    return False


def codes(meta: dict) -> tuple[str | None, str | None]:
    """(original code, translated code) as `translate` recorded them.

    `translate --from DE --to EN-US` STATES both and writes them to the model
    meta, so this is a record rather than a detection.
    """
    if not isinstance(meta, dict):
        return (None, None)
    src = meta.get("source_lang")
    tgt = meta.get("translated_lang")
    return (src if isinstance(src, str) and src else None,
            tgt if isinstance(tgt, str) and tgt else None)


def file_tag(code: str | None, role: str) -> str:
    """The filename infix for a language-tagged projection: `de`, `en-us`.

    A language-tagged file NEVER overwrites the canonical `<bibkey>.md` /
    `<bibkey>.tex`: 41 bought MathPix downloads in the library were lost to a
    projection writing the one filename the download owns.
    """
    if code:
        return str(code).strip().lower().replace("_", "-")
    return "original" if role == "original" else "translated"
