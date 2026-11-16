"""
An interpolated box never runs backwards up the page.

THE DEFECT. `_interpolate_regions` boxes the objects text matching cannot
reach — a Formula whose source is `\\frac{...}`, a Picture with no text at all —
by handing each the unclaimed lines between its matched neighbours, and
`_union_region` takes the bounding box of them. `_until_paragraph_break` cuts
the run at a vertical gap wider than 1.8x the modal leading.

A COLUMN BREAK IS A NEGATIVE GAP, and `g > limit` is false for every negative
number. So the allotment walked straight through the column boundary and the
union boxed both columns at once. The same hole swallowed the page's margin
furniture: a rotated margin stamp is read after the body, so it sits far above
the line before it, and a box ran from the stamp at x=16.3 across to the right
column's edge.

Measured on the owner's arxiv.2209.02970 (2026-11-16), 21 pages, before and
after, with nothing else changed:

    boxed objects                 152 -> 184
    crossing the column gutter     86 -> 13
    wider than one column          85 -> 12
    reaching the margin stamp       1 -> 0

and on page 1, two boxes that were wrong by a whole column:

    'Remarkable advances in Art...'   x 70.9..530.5  ->  70.9..291.0
    'Our goal is to build a com...'   x 16.3..525.8  ->  306.1..525.8

THE RULE. Within one column's reading order the tops increase. A line whose
top jumps ABOVE its predecessor's is in a new column, or is furniture read
after the body — either way the run has ended. The tolerance is half a line
height, for the baseline jitter of a superscript; a column break is a jump of
hundreds of points, so nothing rides on the exact figure.

The 13 that still cross are genuinely full-width: a `\\begin{CJK*}` paragraph,
a centred `\\maketitle` block, wide captions.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.commands import _until_paragraph_break, _union_region

LEAD = 13.0          # the leading these synthetic lines are set at
H = 11.0


def _line(x, y, w, text="x"):
    return {"text": text,
            "region": {"top_left_x": x, "top_left_y": y,
                       "width": w, "height": H}}


def _column(x, y0, n, w=220.0):
    return [_line(x, y0 + i * LEAD, w) for i in range(n)]


def test_a_run_stops_at_the_column_break():
    left = _column(70.9, 200.0, 6)
    right = _column(306.0, 200.0, 6)          # starts again at the TOP
    kept = _until_paragraph_break(left + right)
    assert len(kept) == 6, \
        f"the run crossed the column break: kept {len(kept)} of 12"
    box = _union_region(kept)
    assert box["top_left_x"] == 70.9 and box["width"] <= 230.0, \
        f"the box spans both columns: {box}"


def test_the_box_is_one_column_wide():
    left = _column(70.9, 200.0, 6)
    right = _column(306.0, 200.0, 6)
    box = _union_region(_until_paragraph_break(left + right))
    assert box["top_left_x"] + box["width"] < 300.0, \
        f"the box reaches into the right column: {box}"


def test_margin_furniture_read_after_the_body_is_not_swept_in():
    """A rotated stamp is its own record, read after the upright lines, and its
    top is far above the last body line. That is the same backwards jump."""
    body = _column(70.9, 600.0, 5)
    stamp = [_line(16.3, 232.0, 20.0, "arXiv:2209.02970v3")]
    kept = _until_paragraph_break(body + stamp)
    assert all(l["region"]["top_left_x"] >= 70.0 for l in kept), \
        "the margin stamp was swept into a body object's box"
    box = _union_region(kept)
    assert box["top_left_x"] >= 70.0, f"the box reaches the stamp: {box}"


def test_a_single_column_run_is_not_cut():
    lines = _column(70.9, 200.0, 8)
    assert len(_until_paragraph_break(lines)) == 8, \
        "a clean single-column run was cut short"


def test_a_small_backwards_jump_does_not_end_a_run():
    """Half a line height of tolerance, because a raised glyph's top IS above
    its line's and that is not a column break. Kept to three lines so the
    vertical-gap rule cannot fire and confuse the two tests -- it did, on an
    earlier version of this one, and the code was right."""
    lines = [_line(70.9, 200.0, 220.0),
             _line(150.0, 197.0, 8.0, "2"),       # raised 3 pt, within 5.5
             _line(70.9, 213.0, 220.0)]
    assert len(_until_paragraph_break(lines)) == 3, \
        "a 3 pt backwards jump ended the run"


def test_the_paragraph_break_rule_still_holds():
    """The gap test is not replaced, only joined."""
    lines = _column(70.9, 200.0, 4)
    lines += _column(70.9, 200.0 + 4 * LEAD + 40.0, 4)      # a 40 pt gap
    assert len(_until_paragraph_break(lines)) == 4, \
        "the vertical-gap break stopped working"


def test_lines_without_geometry_are_returned_whole():
    lines = [{"text": "a"}, {"text": "b"}, {"text": "c"}, {"text": "d"}]
    assert _until_paragraph_break(lines) == lines, \
        "lines with no region were cut on a guess"
