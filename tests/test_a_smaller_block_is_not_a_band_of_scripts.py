r"""A block set smaller than the page body was dissolved into the line above.

733 places a band of pure scripts onto the row holding their bases, by the
content stream. It asks whether a row IS such a band through `_off_row_band`,
whose size clause is

    if g.size < 0.95 * span_pt:   continue      # a script: off-row by size

and `span_pt` is the dominant size of the WHOLE PAGE. So every row of any block
set smaller than the body qualifies in its entirety.

780 already caught this once, for code: a `\ttfamily\tiny` listing on a 10 pt
page was dissolved line by line, and the guard it added is a MONOSPACE test --
which fixes the case where the smaller block happens to be code and nothing
else.

MEASURED 2026-10-29 on 2016icpr page 1 (body 10.0 pt, abstract 9.0 pt), through
the reader itself. `_group_lines` returned the abstract as eight clean rows of
about 50 glyphs each; pass 733 then moved 51 of 51, 50 of 50, 47 of 47, 51 of
51, 54 of 54, 55 of 55, 54 of 54 and 27 of 27 glyphs onto the row above, and
`page.lines` held four rows of two lines interleaved glyph by glyph:

    (CCALbs)troafcta—bTihnearpyroimblaegmeoisflwaeblel-lidnegﬁntheedcaonnd…

A word-level projection prints that as

    Abstract—The problem of labeling the connected (CCL) components of a
    binary image is well-deﬁned and several proposals
    ... an exact solution to problem the exists and should be mandatory
    provided as output,

which is `pdftotext`'s two lines with their words shuffled together. The
library's own reading of this paper carries it, so the defect is not new; it is
the second half of what the owner's Claude.ai chat read as the columns being
mixed up (the first half was the gutter, `_column_edge`).

THE MEASURE THAT MATTERS IS THE DESTINATION'S OWN SIZE. A superscript is small
BESIDE ITS BASE; the page's dominant size says nothing about it. 767's fraction
clause stays, because there the page drew the evidence itself -- a
display-style `\frac{1}{2}` sets its parts at text size and is off-row anyway.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfreader import docmodel_six as D                        # noqa: E402

SPAN = 10.0            # the page body on 2016icpr page 1


def _g(size: float, *, x: float = 100.0, y: float = 600.0, text: str = "x"):
    return D.GlyphNode(id=f"g{x}_{y}_{size}", page=1,
                       rect=(x, y, x + 0.5 * size, y + size),
                       text=text, cid=120, glyphname=text,
                       fontname="F1", family="F", size=size,
                       tex=None, stream=0)


def _row(size: float, y: float, n: int = 50):
    return [_g(size, x=40.6 + i * 5.0, y=y) for i in range(n)]


# --------------------------------------------------------------------------- #
#  The rule, on its own
# --------------------------------------------------------------------------- #

def test_a_nine_point_line_does_not_join_a_nine_point_line():
    """THE CASE BUILT TO FAIL: 2016icpr's abstract. Both rows are 9.0 pt on a
    10.0 pt page, so the page-relative test calls every glyph a script."""
    dest = _row(9.0, 625.7)
    glyph = _g(9.0, x=40.6, y=615.7)
    assert D._script_beside_its_base(glyph, dest, [], SPAN) is False


def test_an_eight_point_script_joins_a_ten_point_row():
    """wzlxjtu-006: the superscripts of `e^{\\sigma}` and `\\phi^3`, 8 pt
    beside a row set at 9.96. They must still be placed."""
    dest = _row(9.96, 152.7, n=20)
    assert D._script_beside_its_base(_g(8.0, y=157.7), dest, [], SPAN) is True


def test_a_seven_point_script_joins_a_ten_point_row():
    """wzlxjtu-031's eighth display: a band at 6.97 pt over a 9.96 pt row."""
    dest = _row(9.96, 400.0, n=20)
    assert D._script_beside_its_base(_g(6.97, y=405.0), dest, [], SPAN) is True


def test_a_full_size_fraction_part_still_joins_by_the_rule():
    """767. A display-style `\\frac{1}{2}` sets its `1` and its `2` at text
    size; the bar the page drew is the evidence that they are off the row, and
    that clause outranks the size test in both directions."""
    dest = _row(9.96, 400.0, n=20)
    numerator = _g(9.96, x=200.0, y=406.0)
    bar = D.RuleNode(id="r1", page=1, rect=(198.0, 403.0, 210.0, 403.6))
    bar.role = "fraction"
    assert D._script_beside_its_base(numerator, dest, [bar], SPAN) is True


def test_a_body_sized_glyph_beside_a_body_sized_row_is_a_term_of_it():
    """The ordinary refusal: nothing to move."""
    dest = _row(10.0, 400.0, n=20)
    assert D._script_beside_its_base(_g(10.0, y=400.0), dest, [], SPAN) is False
