r"""Phase 4 — rule weights, and which rule was drawn.

`svg.py` already injects `booktabs` when it sees `\toprule`. What it cannot
know is WHICH rule was drawn, and for a round trip `\toprule` / `\midrule` /
`\bottomrule` are three different documents.

THE MEASUREMENT IS EMITTED, THE CLASSIFICATION IS COMPUTED HERE. inkdrill
supplies `ink.rules[].width_pt` and deliberately no name, because the absolute
value runs ~12% high from rasteriser coverage and the RATIO is unstable under
pixel quantisation — 1.50, 1.33, 1.67, 1.40, 1.67 measured against a nominal
1.60. What is stable is the ORDERING, and pdfdrill has the table context needed
to use it: cluster the rules within one table, take the heavier cluster, and
confirm by position.

Ground truth for these tests is a real compiled booktabs table:

    \toprule     y 125.20   0.7970 pt
    \midrule     y 142.31   0.4980 pt
    \midrule     y 171.22   0.4980 pt
    \bottomrule  y 188.33   0.7970 pt      ratio 1.60

Rule 5 applies throughout: where the evidence does not separate, nothing is
named. A table ruled entirely with `\hline` has ONE weight class and therefore
no weight evidence at all, and saying `toprule` there would be a guess wearing
a measurement's clothes.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.ink_rules import (  # noqa: E402
    BOTTOMRULE, CMIDRULE, MIDRULE, TOPRULE, UNKNOWN, rank_rules)


def _r(width_pt, y, orient="h", x0=148.7, x1=285.9):
    return {"width_pt": width_pt, "orient": orient,
            "x0": x0, "y0": y, "x1": x1, "y1": y + width_pt}


# real compiled booktabs, measured with pdfplumber
_BOOKTABS = [_r(0.7970, 125.20), _r(0.4980, 142.31),
             _r(0.4980, 171.22), _r(0.7970, 188.33)]


def test_a_real_booktabs_table_names_its_four_rules():
    got = rank_rules(_BOOKTABS)
    assert [g["kind"] for g in got] == [TOPRULE, MIDRULE, MIDRULE, BOTTOMRULE]


def test_the_ordering_decides_not_the_absolute_value():
    """The absolute width is never trustworthy and does not become trustworthy
    at higher resolution. Measured on this fixture against pdflatex's truth:
    +24.2% at 400 dpi, +5.4% at 600, +12.9% at 800, +5.4% at 1200 — it does not
    shrink with resolution because it is QUANTISATION, not a bias. The measured
    width is the true width rounded up to a whole pixel, so the error oscillates
    with how the two happen to line up.

    Inflating every rule must therefore never move a name, and the guard is set
    at the worst inflation measured (+25%), not the nominal +12%.
    """
    for factor in (1.12, 1.25):
        inflated = [dict(r, width_pt=r["width_pt"] * factor) for r in _BOOKTABS]
        assert [g["kind"] for g in rank_rules(inflated)] == \
               [g["kind"] for g in rank_rules(_BOOKTABS)], factor


def test_the_separation_margin_is_reported_in_pixels_at_the_render_dpi():
    """THE MARGIN IS RESOLUTION-DEPENDENT, NOT A CONSTANT. Measured on the
    compiled fixture: 1.0 px at 400 dpi, 2.0 at 600, 4.0 at 800, 5.0 at 1200.

    A margin of one pixel means one pixel of extra noise flips a `\\toprule`
    into a `\\midrule`, so the margin has to reach a reader rather than being a
    property the classifier keeps to itself.
    """
    got = rank_rules(_BOOKTABS, render_dpi=400)
    sep = got[0]["separation"]
    assert round(sep["margin_pt"], 3) == 0.299        # 0.797 - 0.498
    assert round(sep["margin_px"], 1) == 1.7
    assert sep["thin"] is True                        # under 2 px


def test_a_thin_margin_names_the_remedy_rather_than_only_the_number():
    got = rank_rules(_BOOKTABS, render_dpi=400)
    assert "800" in got[0]["separation"]["advice"]


def test_the_same_rules_at_800_dpi_are_not_flagged_thin():
    got = rank_rules(_BOOKTABS, render_dpi=800)
    assert got[0]["separation"]["thin"] is False


def test_no_render_dpi_reports_the_margin_in_points_and_claims_no_pixels():
    """A file that does not declare its resolution cannot be given a pixel
    margin, and inventing one would be a measurement nobody made."""
    sep = rank_rules(_BOOKTABS)[0]["separation"]
    assert sep["margin_px"] is None and sep["thin"] is None


def test_an_unstable_ratio_still_names_the_same_rules():
    """1.33 and 1.67 are both real measurements of the same nominal 1.60."""
    for heavy in (0.66, 0.83):                      # ratio 1.33 and 1.67
        rules = [_r(heavy, 125.2), _r(0.498, 142.3),
                 _r(0.498, 171.2), _r(heavy, 188.3)]
        assert [g["kind"] for g in rank_rules(rules)] == \
               [TOPRULE, MIDRULE, MIDRULE, BOTTOMRULE]


def test_one_weight_class_yields_no_weight_evidence_and_says_so():
    r"""A table ruled with `\hline` throughout has one width everywhere. There
    is no heavier cluster, so there is nothing to rank — and naming the first
    one `toprule` on position alone would be a guess wearing a measurement's
    clothes. Rule 5."""
    rules = [_r(0.4, 100.0), _r(0.4, 120.0), _r(0.4, 140.0)]
    got = rank_rules(rules)
    assert [g["kind"] for g in got] == [UNKNOWN, UNKNOWN, UNKNOWN]
    assert got[0]["reason"] == "one weight class"


def test_a_heavy_rule_in_the_middle_is_not_called_a_toprule():
    """Position CONFIRMS the weight; it does not get overruled by it. A heavy
    interior rule is a real thing (a group separator) and naming it `toprule`
    because it is heavy would put it at the top of the reconstructed table."""
    rules = [_r(0.498, 100.0), _r(0.797, 130.0), _r(0.498, 160.0)]
    got = rank_rules(rules)
    assert got[1]["kind"] == UNKNOWN
    assert "not at an edge" in got[1]["reason"]


def test_a_partial_width_interior_rule_is_a_cmidrule_not_a_midrule():
    r"""Ground truth, 2409.18839 p9 table 1: `\toprule` 0.9017 pt over 346.4 pt,
    then TWO rules of 0.3006 pt spanning only 95.6 pt, then a full-width
    `\midrule` 0.5006 pt, then `\bottomrule`.

    The short ones are `\cmidrule{i-j}`, and calling them `\midrule` draws a
    line across the whole table in the reconstruction. The evidence is the
    LENGTH, which was sitting in the record unused.
    """
    rules = [_r(0.9017, 185.26, x0=100, x1=446.4),
             _r(0.3006, 201.55, x0=120, x1=215.6),
             _r(0.5006, 217.65, x0=100, x1=446.4),
             _r(0.9017, 277.92, x0=100, x1=446.4)]
    got = rank_rules(rules)
    assert [g["kind"] for g in got] == [TOPRULE, CMIDRULE, MIDRULE, BOTTOMRULE]
    assert round(got[1]["span"], 2) == 0.28        # 95.6 / 346.4


def test_a_full_width_interior_rule_stays_a_midrule():
    rules = [_r(0.9, 100.0, x0=100, x1=400), _r(0.5, 150.0, x0=100, x1=400),
             _r(0.9, 200.0, x0=100, x1=400)]
    assert [g["kind"] for g in rank_rules(rules)] == [TOPRULE, MIDRULE, BOTTOMRULE]


def test_vertical_rules_are_not_booktabs_rules():
    r"""booktabs draws no vertical rules at all; a `v` rule is a `|` column
    separator and belongs to a different reconstruction."""
    rules = _BOOKTABS + [_r(0.4, 130.0, orient="v")]
    got = rank_rules(rules)
    vs = [g for g in got if g["orient"] == "v"]
    assert vs and all(g["kind"] == UNKNOWN for g in vs)
    assert "vertical" in vs[0]["reason"]


def test_fewer_than_two_rules_is_not_a_ranking():
    got = rank_rules([_r(0.797, 125.2)])
    assert got[0]["kind"] == UNKNOWN and "too few" in got[0]["reason"]


def test_the_measured_width_travels_with_the_name():
    """The name is derived; the measurement is the evidence for it, and both
    have to reach a reader who wants to check the call."""
    got = rank_rules(_BOOKTABS)
    assert got[0]["width_pt"] == 0.7970
    assert got[0]["weight_class"] == 1 and got[1]["weight_class"] == 0


def test_rules_are_ranked_top_to_bottom_regardless_of_input_order():
    got = rank_rules(list(reversed(_BOOKTABS)))
    assert [g["kind"] for g in got] == [TOPRULE, MIDRULE, MIDRULE, BOTTOMRULE]
