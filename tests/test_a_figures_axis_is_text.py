r"""A figure's ink is a crop; its axis labels are text.

T-0154. `build` removes every glyph whose centre lies inside a detected
figure region — "a figure's internals are not prose, the rectangle is
projected as a crop instead". That is right for a scatter plot's points and
wrong for the axis labels and legend around them.

MEASURED over the 24 board-14 extracts: the filter removes **680 glyphs that
carry text**, on 4 pages — 2312.11532 p7 364, lib:5a5c76391c9c p4 264,
0864 p4 38, lib:c57ac038ae5f p293 14. On 0864 p4 the 34 it takes are exactly
the y-axis tick labels of its three charts, character for character the
judge's lost set: `5` x14, `0` x8, `1` x5, `.` x5, `2` x2. Of the 688 glyphs
inside a region, 235 sit within 3 em of a left or bottom edge — where an axis
lives — and 453 in the middle, which is the ink the filter exists for.

SO THE FILTER ASKS A SHRUNKEN BOX. The regions themselves are untouched:
they are the crop rectangles and the page keeps them.

AND A LINE IS NOT MADE FROM TWO FIGURES. Admitting the edge text is half of
it; the row grouper then reads across the page, and three charts side by side
put their axis labels on one baseline. 2312 p7 gained `'100 100'`,
`'(b 100'` and `'k=1 k=1 k=1'`, each from two or three different figures.
Refusing such a line is LOCAL and needs no per-region grouping, which is what
makes this safe to do before that larger change.

STILL WRONG AFTER THIS, measured and not hidden: two garbled lines on 2312 p7
survive because their duplication happens WITHIN one region —
`'DiversityDiversity'` and `'TQTQ'`, two sub-charts' axis titles inside one
detected rectangle. Per-region grouping would not fix those either; they need
sub-region grouping.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")
from pdfreader.texmap import UNKNOWN


def _g(x0, y0, x1, y1, text="x"):
    return D.GlyphNode(
        id="g", page=1, rect=(x0, y0, x1, y1), text=text, cid=0,
        glyphname=None, fontname="ABC+CMR7", family="text", size=7.0,
        tex=UNKNOWN, matrix=(7, 0, 0, 7, x0, y0))


def test_the_band_is_taken_off_the_left_and_bottom():
    """Where an axis and its labels sit. The right and top are untouched."""
    out = D._without_edge_band([(0.0, 0.0, 100.0, 100.0)])
    x0, y0, x1, y1 = out[0]
    assert x0 > 0 and y0 > 0, out
    assert (x1, y1) == (100.0, 100.0), out


def test_a_region_too_small_to_shrink_is_left_alone():
    """Shrinking it would empty it, and an empty box admits the whole page."""
    assert D._without_edge_band([(0.0, 0.0, 5.0, 5.0)]) == [(0.0, 0.0, 5.0, 5.0)]


def test_a_glyph_at_the_edge_survives_the_filter():
    """0864 p4's tick labels: inside the figure, within the band."""
    regions = [(0.0, 0.0, 300.0, 300.0)]
    inner = D._without_edge_band(regions)
    tick = _g(2.0, 150.0, 8.0, 157.0)
    assert D._region_holding(tick.rect, regions) == 0, "it IS inside the figure"
    assert D._region_holding(tick.rect, inner) is None, "and it survives"


def test_a_glyph_in_the_middle_is_still_removed():
    """The ink the filter exists for."""
    regions = [(0.0, 0.0, 300.0, 300.0)]
    inner = D._without_edge_band(regions)
    point = _g(150.0, 150.0, 156.0, 157.0)
    assert D._region_holding(point.rect, inner) == 0


def test_a_line_from_two_figures_is_refused():
    """2312 p7's `'k=1 k=1 k=1'`, one line from three charts."""
    regions = [(0.0, 0.0, 100.0, 300.0), (200.0, 0.0, 300.0, 300.0)]
    line = [_g(5.0, 150.0, 11.0, 157.0), _g(205.0, 150.0, 211.0, 157.0)]
    assert D._spans_two_regions(line, regions) is True


def test_a_line_from_one_figure_is_kept():
    regions = [(0.0, 0.0, 100.0, 300.0), (200.0, 0.0, 300.0, 300.0)]
    line = [_g(5.0, 150.0, 11.0, 157.0), _g(20.0, 150.0, 26.0, 157.0)]
    assert D._spans_two_regions(line, regions) is False


def test_a_line_of_prose_passing_a_figure_is_kept():
    """ENTIRELY, or a sentence that runs past a figure would be dropped."""
    regions = [(0.0, 0.0, 100.0, 300.0), (200.0, 0.0, 300.0, 300.0)]
    line = [_g(5.0, 150.0, 11.0, 157.0),       # inside figure 0
            _g(150.0, 150.0, 156.0, 157.0),    # between the figures
            _g(205.0, 150.0, 211.0, 157.0)]    # inside figure 1
    assert D._spans_two_regions(line, regions) is False


def test_an_empty_line_is_not_refused():
    assert D._spans_two_regions([], [(0, 0, 10, 10)]) is False
    assert D._spans_two_regions([_g(1, 1, 2, 2, text=" ")],
                                [(0, 0, 10, 10)]) is False
