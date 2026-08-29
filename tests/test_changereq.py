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


from pdfdrill import changereq as cr  # noqa: E402

# --- 307: the DECLARED column count ----------------------------------------

def test_colspec_counts_only_columns():
    r"""`|` decorates, `p{2cm}` occupies one and swallows a brace group that
    would otherwise count as more columns, `*{4}{c}` repeats."""
    assert cr.parse_colspec("c|c|c|c|c|c|c") == 7
    assert cr.parse_colspec("|l|p{2cm}|r|") == 3
    assert cr.parse_colspec("*{4}{c}|l") == 5
    assert cr.parse_colspec(r">{\bfseries}c@{\quad}c") == 2
    assert cr.parse_colspec("") == 0


def test_declared_width_catches_the_short_row():
    r"""\begin{array}{c|c|c|c|c|c|c} declares seven; the last row has five."""
    eq = (r"\begin{array}{c|c|c|c|c|c|c} 1&2&3&4&5&6&7 \\ \hline "
          r"a&b&c&d&e \end{array}")
    ok, detail = cr.check_declared_widths(eq)
    assert not ok
    assert "declares 7" in detail and "row 2 has 5" in detail


def test_declared_catches_what_uniformity_cannot():
    """Three independent blind spots of the numeric-uniformity rule."""
    # 1. every row short by the same amount: uniform, and wrong
    u = r"\begin{array}{cccc} 1&2&3 \\ 4&5&6 \\ 7&8&9 \end{array}"
    assert cr.check_uniform_widths(u)[0] is True
    assert cr.check_declared_widths(u)[0] is False
    # 2. a symbolic table is never examined by the numeric rule
    s = (r"\begin{array}{ccc} \alpha & \beta \\ "
         r"\gamma & \delta & \epsilon \end{array}")
    assert cr.check_uniform_widths(s)[0] is True
    assert cr.check_declared_widths(s)[0] is False
    # 3. one row gives uniformity no opinion at all
    one = r"\begin{array}{cccc} 1&2 \end{array}"
    assert cr.check_uniform_widths(one)[0] is True
    assert cr.check_declared_widths(one)[0] is False


def test_multicolumn_spans_and_rules_are_not_rows():
    r"""\multicolumn{3} occupies three columns, and \hline is not a row."""
    m = (r"\begin{tabular}{|c|c|c|} \hline \multicolumn{3}{c}{head} \\ "
         r"\hline a&b&c \\ \hline \end{tabular}")
    assert cr.check_declared_widths(m)[0] is True


def test_correct_tables_stay_silent():
    assert cr.check_declared_widths(r"\begin{array}{cc} 1&2 \\ 3&4 \end{array}")[0]
    # matrix/cases declare nothing, so there is nothing to check against
    assert cr.check_declared_widths(
        r"\begin{matrix} 1&2 \\ 3&4&5 \end{matrix}")[0] is True
    assert cr.check_declared_widths("no table here")[0] is True


def test_nested_array_is_one_cell_to_its_parent():
    r"""An inner array's own `\\` must not split the OUTER table's rows."""
    n = (r"\begin{array}{cc} "
         r"\begin{array}{ccc} 1&2&3 \\ 4&5&6 \end{array} & x \\ y & z"
         r" \end{array}")
    assert cr.check_declared_widths(n)[0] is True
