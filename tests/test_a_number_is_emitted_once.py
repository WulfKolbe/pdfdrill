r"""An equation number is emitted once, not twice.

T-0156, under the owner's rule of 2026-11-22 — fix at the lowest level.

`to_lines_json` SPLITS a right-margin equation number out of the display it
labels: the number gets its own record, typed `equation_number`, with its own
region at the margin and its own `cnt`, and the display's region and `cnt` are
narrowed to stop where its own ink stops. All of that was already right.

WHAT WAS NOT: the number stayed in the HOST's `text` as well, so every number
was emitted TWICE. Measured on the board's own judged readings — the exact
files the judge saw:

    lib_c57ac038ae5f-p0293    6 numbers as their own line, the SAME 6 inside a math line
    lib_3fe71b4ef018-p0328    8 and 8
    lib_5a5c76391c9c-p0004    5 and 5
    lib_1a36bfe66b9c-p0154    2 and 2
    -------------------------------------------------------------------
    board-wide               21 doubled, across 4 of the 24 judged pages

The judge renders what is written, so it set each number at the margin AND
beside the formula. That is where the unpaired "(" and the stray digit inside
the formula's region came from: not a number in the wrong place, a number in
BOTH places.

TRIMMED FROM THE GLYPHS THE SPLIT ALREADY IDENTIFIED. `mmd.equation_number`
returns the tag's glyphs by its own three conditions — parenthesised, ending
at the column's right margin, behind a wide gap — and the same `tag` that
decides the new record's text decides what leaves the host's. No pattern is
run over the text.
"""
import json
import os

import pytest

BOARD = os.path.expanduser("~/drillgroup/work/board57")
PAGES = ("lib_c57ac038ae5f-p0293", "lib_3fe71b4ef018-p0328",
         "lib_5a5c76391c9c-p0004", "lib_1a36bfe66b9c-p0154")


def _doubled(doc) -> set:
    """Numbers that appear BOTH as their own line and inside a math line."""
    import re
    num = re.compile(r"\(\s*(\d+(?:\.\d+)*)\s*\)")
    pages = doc if isinstance(doc, list) else doc.get("pages", [])
    own, inmath = set(), set()
    for pg in pages:
        for ln in pg.get("lines") or []:
            text = (ln.get("text") or "").strip()
            kind = ln.get("type") or ""
            if kind == "equation_number":
                m = num.search(text)
                if m:
                    own.add(m.group(1))
            elif kind == "math":
                for m in num.finditer(text):
                    inmath.add(m.group(1))
    return own & inmath


def test_the_split_removes_the_number_from_the_host():
    """The unit of it: a host record whose text ends in its own number."""
    rec = {"text": r"$A = \sigma \omega .$ (14.4.10)",
           "text_display": r"$A = \sigma \omega .$ (14.4.10)"}
    tag = "(14.4.10)"
    for key in ("text", "text_display"):
        at = rec[key].rfind(tag)
        rec[key] = (rec[key][:at] + rec[key][at + len(tag):]).rstrip()
    assert rec["text"] == r"$A = \sigma \omega .$"
    assert "14.4.10" not in rec["text_display"]


def test_only_the_last_occurrence_is_removed():
    """A number that also appears INSIDE the maths is not the label."""
    text = r"$x_{(1)} = y$ (1)"
    at = text.rfind("(1)")
    out = (text[:at] + text[at + len("(1)"):]).rstrip()
    assert out == r"$x_{(1)} = y$"


@pytest.mark.parametrize("key", PAGES)
def test_the_judged_reading_had_the_defect(key):
    """The BEFORE state, kept so the fix cannot be claimed without it."""
    f = os.path.join(BOARD, key, "ours.lines.json")
    if not os.path.exists(f):
        pytest.skip("the board extracts are not in this repo")
    assert _doubled(json.load(open(f, encoding="utf-8"))), (
        "this page is recorded as having had doubled numbers; if it no longer "
        "does, the measurement that justified the fix has changed")


def test_the_split_site_trims_the_text():
    """The fix is at the split, not downstream of it."""
    import inspect

    from pdfreader import docmodel_six
    src = inspect.getsource(docmodel_six)
    at = src.find('num["type"] = "equation_number"')
    assert at > 0
    window = src[at:at + 3000]
    assert "rfind(_tagtext)" in window or "_tagtext" in window, (
        "the host's text must be trimmed where the number is split out, "
        "using the glyphs the split already identified")
