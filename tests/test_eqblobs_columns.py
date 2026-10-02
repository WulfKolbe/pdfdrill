r"""
848 — a row-profile band model must project PER COLUMN, not per page.

`_group_lines` projects ink onto the y axis to find visual lines, which is right
and its docstring says why: pairwise vertical overlap merged a tall display
equation with the prose beside it, so no line was ever short-and-centred and a
paper with 34 displays yielded none.

Over a TWO-COLUMN page the whole-page projection reintroduces exactly that
failure: a band spans both columns, so a left-column line and an unrelated
right-column line land in one "line", every line measures full-body-width, and
nothing is short-and-centred again.

inkdrill measured the shape on their own band model — single-column recall
median 92.9%, two-column 18.8%, no overlap. It does not degrade, it breaks. Seven
of their twenty sampled library documents are two-column.

Measured here, `pfahler_morik_2020a` pages 2-4:

    before   25 display-math regions, reported 1-column
    after     7 display-math regions, reported 2-column

and `eljc-v33i3p12` (single-column) is unchanged at 2 regions, 1-column.

`_count_columns` was wrong for the same reason and could not have been right: it
counted banded LINES crossing the midline, and on a two-column page every band
already crossed. The question was asked of data that had lost the answer.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.eqblobs import (                                 # noqa: E402
    _bands, _count_columns, _group_lines, _gutter_x)


class _B:
    """The five fields the banding reads off a blob."""
    def __init__(self, x0, y0, x1, y1):
        self.min_x, self.min_y, self.max_x, self.max_y = x0, y0, x1, y1
        self.area = max(1, (x1 - x0) * (y1 - y0))


def _two_columns(rows=12, gutter=(480, 520), width=1000):
    """Left and right columns at the SAME y, which is what merges."""
    out = []
    for i in range(rows):
        y = 50 + i * 20
        out += [_B(60, y, gutter[0] - 10, y + 12),
                _B(gutter[1] + 10, y, 940, y + 12)]
    return out


def test_bands_merge_overlapping_spans():
    assert _bands([(0, 10), (5, 15), (30, 40)], 100) == [(0, 15), (30, 40)]


def test_a_single_column_page_has_no_gutter():
    blobs = [_B(60, 50 + i * 20, 940, 62 + i * 20) for i in range(12)]
    assert _gutter_x(blobs, 1000) is None


def test_a_two_column_page_has_one_and_it_is_in_the_middle():
    gx = _gutter_x(_two_columns(), 1000)
    assert gx is not None
    assert 440 < gx < 560, gx


def test_a_blob_level_crossing_count_cannot_find_it():
    """Recorded because it was the first thing tried: at 300 dpi a connected
    component is a glyph, and 0.00% of them cross the midline on a
    single-column page OR a two-column one. The signal had to be the ink
    profile."""
    blobs = _two_columns()
    mid = 500.0
    band = 1000 * 0.04
    crossing = sum(1 for b in blobs if b.min_x < mid - band and b.max_x > mid + band)
    assert crossing == 0


def test_two_columns_are_banded_separately():
    """THE DEFECT. One band per column row, not one band spanning both."""
    lines = _group_lines(_two_columns(), height=400, width=1000)
    assert len(lines) == 24, len(lines)
    for ln in lines:
        span = max(b.max_x for b in ln) - min(b.min_x for b in ln)
        assert span < 450, f"a line spans the gutter: {span}"


def test_without_the_width_the_old_whole_page_banding_still_applies():
    """`width` defaults to 0 so any caller that has not been updated keeps its
    previous behaviour rather than silently changing."""
    lines = _group_lines(_two_columns(), height=400)
    assert len(lines) == 12, len(lines)


def test_a_full_width_element_keeps_its_own_band():
    """A rule or spanning heading is ONE line, not two halves."""
    blobs = _two_columns() + [_B(60, 400, 940, 412)]
    lines = _group_lines(blobs, height=500, width=1000)
    wide = [ln for ln in lines
            if max(b.max_x for b in ln) - min(b.min_x for b in ln) > 800]
    assert len(wide) == 1, [len(ln) for ln in lines]


def test_lines_come_back_in_document_order():
    lines = _group_lines(_two_columns(), height=400, width=1000)
    keys = [(min(b.min_y for b in ln), min(b.min_x for b in ln)) for ln in lines]
    assert keys == sorted(keys)


def test_the_column_count_comes_from_the_gutter():
    blobs = _two_columns()
    lines = _group_lines(blobs, height=400, width=1000)
    assert _count_columns(lines, 60, 940, _gutter_x(blobs, 1000)) == 2
    assert _count_columns(lines, 60, 940, None) == 1


class TestTheGutterCutSitsInTheGap:
    r"""849 — the cut is placed on inkdrill's thirty pages, not on my five.

    Their column label is INDEPENDENT of this profile — it comes from where the
    reader's prose lines start — so it is a real oracle and not a restatement of
    the measurement:

        1-column, 16 pages   0.00 every one. Not "small": exactly zero.
        2-column, 14 pages   0.00 0.00 0.07 0.50 0.53 1.18 1.77
                             4.21 4.35 4.39 4.41 4.41 4.41 4.45

    The gap is 1.77 -> 4.21. Seven of the two-column pages have a figure or table
    spanning the column break and genuinely have no gutter, which is why the
    decision is per page and why those seven SHOULD fall below the cut.

    The trap, which inkdrill asked about and was right to: 4.5% was the value
    OBSERVED on one page and it is the two-column population's MAXIMUM. A cut
    there finds 0 of 14. A gutter's share of the body shrinks as the body widens,
    so the observed number is the worst available threshold.
    """

    ONE = [0.00] * 16
    TWO = [0.00, 0.00, 0.07, 0.50, 0.53, 1.18, 1.77,
           4.21, 4.35, 4.39, 4.41, 4.41, 4.41, 4.45]

    def test_the_cut_is_three_percent(self):
        from pdfdrill.eqblobs import _GUTTER_MIN_FRAC
        assert _GUTTER_MIN_FRAC == 0.03

    def test_no_single_column_page_is_misread(self):
        from pdfdrill.eqblobs import _GUTTER_MIN_FRAC
        cut = _GUTTER_MIN_FRAC * 100
        assert [v for v in self.ONE if v >= cut] == []

    def test_every_clean_gutter_is_found(self):
        from pdfdrill.eqblobs import _GUTTER_MIN_FRAC
        cut = _GUTTER_MIN_FRAC * 100
        found = [v for v in self.TWO if v >= cut]
        assert len(found) == 7, found
        assert min(found) == 4.21

    def test_the_cut_is_centred_in_the_gap(self):
        """Not merely on the right side of it. 2% also separates these two
        populations, with 0.23pp of margin above 1.77 against 2.21pp below
        4.21 — correct, and one re-measurement away from being wrong."""
        from pdfdrill.eqblobs import _GUTTER_MIN_FRAC
        cut = _GUTTER_MIN_FRAC * 100
        below = max(v for v in self.TWO if v < cut)
        above = min(v for v in self.TWO if v >= cut)
        assert cut - below > 1.0, f"only {cut - below:.2f}pp above {below}"
        assert above - cut > 1.0, f"only {above - cut:.2f}pp below {above}"

    def test_the_observed_value_would_have_found_nothing(self):
        """Why the constant is not the number that was measured."""
        assert [v for v in self.TWO if v >= 4.5] == []
