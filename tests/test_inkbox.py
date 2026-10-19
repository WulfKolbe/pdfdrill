"""The page-ink layer: connected components, rows, and the two cleanups.

Each cleanup here exists because of a measured failure, and the test names say
which: a page-tall scan band collapsing a page to one row, and the slivers that
band broke into stretching every row to the page edge.
"""
from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

from pdfdrill import inkbox as ib


def _blank(h, w):
    return np.full((h, w), 255, dtype=np.uint8)


# ── components ─────────────────────────────────────────────────────────────

def test_a_diagonal_touch_is_one_component():
    """8-connected. A thin italic stroke touches only at the corner."""
    g = _blank(20, 40)
    g[2:5, 2:5] = 0
    g[5:8, 5:8] = 0
    assert ib.components(g) == [(2, 2, 8, 8)]


def test_a_gap_of_one_pixel_is_two_components():
    g = _blank(10, 12)
    g[1:3, 1:3] = 0
    g[1:3, 5:7] = 0
    assert len(ib.components(g)) == 2


def test_boxes_are_half_open_so_the_width_is_the_pixel_count():
    g = _blank(10, 10)
    g[2:6, 3:9] = 0                       # 4 rows, 6 columns of ink
    (x0, y0, x1, y1), = ib.components(g)
    assert (x1 - x0, y1 - y0) == (6, 4)


def test_components_come_back_in_reading_order():
    g = _blank(40, 40)
    g[30:33, 30:33] = 0                   # written first, lower on the page
    g[2:5, 20:23] = 0
    g[2:5, 2:5] = 0
    got = ib.components(g)
    assert [b[:2] for b in got] == [(2, 2), (20, 2), (30, 30)]


def test_min_side_drops_specks_and_keeps_an_i_dot():
    g = _blank(30, 30)
    g[1:2, 1:2] = 0                       # a 1x1 mote
    g[10:20, 10:14] = 0                   # a stem
    assert len(ib.components(g)) == 2
    assert len(ib.components(g, min_side=3)) == 1


def test_blank_page_has_no_components():
    assert ib.components(_blank(50, 50)) == []


def test_otsu_separates_a_grey_scan():
    """Ink at 40, paper at 210: the threshold lands between them."""
    g = np.full((60, 60), 210, dtype=np.uint8)
    g[10:30, 10:40] = 40
    thr = ib.otsu(g)
    assert 40 <= thr < 210
    assert (g <= thr).sum() == 20 * 30


# ── rows ───────────────────────────────────────────────────────────────────

def test_rows_group_a_line_and_separate_two():
    boxes = [(0, 0, 10, 10), (12, 1, 22, 11),          # row 1
             (0, 40, 10, 50)]                          # row 2
    assert [len(r) for r in ib.rows(boxes)] == [2, 1]


def test_a_tall_glyph_stays_with_the_row_it_mostly_covers():
    """An integral sign spans two rows; it belongs to one of them, and it does
    not merge them."""
    tall = (0, 0, 8, 60)
    r1 = [(10, 0, 20, 20)]
    r2 = [(10, 44, 20, 60)]
    got = ib.rows([tall] + r1 + r2)
    assert len(got) == 2, "the tall glyph merged two printed rows"


def test_a_page_tall_band_does_not_collapse_the_rows_but_does_inflate_one():
    """The measured failure and what is left of it.

    A component spanning the page used to join the first row, stretch it to
    the whole page, and pull every other component in after it — one row for
    the whole page. The two-phase grouping removes that: the band is tall, so
    it is assigned to the band it overlaps most and never extends one.

    What remains is that the row it lands in now has a page-tall UNION box,
    which is a box no printed line has. `max_height` is what keeps it out
    altogether, and that is why `gemma_reader` passes one.
    """
    band = (0, 0, 6, 1000)
    text = [(50, y, 200, y + 20) for y in range(0, 900, 50)]
    rows = ib.rows([band] + text)
    assert len(rows) == len(text), "the band merged the page's rows"
    inflated = [r for r in rows if band in r]
    assert len(inflated) == 1
    assert ib.union_box(inflated[0])[3] == 1000      # the box is still wrong

    clean = ib.rows([band] + text, max_height=100)
    assert len(clean) == len(text)
    assert all(band not in r for r in clean)
    assert max(ib.union_box(r)[3] for r in clean) < 1000


def test_median_height_is_taken_over_components():
    assert ib.median_height([(0, 0, 1, 10), (0, 0, 1, 20), (0, 0, 1, 30)]) == 20.0
    assert ib.median_height([], default=7.0) == 7.0


# ── the two cleanups ───────────────────────────────────────────────────────

def test_drop_scan_edges_removes_the_slivers_a_band_broke_into():
    """Seven 2px slivers at the right border, each joining a different text
    row and stretching it to the page edge."""
    w, h = 2037, 3413
    slivers = [(2035, y, 2037, y + 6) for y in range(1200, 1620, 60)]
    text = [(180, y, 1900, y + 30) for y in range(1200, 1620, 60)]
    kept = ib.drop_scan_edges(slivers + text, w, h)
    assert kept == text
    assert max(b[2] for b in kept) == 1900


def test_drop_scan_edges_keeps_ink_inside_the_margin():
    assert ib.drop_scan_edges([(10, 10, 100, 40)], 500, 500) == [(10, 10, 100, 40)]


def test_drop_speck_rows_removes_a_row_with_no_glyph_in_it():
    real = [(100, 100, 400, 130)]
    speck = [(50, 50, 54, 54)]
    rows = [speck, real]
    assert ib.drop_speck_rows(rows, line_height=30.0) == [real]


# ── box arithmetic ─────────────────────────────────────────────────────────

def test_iou_of_a_box_with_itself_is_one_and_disjoint_is_zero():
    a, b = (0, 0, 10, 10), (20, 20, 30, 30)
    assert ib.iou(a, a) == 1.0
    assert ib.iou(a, b) == 0.0


def test_iou_of_a_degenerate_box_is_zero_not_a_crash():
    assert ib.iou((5, 5, 5, 5), (0, 0, 10, 10)) == 0.0


def test_union_box_of_nothing_is_none():
    assert ib.union_box([]) is None
    assert ib.union_box([(1, 2, 3, 4), (10, 0, 12, 20)]) == (1, 0, 12, 20)


def test_prune_row_outliers_drops_a_far_small_fleck():
    """MEASURED: ten 1-2 px flecks in the outer margin of a reference scan,
    each joining the text row it happened to align with and stretching that
    row's box from 0.94 of the page to 0.996."""
    text = [(180, 100, 1900, 130)]
    fleck = (2027, 110, 2029, 116)
    (row,) = ib.prune_row_outliers([text + [fleck]], line_height=31.0)
    assert row == text


def test_prune_row_outliers_keeps_an_equation_number():
    """Far from the row and deliberately so, but not small — and the reader
    needs its ink to cut it out of the display's row. A threshold on distance
    alone would throw it away."""
    number = (40, 100, 85, 140)
    body = [(400, 100, 900, 140)]
    (row,) = ib.prune_row_outliers([[number] + body], line_height=40.0)
    assert number in row


def test_prune_row_outliers_keeps_a_small_glyph_that_is_close():
    """An accent, an `i` dot, a hyphen: small, but part of the line."""
    row_in = [(100, 100, 140, 130), (145, 95, 150, 100), (160, 100, 400, 130)]
    (row,) = ib.prune_row_outliers([row_in], line_height=30.0)
    assert row == row_in


def test_prune_row_outliers_leaves_a_single_component_row_alone():
    assert ib.prune_row_outliers([[(1, 1, 3, 3)]], 30.0) == [[(1, 1, 3, 3)]]
