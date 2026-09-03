"""585 — the measure build is the full listing, and publishready checks coverage.

557 made both phases build the same shape so an ink measured against a
276-page listing could not be attributed to a 19-page findings report. Right
about the attribution, wrong about the direction: the findings shape SELECTS
its rows from the ink, so a row the ink never mentioned cannot be flagged,
cannot appear in the report, and cannot be measured next time either.

Stage C measured the ratchet: of the five documents whose measurement
completed, five lost their flagged set (cardona 110->1 with the ink falling
1012->2, voloshin 24->0, penev_A 33->0, 2501.06662 14->1, 0707.4470 13->0).
The other sixteen kept their numbers only because their measurement failed.
"""
import json

from pdfdrill import commands as C
from pdfdrill import report_tex as rt


def test_the_measure_phase_constants_are_the_full_listing():
    assert C.MEASURE_FORMULA_RULE == "all"
    assert C.MEASURE_FINDINGS is False
    # 593 — 0, not None. `pages=None` used to become PAGES_DEFAULT (10) at the
    # build_report call, so the "unbounded" measure build 585 thought it had
    # built was in fact ten pages. 0 is what pagesel_line reads as every page.
    assert C.MEASURE_PAGES_BOUND == 0, "phase 1 must not be page-bounded"


def test_step_2_builds_the_full_listing_regardless_of_profile():
    import inspect
    src = inspect.getsource(C.cmd_inkreport)
    i = src.index("2 — the MEASURE build")
    j = src.index("2b —", i)
    call = src[i:j]
    assert "formulas=MEASURE_FORMULA_RULE" in call
    assert "findings=MEASURE_FINDINGS" in call
    assert "pages=MEASURE_PAGES_BOUND" in call
    assert "legend=False" in call and "ink_bullets=False" in call


def _doc(tmp_path, ink_ids, shown_ids):
    (tmp_path / "report.ink.json").write_text(json.dumps(
        {"rows": [{"id": i} for i in ink_ids],
         "measured_against": {"sha256": "M"}}))
    (tmp_path / "report.tables.json").write_text(json.dumps(
        {"bibkey": "X", "tables": [{"caption": "Flagged, not acted on",
                                    "identifiers": shown_ids}]}))
    return tmp_path


def test_coverage_counts_the_published_rows_inside_the_measured_set(tmp_path):
    d = _doc(tmp_path, ["A", "B", "C"], ["A", "B"])
    c = rt.findings_covered_by_ink(d)
    assert c == {"measured": 3, "shown": 2, "covered": 2, "missing": []}


def test_a_published_row_the_ink_never_saw_is_named(tmp_path):
    d = _doc(tmp_path, ["A"], ["A", "B"])
    c = rt.findings_covered_by_ink(d)
    assert c["missing"] == ["B"] and c["covered"] == 1


def test_a_corrected_pair_is_one_region_not_three(tmp_path):
    d = _doc(tmp_path, ["A"], ["A (was)", "A (now)", "A (basis)"])
    c = rt.findings_covered_by_ink(d)
    assert c["shown"] == 1 and c["missing"] == []


def test_publishready_no_longer_requires_the_two_builds_to_match_shape(tmp_path):
    """The whole point of 585: they differ by design now."""
    import inspect
    src = inspect.getsource(rt.ink_describes_published)
    assert "different SHAPES" not in src
    assert "a different set of rows, not a legend" not in src
    assert "findings_covered_by_ink" in src
