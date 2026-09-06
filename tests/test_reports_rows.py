"""The row model is source-independent: no I/O, frozen, one class per kind."""
import dataclasses

import pytest

from pdfdrill.reports import KINDS, COLUMNS
from pdfdrill.reports.rows import (EvidenceRow, EquationRow, FormulaRow,
                                   TableRow, ImageRow, HostLine, row_kind)


def test_the_six_columns_are_fixed():
    assert COLUMNS == ("Identifier", "Page", "Conf.", "LaTeX source",
                       "Rendered", "Image")
    assert KINDS == ("equation", "formula", "table", "image")


def test_rows_are_frozen():
    r = EquationRow(identifier="D_EQ0001", page="3", latex="x", eqnum="(1)")
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.latex = "y"


def test_a_formula_without_a_host_line_shows_dashes():
    r = FormulaRow(identifier="D_FO0001", latex="P")
    assert r.page is None and r.confidence is None and r.crop is None
    assert r.host_line is None
    assert r.shown_page == "---"
    assert r.shown_confidence is None


def test_a_formula_with_a_host_line_shows_the_lines_values():
    h = HostLine(page=4, line_type="text", confidence=0.987,
                 region={"top_left_x": 1, "top_left_y": 2,
                         "width": 30, "height": 4})
    r = FormulaRow(identifier="D_FO0002", latex="P", host_line=h)
    assert r.shown_page == "4"
    assert r.shown_confidence == 0.987


def test_an_equation_row_carries_its_ink_code():
    r = EquationRow(identifier="D_EQ0002", page="1", latex="x",
                    confidence=0.5, ink={"flag": "weak", "code": "W|+1"})
    assert r.ink_code == "W|+1"
    assert EquationRow(identifier="D_EQ0003", latex="x").ink_code == ""


def test_row_kind_names_the_kind():
    assert row_kind(EquationRow(identifier="a", latex="")) == "equation"
    assert row_kind(FormulaRow(identifier="a", latex="")) == "formula"
    assert row_kind(TableRow(identifier="a", latex="")) == "table"
    assert row_kind(ImageRow(identifier="a", latex="")) == "image"
