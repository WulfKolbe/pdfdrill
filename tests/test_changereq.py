"""105a — reject a numeric table whose rows are not the same width."""
import json

from pdfdrill.changereq import (check_uniform_widths, confusable_cells,
                                load, numeric_rows, numeric_tables)


def test_uniform_space_separated_run_passes():
    ok, d = check_uniform_widths(r"a &= 1\ 0\ 1 \\ b &= 0\ 1\ 1")
    assert ok and "2x3" in d


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


# --------------------------------------------------- 187: the parser fix ---

_EMBEDDED_4x4 = (r"\left[\eta_{a b}\right] \equiv\left(\begin{array}{cccc} "
                 r"0 & 1 & 0 & 0 \\ 1 & 0 & 0 & 0 \\ 0 & 0 & 0 & -1 \\ "
                 r"0 & 0 & -1 & 0 \end{array}\right) .")


def test_embedded_array_is_not_miscounted():
    """The first segment used to carry the surrounding LaTeX in its first
    cell, so a plain 4x4 reported [[3],[4],[4],[3]] and was flagged."""
    assert numeric_tables(_EMBEDDED_4x4) == [[4, 4, 4, 4]]
    ok, d = check_uniform_widths(_EMBEDDED_4x4)
    assert ok, d


def test_two_matrices_of_different_widths_are_two_tables():
    lx = (r"A=\left(\begin{array}{lll} 3 & 3 & 1 \\ 2 & 0 & 4 \end{array}\right) "
          r"\quad B=\left(\begin{array}{lll} 2 & 5 & 6 \\ 1 & 1 & 1 \end{array}\right)")
    assert numeric_tables(lx) == [[3, 3], [3, 3]]
    assert check_uniform_widths(lx)[0]


def test_a_genuinely_ragged_table_still_fails():
    ok, d = check_uniform_widths(r"\begin{array}{lll} 1 & 2 & 3 \\ 4 & 5 \end{array}")
    assert not ok and "non-uniform" in d


def test_one_ragged_table_beside_a_clean_one_still_fails():
    lx = (r"\begin{array}{ll} 1 & 2 \\ 3 & 4 \end{array}\quad"
          r"\begin{array}{lll} 1 & 2 & 3 \\ 4 & 5 \end{array}")
    ok, d = check_uniform_widths(lx)
    assert not ok and "table 2" in d


def test_nested_array_is_one_table_not_two_torn_halves():
    lx = (r"\begin{array}{cc} \begin{array}{cc} 1 & 2 \\ 3 & 4 \end{array} & 0 \\ "
          r"0 & 1 \end{array}")
    numeric_tables(lx)          # must not raise, and must not tear the body


# ------------------------------------- the detection the fix would have lost ---

def test_lone_letter_in_a_numeric_table_is_caught():
    """An incidence matrix reading `0 & 0 & 1 & l & 0 & 0`. The OLD width
    check caught this BY ACCIDENT, via a miscount. Parsing properly makes the
    row six wide and uniform, so the real signal is named and kept instead."""
    lx = (r"\left(\begin{array}{rrrrrr} 1 & 1 & 0 & 0 & 0 & 0 \\ "
          r"0 & 0 & 1 & l & 0 & 0 \\ 0 & 0 & -1 & 0 & 1 & -1 \\ "
          r"-1 & -1 & 0 & 0 & -1 & 1 \end{array}\right) ;")
    assert check_uniform_widths(lx)[0]          # widths are fine
    hits = confusable_cells(lx)
    assert len(hits) == 1
    assert hits[0]["cell"] == "l" and hits[0]["likely"] == "1"
    assert (hits[0]["row"], hits[0]["col"]) == (2, 4)


def test_symbolic_matrix_does_not_trip_the_letter_check():
    """A matrix of a, b, c, d is ordinary mathematics."""
    assert confusable_cells(r"\begin{array}{cc} a & b \\ c & d \end{array}") == []
    assert confusable_cells(r"\begin{array}{cc} \lambda & 0 \\ 0 & \mu \end{array}") == []


def test_clean_numeric_matrix_does_not_trip_it():
    assert confusable_cells(r"\begin{array}{cc} 1 & 0 \\ 0 & 1 \end{array}") == []


def test_nested_array_rows_do_not_leak_into_the_parent():
    """An outer {c} column holding an inner {ccc} matrix reported widths
    {3: 6, 1: 2}: the inner table's own \\\\ split the OUTER's rows."""
    lx = (r"\left(\begin{array}{c} \left(\begin{array}{ccc} 1 & 2 & 3 \\ "
          r"4 & 5 & 6 \end{array}\right) \\ 0 \end{array}\right)")
    assert check_uniform_widths(lx)[0]


def test_column_vector_beside_a_matrix_passes():
    lx = (r"\nabla f=\left[\begin{array}{c} 2x-y \\ -x+2y \end{array}\right],"
          r"\quad H=\left[\begin{array}{cc} 2 & -1 \\ -1 & 2 \end{array}\right]")
    assert check_uniform_widths(lx)[0]


def test_imaginary_unit_is_not_a_misread_digit():
    """`i` and `I` were in the first confusable set, and it fired on a complex
    matrix: 0 & -i & i & 0 is mathematics, not OCR damage."""
    assert confusable_cells(
        r"\begin{array}{crcr} 0 & 1 & 1 & 0 \\ 0 & -i & i & 0 \\ "
        r"1 & 0 & 0 & -1 \\ 1 & 0 & 0 & 1 \end{array}") == []


def test_identity_matrix_letter_is_not_a_misread_digit():
    assert confusable_cells(
        r"\begin{array}{cc} I & 0 \\ 0 & I \end{array}") == []
