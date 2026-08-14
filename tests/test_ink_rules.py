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

from pdfdrill.ink_rules import BOTTOMRULE, MIDRULE, TOPRULE, UNKNOWN, rank_rules  # noqa: E402


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
    """The absolute width runs ~12% high and the ratio wanders between 1.33 and
    1.67 under pixel quantisation. Scaling every rule by 1.12 must not change a
    single name — if it does, the classifier is reading the wrong signal."""
    inflated = [dict(r, width_pt=r["width_pt"] * 1.12) for r in _BOOKTABS]
    assert [g["kind"] for g in rank_rules(inflated)] == \
           [g["kind"] for g in rank_rules(_BOOKTABS)]


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
