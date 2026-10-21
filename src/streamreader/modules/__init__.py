# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Refinement modules.

A module is a function

    process(page: dict, record: PageGlyphs, own: list[int]) -> list[Patch]

It receives one lines.json page, that page's glyph record (glyphs and
rules; a bare `Glyphs` is accepted too) and each glyph's owning line, and
returns patches. It never changes the page itself: `apply` does,
and refuses anything that is not a MathPix line key, so no module can widen
the format. A patch `(id, [line, ...])` puts whole lines in that line's
place, as a table does for the cells it replaces.
"""
from __future__ import annotations

from .. import mathpix
from . import fontsize, formulas, tables, unread

Patch = tuple[str, dict | list[dict] | None]

#: Run in this order; a later module sees the earlier ones' patches applied.
MODULES = [("fontsize", fontsize.process), ("formulas", formulas.process),
           ("unread", unread.process), ("tables", tables.process)]


def unpack(record):
    """(glyphs, rules) from a PageGlyphs record or a bare Glyphs."""
    return getattr(record, "glyphs", record), getattr(record, "rules", None)


def apply(page: dict, patches: list[Patch]) -> int:
    """Apply patches to the page. `(id, {key: value})` sets keys of a line;
    `(id, None)` removes the line, as when formula fragments become one
    line. Line numbers are not renumbered: MathPix's have gaps too."""
    by_id = {ln["id"]: ln for ln in page["lines"]}
    for line_id, values in patches:
        if line_id not in by_id:
            raise ValueError(f"patch names no line of page {page['page']}: "
                             f"{line_id}")
        if values is None:
            continue
        if isinstance(values, list):
            known = {ln["id"] for ln in page["lines"]} - {line_id}
            for new in values:
                unknown = set(new) - mathpix.LINE_KEYS
                if unknown:
                    raise ValueError(
                        f"not MathPix line keys: {sorted(unknown)}")
                if new["id"] in known:
                    raise ValueError(f"line id taken: {new['id']}")
                known.add(new["id"])
            continue
        unknown = set(values) - mathpix.LINE_KEYS
        if unknown:
            raise ValueError(f"not MathPix line keys: {sorted(unknown)}")
        if "id" in values:
            raise ValueError("a patch may not change a line's id")
    gone = {line_id for line_id, values in patches if values is None}
    for line_id, values in patches:
        if isinstance(values, dict) and line_id not in gone:
            by_id[line_id].update(values)
    put = {line_id: values for line_id, values in patches
           if isinstance(values, list) and line_id not in gone}
    if put:
        page["lines"] = [new for ln in page["lines"]
                         for new in put.get(ln["id"], [ln])]
    if gone:
        page["lines"] = [ln for ln in page["lines"] if ln["id"] not in gone]
        for ln in page["lines"]:
            if "children_ids" in ln:
                ln["children_ids"] = [c for c in ln["children_ids"]
                                      if c not in gone]
    return len(patches)
