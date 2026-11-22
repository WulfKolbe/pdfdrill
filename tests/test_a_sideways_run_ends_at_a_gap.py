r"""A sideways run ends where a gap says the label ended.

T-0156, under the owner's rule of 2026-11-22 — fix at the lowest level.
inkdrill-10, board 0864 p4: the board's worst `ours` row at 0.0656, nearly
twice the next.

`_group_rotated` keys a run on the coordinate PERPENDICULAR to the writing
direction, so every rotated glyph sharing a rounded x lands in ONE run
however far apart it is along the writing axis — and nothing split it.
Horizontal rows ARE split at a wide gap: `_column_edge` takes a gap of 1.5
type sizes as separating two blocks on one row. Sideways runs were not.
This is that same rule along the other axis, and no new constant.

WHAT IT COST. 0864 p4 is a chart page: our reading gave it 242 lines
against MathPix's 83, 135 of ours `rotated_text`, and the lines held
`monspc`, `PUSPUS`, `rndOO`, `rrd(O,O)` — Figure 3's axis and legend labels
run together. The judge's unpaired glyphs were the SAME characters on both
sides (14 E, 7 Y, 7 U, 7 S, 7 s, 7 R, 7 P, 7 D … identical distributions),
so nothing was lost: the text was read and placed wrong. 50% of the 226
unpaired sat in five lines, and those lines were the merged labels.

MEASURED, in ems of each run's own type size:

    'monspc'    0.39 0.25 [2.41] 0.19 0.25        -> mon | spc
    'PUSPUS'    0.93 1.09 [5.54] 0.93 1.08        -> PUS | PUS
    'rrd(O,O)'  0.43 0.43 0.64 0.61 [4.89] 0.72 [4.48]

within-label 0.19-1.09, between-label 2.41-5.54.

AND THE STAMP SURVIVES, which is what this function was written for: on
arxiv.0912.2444, 1503.00301 and 1909.00741 the margin stamp stays ONE run,
double spaces and all.
"""
import pytest

from pdfreader.docmodel_six import _split_rotated_run


class G:
    """Enough of a GlyphNode for the splitter: a rect and a size."""

    def __init__(self, y0, y1, size=10.0, x0=0.0, x1=5.0):
        self.rect = (x0, y0, x1, y1)
        self.size = size
        self.text = "x"


def test_one_label_is_not_split():
    run = [G(0, 8), G(9, 17), G(18, 26)]          # gaps of 1 unit on size 10
    assert len(_split_rotated_run(run, vertical=True)) == 1


def test_two_labels_are_split_at_the_wide_gap():
    run = [G(0, 8), G(9, 17), G(45, 53), G(54, 62)]   # a 28-unit gap, 2.8 em
    out = _split_rotated_run(run, vertical=True)
    assert len(out) == 2
    assert [len(x) for x in out] == [2, 2]


def test_the_threshold_is_the_horizontal_one():
    r"""1.5 type sizes — `_column_edge`'s rule, not a number from 0864."""
    size = 10.0
    just_under = [G(0, 8), G(8 + 1.4 * size, 8 + 1.4 * size + 8, size)]
    just_over = [G(0, 8), G(8 + 1.6 * size, 8 + 1.6 * size + 8, size)]
    assert len(_split_rotated_run(just_under, vertical=True)) == 1
    assert len(_split_rotated_run(just_over, vertical=True)) == 2


def test_a_run_of_one_glyph_is_returned_whole():
    g = G(0, 8)
    out = _split_rotated_run([g], vertical=True)
    assert out == [[g]]


def test_the_gap_is_measured_whichever_way_the_run_runs():
    """A run advancing DOWN the page is sorted descending; the clear
    distance between two glyphs is the same either way."""
    down = [G(54, 62), G(45, 53), G(9, 17), G(0, 8)]
    out = _split_rotated_run(down, vertical=True)
    assert len(out) == 2


def test_a_horizontal_sideways_run_splits_on_x():
    """`vertical=False` — a run advancing along x (180-degree text)."""
    run = [G(0, 8, 10.0, 0, 5), G(0, 8, 10.0, 6, 11),
           G(0, 8, 10.0, 40, 45), G(0, 8, 10.0, 46, 51)]
    out = _split_rotated_run(run, vertical=False)
    assert len(out) == 2


@pytest.mark.parametrize("gap_em,expected", [(0.2, 1), (1.0, 1), (1.4, 1),
                                             (1.5, 2), (2.4, 2), (5.5, 2)])
def test_the_measured_gaps_fall_the_right_side(gap_em, expected):
    """The within-label gaps measured on 0864 p4 (0.19-1.09 em) stay joined;
    the between-label ones (2.41, 5.54) split."""
    size = 10.0
    run = [G(0, 8, size), G(8 + gap_em * size, 8 + gap_em * size + 8, size)]
    assert len(_split_rotated_run(run, vertical=True)) == expected
