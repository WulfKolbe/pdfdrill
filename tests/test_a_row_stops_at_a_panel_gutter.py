r"""A row stops at the gutter between two figure panels.

T-0156 — the board's worst `ours` row, 2312.11532 p7 at judge 0.0454.

The page's prose is clean and all 26 of its unpaired glyphs sit on two
lines: `0.050.25` loses the page's `k=3` and `k=1`, and the merged
subfigure caption carries the legend digits at x 1348..2093 where the page
has them at 1735..3004 — the same characters in the wrong place. Three
charts side by side put their tick labels, legends and captions on one
baseline each, and the row grouper read straight across.

NOT A MISSING THRESHOLD, which is why nothing here is a new number. In each
row's own type size the gaps at the panel boundaries measure 15.2, 20.1,
20.7 and 43.1 em against `_column_edge`'s 1.5. What was missing is a
BARRIER saying a gap is a figure boundary rather than word spacing, and it
comes from the diagram rectangles the page already carries.

THE THREE EXISTING MECHANISMS WERE CHECKED FIRST, and each is blind to this
for its own reason — `_spans_two_regions` (which already refuses lines
drawn from two figures, and whose docstring names this very page) requires
every glyph to be INSIDE a region, while a chart's labels are drawn just
outside the plot rectangle; `_column_edge` yields one page-level boundary
and skips rows of <= 8 glyphs; `_split_local_columns` infers a gutter from
3+ wide rows in one vertical band, and this band holds four rows at four
baselines. Finding the near-miss first is the point: the capability that
already exists is the one most likely to be rebuilt.
"""
import pytest

from pdfreader.docmodel_six import _split_at_panel_gutters


class G:
    r"""The least a glyph needs for this rule: a box, a size, a text.

    THE Y DEFAULT IS NOT COSMETIC. The first version of this fixture put
    every glyph at y=0 while the panels sit at y 608..738, so the tests
    passed against an implementation that ignored Y — and that
    implementation cut prose anywhere on the page. The default places a
    glyph just below the panels, where a tick label actually is.
    """

    def __init__(self, text, x0, x1, size=7.0, y0=600.0):
        self.text = text
        self.size = size
        self.rect = (x0, y0, x1, y0 + size)


#: three panels side by side, as 2312.11532 p7 has them (points)
PANELS = [(91.0, 608.0, 219.0, 738.0),
          (255.0, 608.0, 383.0, 738.0),
          (419.0, 608.0, 546.0, 738.0)]


def _texts(rows):
    return ["".join(g.text for g in sorted(r, key=lambda g: g.rect[0]))
            for r in rows]


def test_a_tick_row_is_cut_once_per_gutter():
    row = [G("0.15", 95, 110), G("1.0", 260, 272), G("0.15", 423, 438)]
    assert _texts(_split_at_panel_gutters([row], PANELS)) == ["0.15", "1.0", "0.15"]


def test_a_caption_row_is_cut_into_its_subfigures():
    row = [G("(d)", 95, 110, 9.0), G("(e)", 260, 275, 9.0), G("(f)", 423, 438, 9.0)]
    assert _texts(_split_at_panel_gutters([row], PANELS)) == ["(d)", "(e)", "(f)"]


def test_word_spacing_inside_one_panel_is_NOT_cut():
    """The barrier is needed as well as the gap: a caption's own spaces are
    far below 1.5 sizes and lie nowhere near a gutter."""
    row = [G("NYT", 95, 115), G("NPMI", 118, 140), G("300", 143, 158)]
    assert _texts(_split_at_panel_gutters([row], PANELS)) == ["NYTNPMI300"]


def test_a_wide_gap_AWAY_from_a_gutter_is_NOT_cut():
    """The gap alone must not split: this one is 20 sizes wide and sits
    inside panel 2, so it is a figure's own spacing, not a boundary."""
    row = [G("a", 423, 428), G("b", 530, 535)]
    assert _texts(_split_at_panel_gutters([row], PANELS)) == ["ab"]


def test_a_narrow_gap_AT_a_gutter_is_NOT_cut():
    """And the barrier alone must not split: 1.5 sizes still has to be met,
    or a caption that legitimately runs under all three panels is torn."""
    row = [G("a", 215, 220), G("b", 226, 231)]
    assert _texts(_split_at_panel_gutters([row], PANELS)) == ["ab"]


def test_PROSE_FAR_FROM_THE_FIGURES_IS_NOT_CUT():
    r"""The gutter is evidence about the panels' own band and nothing else.

    Measured on arxiv.2609.23822 p11, where the first version of this rule
    had no Y test: `on the sign convention.` was cut into `on the sign
    conventi` + `on.` (the tail then typed as maths), and the regrouping
    cost `e^{n-1}` its exponent. The sample found it; the board's 30 pages
    did not, because none of them has a figure above a wide prose gap.
    """
    # 28.2 pt below the panels at row size 12 = 2.36 sizes, as measured
    row = [G("conventi", 180, 219, 12.0, y0=608.0 - 28.2 - 12.0),
           G("on.", 260, 275, 12.0, y0=608.0 - 28.2 - 12.0)]
    assert _split_at_panel_gutters([row], PANELS)[0] is row


def test_a_caption_BELOW_the_panels_is_still_cut():
    r"""The band reaches down 2.0 of the row's own size.

    MEASURED ON THE ROW THE SPLITTER RECEIVES, not on the final line:
    2312.11532's caption sits 14.0 pt below the panels at row size 9.0 =
    1.56 sizes, and the prose that must survive sits at 2.36. The window is
    (1.56, 2.36); 1.5 falls below it and excluded the caption by 0.6 pt.
    """
    y = 608.0 - 14.0            # 1.56 sizes below, as measured
    row = [G("(d)", 95, 110, 9.0, y0=y), G("(e)", 260, 275, 9.0, y0=y),
           G("(f)", 423, 438, 9.0, y0=y)]
    assert _texts(_split_at_panel_gutters([row], PANELS)) == ["(d)", "(e)", "(f)"]


def test_a_row_that_does_not_cross_is_returned_UNTOUCHED():
    """Identity, not a rebuilt copy, so the rule is a no-op where it does
    not fire — every later pass sees the original object."""
    row = [G("x", 95, 100), G("y", 101, 106)]
    out = _split_at_panel_gutters([row], PANELS)
    assert out[0] is row


def test_one_panel_gives_no_barrier():
    row = [G("0.15", 95, 110), G("1.0", 260, 272)]
    assert _split_at_panel_gutters([row], PANELS[:1])[0] is row


def test_stacked_panels_give_no_barrier():
    """Two panels one above the other overlap in x, so there is no
    horizontal gutter between them and nothing to cut."""
    stacked = [(91.0, 608.0, 546.0, 670.0), (91.0, 680.0, 546.0, 738.0)]
    row = [G("0.15", 95, 110), G("1.0", 260, 272)]
    assert _split_at_panel_gutters([row], stacked)[0] is row


def test_no_diagrams_is_a_no_op():
    row = [G("0.15", 95, 110), G("1.0", 260, 272)]
    assert _split_at_panel_gutters([row], [])[0] is row


def test_every_glyph_survives_a_cut():
    """A split redistributes glyphs; it must never drop one. The reading
    loses content when a row is rebuilt from a filtered copy."""
    row = [G("0.15", 95, 110), G("1.0", 260, 272), G("0.15", 423, 438)]
    out = _split_at_panel_gutters([row], PANELS)
    assert sorted(id(g) for r in out for g in r) == sorted(id(g) for g in row)


def test_a_blank_glyph_is_kept():
    """Blanks carry spacing for later passes, so the cut keeps them."""
    row = [G("0.15", 95, 110), G(" ", 111, 114), G("1.0", 260, 272)]
    out = _split_at_panel_gutters([row], PANELS)
    assert sum(len(r) for r in out) == 3




def _panel_barriers_of(d):
    from pdfreader.docmodel_six import _panel_barriers
    return _panel_barriers(d)


# ---------------------------------------------------------------------------
# T-0156 — AND A SCRIPT DOES NOT ATTACH ACROSS A PANEL GUTTER.
#
# inkdrill-80 reported 2312 p7 rising 0.0394 -> 0.0454 after the split, with
# two line boxes overlapping by 363 px: `(d) NYT-NPMI. 100 200 300` at
# x 393..1308 running into `(e) NYT-Diversity. 100 200 300` at x 945..1877,
# on one row. Its diagnosis was that each split piece inherits the pre-split
# region and must recompute it from its own glyphs.
#
# THE REGION WAS NOT THE CAUSE. Traced with a logging list over `groups`, the
# splitter emits `(d)NYT-NPMI.` and `(e)NYT-Diversity.` CLEAN, and the
# script-absorption pass then puts the digits back one at a time —
# `(d)NYT-NPMI.100` -> `...1002` -> `...10020` -> `...100200300` — because a
# chart's legend digits are SMALLER than the caption beside them and so read
# as scripts. Recomputing the regions would have shrunk the boxes while
# leaving the wrong glyphs in them.
#
# It is also why those digits came out typed as maths (`$100 200$`): a script
# is maths by construction. One cause, two symptoms, and the rider the
# coordinator had already set aside closes with it.


# ---------------------------------------------------------------------------
# T-0156 — THE BAND IS PART OF THE BARRIER.
#
# Five tests were removed here and replaced by the ones below. They asserted
# on the IMPLEMENTATION'S TEXT — `assert "for _b in _bars" in body`, grepped
# out of docmodel_six.py — and a refactor that improved the design broke all
# five while changing no behaviour. A source grep pins the code, not the
# rule; `_PanelBarriers.crosses` can be called, so the rule can be tested.


def _bars2():
    from pdfreader.docmodel_six import _panel_barriers
    # two panels side by side, 2312.11532 p7's geometry in points
    return _panel_barriers([(91.0, 608.0, 219.0, 738.0),
                            (255.0, 608.0, 383.0, 738.0)])


def test_a_gutter_inside_the_band_crosses():
    b = _bars2()
    assert b.xs and b.crosses(200.0, 300.0, 600.0, 607.0, reach=18.0)


def test_the_same_gutter_far_from_the_band_does_not():
    r"""Prose 490 pt up the page is nobody's figure: this is the regression
    that cut `on the sign convention.` in half and detached
    `\psi|_{K_{H} \times\{0\}}` from its base."""
    b = _bars2()
    assert not b.crosses(200.0, 300.0, 110.0, 120.0, reach=18.0)


def test_a_Y_RANGE_AND_NOT_A_BASELINE():
    """A caption's baseline can sit below the band while its box reaches in.
    Routing the split through a baseline POINT merged 2312.11532 p7's three
    captions back into one line, measured, which is why `crosses` takes a
    range."""
    b = _bars2()
    assert not b.crosses(200.0, 300.0, 588.0, 588.0, reach=18.0)
    assert b.crosses(200.0, 300.0, 585.1, 606.3, reach=18.0)


def test_no_gutter_between_the_two_x_means_no_crossing():
    b = _bars2()
    assert not b.crosses(100.0, 150.0, 600.0, 607.0, reach=18.0)


def test_x_given_backwards_is_the_same_interval():
    b = _bars2()
    assert b.crosses(300.0, 200.0, 600.0, 607.0, reach=18.0)


def test_stacked_panels_carry_no_barrier_and_never_cross():
    from pdfreader.docmodel_six import _panel_barriers
    b = _panel_barriers([(91.0, 608.0, 546.0, 670.0),
                         (91.0, 680.0, 546.0, 738.0)])
    assert b.xs == ()
    assert not b.crosses(0.0, 999.0, 600.0, 700.0, reach=18.0)


def test_no_panels_carries_no_barrier_and_never_cross():
    from pdfreader.docmodel_six import _panel_barriers
    b = _panel_barriers([])
    assert b.xs == () and b.y0 == 0.0 and b.y1 == 0.0
    assert not b.crosses(0.0, 999.0, 0.0, 999.0, reach=18.0)


def test_every_consumer_asks_through_crosses():
    """Split, rejoin sweep and script absorption. The rejoin sweep had NO
    band test until this type existed — latent, and found only because the
    omission became impossible to express."""
    from pathlib import Path
    src = Path("src/pdfreader/docmodel_six.py").read_text(encoding="utf-8")
    assert src.count(".crosses(") >= 4      # split, 2x rejoin, absorption
    # and nobody reads the barrier x's without the band any more
    assert "for _b in _bars" not in src
    assert "for b in bars" not in src
