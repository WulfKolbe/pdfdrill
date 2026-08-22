"""105a — reject a numeric table whose rows are not the same width."""
import json

from pdfdrill.changereq import check_uniform_widths, load, numeric_rows


def test_uniform_space_separated_run_passes():
    ok, d = check_uniform_widths(r"a &= 1\ 0\ 1 \\ b &= 0\ 1\ 1")
    assert ok and "width 3" in d


def test_short_row_is_rejected_and_named():
    ok, d = check_uniform_widths(r"a &= 1\ 0\ 1 \\ b &= 0\ 1")
    assert not ok and "row(s) [2]" in d


def test_uniform_array_cells_pass():
    ok, _ = check_uniform_widths(r"x & 1 & 2 & 3 \\ y & 4 & 5 & 6")
    assert ok


def test_a_proposal_with_no_table_passes_untouched():
    """Most proposals are not tables. A validator that fires on prose would
    reject the majority of legitimate change requests."""
    ok, d = check_uniform_widths(r"E = mc^{2}")
    assert ok and d == "no numeric table"
    assert numeric_rows(r"\alpha + \beta = \gamma") == []


def test_isolated_number_in_prose_is_not_a_table():
    """`a & 2 & b` inside a two-column layout is not a numeric table; counting
    it as one would reject rows that never claimed uniformity."""
    assert numeric_rows(r"\text{see} & 2 & \text{below and further along}") == []


def test_loader_reports_problems_per_proposal(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps([
        {"target": "A", "field": "latex", "proposed": r"a &= 1\ 1 \\ b &= 1\ 1"},
        {"target": "B", "field": "latex", "proposed": r"a &= 1\ 1 \\ b &= 1"},
        {"target": "C", "field": "latex"},
    ]))
    got = load(p)
    assert got[0].ok
    assert not got[1].ok and "non-uniform" in got[1].problems[0]
    assert not got[2].ok and "missing required" in got[2].problems[0]
