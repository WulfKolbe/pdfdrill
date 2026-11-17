"""A rule across the page is a table's, not a fraction bar.

735 tells a listing border from a fraction bar by reach: one of the two groups
must span the bar end to end. A TABLE rule passes that test, because a table's
rows do span their rule, so it was classified `fraction`.

Calling one `fraction` does not merely build a wrong `\\frac`. `_off_row_by_rule`
treats every glyph whose centre lies in a fraction bar's x-range as being OFF
its row, so ONE full-width rule makes `_off_row_band` true for every row of the
page, and the script-band pass then moves each glyph to whatever row the content
stream emitted before it. Measured on the board's table page 1511.08771 p2709
(drillgroup 716b4d1):

    one rule x=[72,532], classified `fraction`
    _off_row_band true for 50 of 50 rows
    1,145 of the page's 2,526 glyphs moved
    52 rows collapsed into 26 lines of 17.5 pt, two printed table rows each
    the ink judge paired 73 of 2,526 glyphs -- 2.9% of the page

Over the board's 21 born-digital pages, the 56 rules the classifier called
`fraction`, by width:

    of the PAGE width   in ems          what they are
    0.064 .. 0.089      2.8 ..  3.9     real fraction bars      (8)
    0.344, 0.380        15.1,  23.2     wide display fractions  (2)
    0.550 .. 0.773      42.2 .. 47.1    table rules             (4)

Both conditions are required -- 0.45 of the page width AND 25 em -- because a
share of the page is blind to type size and an em count is blind to page size.
735's contract bar (160.2 pt in 12 pt type, 13.35 em) clears neither -- that
case keeps its own test, `TestAWideFractionBar` in test_docmodel_six.py, which
this change leaves green.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

docmodel = pytest.importorskip("pdfreader.docmodel_six")
texmap = pytest.importorskip("pdfreader.texmap")

PAGE_W = 595.0                      # A4 in points
TEXT_X0, TEXT_X1 = 72.0, 532.0      # the text column: 460 pt, 0.773 of the page
SIZE = 10.9                         # 460 pt is 42.2 em at this size


def _glyph(x0, baseline, size=SIZE):
    return docmodel.GlyphNode(
        id="g%d_%d" % (int(x0), int(baseline)), page=1,
        rect=(x0, baseline, x0 + 5.0, baseline + size * 0.7), text="x",
        cid=0, glyphname=None, fontname="CMR10", family="cm", size=size,
        tex=texmap.UNKNOWN)


def _rule(x0, x1, y):
    return docmodel.RuleNode(id="r", page=1, rect=(x0, y - 0.2, x1, y + 0.2))


def _two_rows():
    """Two table rows spanning the text column, with the rule between them."""
    out = []
    for x in range(int(TEXT_X0), int(TEXT_X1), 20):
        out += [_glyph(float(x), 700.0), _glyph(float(x), 680.0)]
    return out


def test_a_rule_across_the_page_is_a_table_rule():
    role = docmodel._rule_role(_rule(TEXT_X0, TEXT_X1, 690.0), _two_rows(),
                               SIZE, [], page_width=PAGE_W)
    assert role == "table", role


def test_without_a_page_width_the_old_verdict_stands():
    # Every existing caller that has no page keeps the behaviour it had.
    before = docmodel._rule_role(_rule(TEXT_X0, TEXT_X1, 690.0), _two_rows(),
                                 SIZE, [])
    assert before != "table", before


def test_a_wide_display_fraction_is_not_a_table_rule():
    # 0.38 of the page, 23.2 em: the widest bar the board measured as a real
    # fraction. Neither condition is met.
    x0, x1 = 150.0, 150.0 + 0.38 * PAGE_W
    g = _two_rows() + [_glyph(200.0, 694.0, size=7.6),
                       _glyph(200.0, 684.0, size=7.6)]
    role = docmodel._rule_role(_rule(x0, x1, 689.0), g, SIZE, [],
                               page_width=PAGE_W)
    assert role != "table", role


def test_both_conditions_are_required():
    g = _two_rows()
    # wide on the page but small in ems: a big rule in very large type
    assert docmodel._rule_role(_rule(TEXT_X0, TEXT_X1, 690.0), g, 30.0, [],
                               page_width=PAGE_W) != "table"
    # many ems but a small share of a very wide page
    assert docmodel._rule_role(_rule(TEXT_X0, TEXT_X1, 690.0), g, SIZE, [],
                               page_width=4000.0) != "table"
