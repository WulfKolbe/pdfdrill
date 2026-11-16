"""
The two-column gutter is found as the EMPTY BAND the ink shows, not as a
density valley in a histogram.

THE DEFECT, reported by the owner on arxiv.2209.02970 (2026-11-16) as "2 column
design not recognized". `_column_split` bins glyph x-centres into 48 bins and
rejects the valley unless the emptiest bin holds under 12% of the median bin.
On that paper, an ACL two-column PDF 595.3 pt wide:

    bin width                                    12.40 pt
    the real gutter, by zero ink coverage (p2)    x 292..304, 12 pt
    emptiest bin in the gutter band (bin 24)      34 chars
    median non-empty bin                          98
    threshold, 0.12 * median                      11.8

THE GUTTER IS NARROWER THAN A BIN and straddles two of them -- bin 23 holds the
left column's last glyphs, bin 24 the right column's first -- so no bin can
ever be empty. The deepest achievable valley is about 65% where the test
demands 88%. All 21 pages read as one column and the line clusterer welded a
left-column line to a right-column line:

    '1 Introduction tions, benchmarks, and datasets.'
    'L Computing and Natural Language (CCNL). dation models can be adapted to'
    'Remarkable advances in Artificial Intelligence (AI) ized and user-centere'

A band of x at which no glyph paints is not a proxy for a gutter; it is the
gutter.

MEASURED, through the real call path (`_column_split_for_lines`):

    arxiv.2209.02970, 21 pages      19 split at x = 298.0..298.5
    pages 9 and 17                  not split, correctly -- a 454x114 pt
                                    raster and a full-width table
    0001124, 69 pages, one column   0 split   <- the control that matters

And on the reading itself, page 1: lines crossing the gutter 47 -> 8, lines
wider than one column 42 -> 5, line count 60 -> 99 as the welded pairs came
apart. Over all 21 pages, lines crossing the gutter 427 -> 29.

A PAGE WHOSE HEADER BLOCK SPANS THE WIDTH needs the measurement taken below
that block, and excluding full-width ROWS is not enough -- measured on the same
page 1, whose author block carries internal spaces wide enough that
`_spans_gutter` calls it two columns and keeps its glyphs, which fill the
gutter again. `_header_block_cuts` offers the row bottoms in the top half,
nearest first, and the search stops at the first cut where a band appears. No
fraction of the page is assumed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import chars_to_lines as C

PW = 595.3                      # A4 width in points, as the paper is
GUTTER = (292.0, 304.0)         # the real one, measured
CH = 5.0                        # a glyph's width
LH = 11.0                       # a line's height


def _glyph(x, top):
    return {"x0": x, "x1": x + CH, "top": top, "bottom": top + 8.9}


def _row(top, x0, x1):
    """A row of glyphs from x0 to x1, one every CH points."""
    out, x = [], x0
    while x + CH <= x1:
        out.append(_glyph(x, top))
        x += CH
    return out


def _two_columns(n_rows=40, top0=100.0):
    """A page with the measured gutter: left 70.9..292, right 304..524.4."""
    items = []
    for i in range(n_rows):
        top = top0 + i * LH
        items += _row(top, 70.9, GUTTER[0])
        items += _row(top, GUTTER[1], 524.4)
    return items


def _one_column(n_rows=40, top0=100.0):
    items = []
    for i in range(n_rows):
        items += _row(top0 + i * LH, 70.9, 524.4)
    return items


def test_a_gutter_narrower_than_a_histogram_bin_is_found():
    split = C._column_split_for_lines(_two_columns(), PW)
    assert split is not None, \
        "the gutter the owner's page actually has was not found"
    assert GUTTER[0] <= split <= GUTTER[1], \
        f"split at {split}, outside the real gutter {GUTTER}"


def test_the_histogram_alone_cannot_find_it():
    """Not a complaint about `_column_split` but the reason the gap rule
    exists: on this geometry the old detector is blind, so a test that only
    exercised the new path could pass with the bug still present."""
    assert C._column_split(_two_columns(), PW) is None, \
        "the histogram found it after all — then the gap rule is not needed, " \
        "and this test should be deleted rather than inverted"


def test_a_single_column_page_is_never_split():
    assert C._column_split_for_lines(_one_column(), PW) is None, \
        "a single-column page was split in two"


def test_a_spanning_header_block_does_not_hide_the_gutter():
    """The title/author block paints across the middle at its own y. The
    gutter is empty below it, and that is where it has to be measured."""
    items = []
    for i in range(6):                                  # the header block
        items += _row(100.0 + i * LH, 70.9, 524.4)
    items += _two_columns(n_rows=40, top0=100.0 + 7 * LH)
    split = C._column_split_for_lines(items, PW)
    assert split is not None and GUTTER[0] <= split <= GUTTER[1], \
        f"a spanning header block hid the gutter: split={split}"


def test_one_narrow_stray_column_is_not_a_second_column():
    """Both sides must carry a real share of the glyphs, so a marginal note or
    a line-number column does not split the page."""
    items = _one_column(n_rows=40)
    for i in range(40):                                 # a thin right margin
        items += _row(100.0 + i * LH, 560.0, 575.0)
    assert C._column_split_for_lines(items, PW) is None, \
        "a narrow stray column was read as a second text column"


def test_a_page_with_almost_no_text_is_not_split():
    """Under 60 glyphs there is nothing to measure, and a guess here would be
    a two-column reading order imposed on a title page or a plate."""
    assert C._gutter_by_gap(_row(100.0, 70.9, 150.0), PW) is None


def test_the_band_must_be_wide_enough_to_be_a_gutter():
    """A word space is not a gutter. The floor is max(6 pt, 1.2% of the page),
    which is 7.1 pt here."""
    items = []
    for i in range(40):
        top = 100.0 + i * LH
        items += _row(top, 70.9, 295.0)        # glyphs every 5 pt: ends 290.9
        items += _row(top, 294.0, 524.4)       # a 3.1 pt band only
    assert C._column_split_for_lines(items, PW) is None, \
        "a 3 pt gap was accepted as a column gutter"
