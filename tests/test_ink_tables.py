r"""Phase 3 — table structure from ink, cross-checked against MathPix.

Two producers draw tables two ways and pdfdrill sees only one of them.

CONNECTED GRID (Word, InDesign). The ruled table is ONE component whose HOLES
are its cells: Infineon p19 is 52 holes = 13 rows x 4 columns, and the grid
falls out with column widths and row heights to 0.1 pt. The alternating row
heights are the rows whose text wraps to two lines — information a cell-text
extractor discards and a round trip needs.

DISJOINT RULES (LaTeX booktabs). No frame, no holes, so the hole lattice finds
nothing at all. The discriminator is ONE number — does the largest component in
the region have holes — and 52 versus 0 is not a marginal call.

The deliverable is explicit that inkdrill's `simple_cell` lines flow through
the EXISTING `table_structure.cells_from_mathpix` unchanged. A third
`cells_from_*` would make a scoring difference indistinguishable from a format
difference, so the first test below asserts the reuse rather than trusting it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import ink_tables  # noqa: E402
from pdfdrill.ink_crosscheck import AGREE, GRID_DISAGREE, ONLY_IN_MODEL  # noqa: E402
from pdfdrill.table_structure import cells_from_mathpix  # noqa: E402


def _cell(row, col, x, y, w=10.0, h=10.0, text=""):
    return {"type": "simple_cell", "cell_row": row, "cell_column": col,
            "cell_row_span": 1, "cell_col_span": 1, "text": text,
            "region": {"top_left_x": x, "top_left_y": y,
                       "width": w, "height": h}}


def _ink_doc(lines, page=1):
    return {"source": "inkdrill", "ocr": {"units": "pt", "render_dpi": 400.0},
            "pages": [{"page": page, "page_width": 612.0, "page_height": 792.0,
                       "lines": lines}]}


def _table_line(x, y, w, h, holes=4, rows=2, cols=2):
    return {"type": "table", "text": "",
            "region": {"top_left_x": x, "top_left_y": y, "width": w, "height": h},
            "ink": {"region_id": 1, "holes": holes, "rows": rows, "columns": cols}}


# ------------------------------------------------------- no third cell reader
def test_ink_cells_go_through_the_existing_mathpix_reader_unchanged():
    """inkdrill emits the MathPix cell keys on purpose, so the same reader
    takes both. A parallel implementation is how a scoring difference becomes
    indistinguishable from a format difference."""
    cells = [_cell(0, 0, 0, 0), _cell(0, 1, 10, 0),
             _cell(1, 0, 0, 10), _cell(1, 1, 10, 10)]
    doc = _ink_doc([_table_line(0, 0, 20, 20)] + cells)
    got = ink_tables.tables_of(doc, page=1)
    expect_cells, nr, nc = cells_from_mathpix(cells)
    assert got[0]["cells"] == expect_cells
    assert (got[0]["n_rows"], got[0]["n_cols"]) == (nr, nc) == (2, 2)


def test_a_cell_outside_the_table_rectangle_belongs_to_no_table():
    """Cells are assigned to the table that CONTAINS them. Two tables on one
    page otherwise merge into one grid whose row count is the sum."""
    doc = _ink_doc([_table_line(0, 0, 20, 20),
                    _cell(0, 0, 0, 0), _cell(0, 1, 10, 0),
                    _cell(0, 0, 500, 500)])          # far away
    got = ink_tables.tables_of(doc, page=1)
    assert len(got) == 1 and len(got[0]["cells"]) == 2


# ------------------------------------------------------------- one coordinate space
def test_model_regions_are_converted_to_points_before_they_are_compared():
    """The model holds MathPix PIXELS and inkdrill declares POINTS. Comparing
    them raw gives an IoU of zero for a table both tools found, which reads as
    'only in model' — a units bug wearing the costume of a finding."""
    model = [{"page": 1, "n_rows": 2, "n_cols": 2, "cells": [],
              "region": {"top_left_x": 1000, "top_left_y": 1000,
                         "width": 500, "height": 500}}]
    got = ink_tables.model_tables_pt(model, page_px=(2000, 3000),
                                     page_pt=(600.0, 900.0))
    assert got[0]["region"] == {"top_left_x": 300.0, "top_left_y": 300.0,
                                "width": 150.0, "height": 150.0}


# ------------------------------------------------------------------ the verdicts
def test_the_same_grid_from_both_tools_agrees():
    cells = [_cell(0, 0, 0, 0), _cell(0, 1, 10, 0),
             _cell(1, 0, 0, 10), _cell(1, 1, 10, 10)]
    ink = ink_tables.tables_of(_ink_doc([_table_line(0, 0, 20, 20)] + cells), page=1)
    model = [{"n_rows": 2, "n_cols": 2, "cells": [{}] * 4,
              "region": {"top_left_x": 0, "top_left_y": 0,
                         "width": 20, "height": 20}}]
    out = ink_tables.crosscheck(model, ink)
    assert [f["verdict"] for f in out] == [AGREE]


def test_a_different_grid_over_the_same_rectangle_is_the_signal():
    """pdfplumber found the nameplate's text grid and MathPix the ruled table.
    Neither tool is wrong about what IT looks for — the ink adjudicates, and
    the disagreement is the product, so it is reported with both numbers."""
    cells = [_cell(0, 0, 0, 0), _cell(0, 1, 10, 0),
             _cell(1, 0, 0, 10), _cell(1, 1, 10, 10)]
    ink = ink_tables.tables_of(_ink_doc([_table_line(0, 0, 20, 20)] + cells), page=1)
    model = [{"n_rows": 6, "n_cols": 5, "cells": [{}] * 30,
              "region": {"top_left_x": 0, "top_left_y": 0,
                         "width": 20, "height": 20}}]
    out = ink_tables.crosscheck(model, ink)
    assert out[0]["verdict"] == GRID_DISAGREE
    assert out[0]["detail"]["n_rows"] == {"model": 6, "ink": 2}


def test_a_booktabs_page_is_reported_as_the_rule_case_not_as_a_disagreement():
    r"""A MathPix table with NO ink table anywhere on the page is the disjoint-
    rule case: no frame, no holes, so the hole lattice finds nothing. Calling
    that "only in model" would read as inkdrill contradicting MathPix, when
    inkdrill said nothing at all. The discriminator is the hole count, and 0
    holes on the page means the lattice never applied."""
    model = [{"n_rows": 5, "n_cols": 3, "cells": [{}] * 15,
              "region": {"top_left_x": 0, "top_left_y": 0,
                         "width": 20, "height": 20}}]
    out = ink_tables.crosscheck(model, ink_tables.tables_of(_ink_doc([]), page=1))
    assert out[0]["verdict"] == ONLY_IN_MODEL
    assert out[0]["no_lattice"] is True


def test_the_same_grid_with_a_different_cell_population_names_the_missing_slots():
    """Measured on Infineon p19: both tools say 13x4, but MathPix emits 44
    cells and the ink 52. The 8 MathPix omits are exactly the EMPTY slots — it
    emits a cell when there is text, while a hole is a hole either way.

    So the two are COMPLEMENTARY: MathPix supplies text for 44, the ink
    supplies the 8 empties, and a LaTeX round trip needs all 52 because an
    empty cell is still an `&`. Reporting that as "disagreement" would read as
    a defect in one tool, so the slots are named instead of counted.
    """
    model = [{"row": 0, "col": 0}, {"row": 0, "col": 1}, {"row": 1, "col": 0}]
    ink = [{"row": r, "col": c} for r in (0, 1) for c in (0, 1)]
    diff = ink_tables.slot_diff(model, ink)
    assert diff["model_missing"] == [(1, 1)]
    assert diff["ink_missing"] == []
    assert diff["same_grid_population_differs"] is True


def test_slot_diff_reports_no_difference_when_both_cover_the_same_slots():
    cells = [{"row": 0, "col": 0}, {"row": 0, "col": 1}]
    diff = ink_tables.slot_diff(cells, cells)
    assert diff["model_missing"] == [] and diff["ink_missing"] == []
    assert diff["same_grid_population_differs"] is False


def test_a_model_table_claims_the_page_level_rules_inside_it():
    r"""The join that makes Phase 4 work on a real paper.

    A booktabs page emits NO ink table, so there is nothing on the ink side to
    hang the rules on — but MathPix knows where the table is, and the rules sit
    on the page record with no owner. pdfdrill holds both, so the model's
    rectangle claims them and they are ranked against it.

    Without this, `inktables` reports `no_lattice` on exactly the pages whose
    rules Phase 4 exists to name.
    """
    model = [{"n_rows": 4, "n_cols": 2, "cells": [],
              "region": {"top_left_x": 100.0, "top_left_y": 120.0,
                         "width": 400.0, "height": 130.0}}]
    rules = [{"width_pt": 1.08, "orient": "h", "x0": 118.6, "y0": 135.0,
              "x1": 497.9, "y1": 136.1},
             {"width_pt": 0.72, "orient": "h", "x0": 118.6, "y0": 203.0,
              "x1": 497.9, "y1": 203.8},
             {"width_pt": 1.08, "orient": "h", "x0": 118.6, "y0": 241.6,
              "x1": 497.9, "y1": 242.6},
             {"width_pt": 0.72, "orient": "h", "x0": 118.6, "y0": 900.0,
              "x1": 497.9, "y1": 900.8}]          # far below: another table
    got = ink_tables.attach_rules(model, rules)
    kinds = [r["kind"] for r in got[0]["rules"]]
    assert kinds == ["toprule", "midrule", "bottomrule"]
    assert len(got[0]["rules"]) == 3, "the rule outside the rectangle is not claimed"


def test_attach_rules_leaves_a_table_with_no_rules_reporting_none():
    model = [{"n_rows": 2, "n_cols": 2, "cells": [],
              "region": {"top_left_x": 0.0, "top_left_y": 0.0,
                         "width": 10.0, "height": 10.0}}]
    got = ink_tables.attach_rules(model, [])
    assert got[0]["rules"] == []


def test_grid_metrics_reports_column_widths_and_row_heights():
    """The alternating row heights ARE the rows whose text wraps to two lines —
    discarded by a cell-text extractor and needed by a round trip."""
    cells = [{"row": 0, "col": 0, "row_span": 1, "col_span": 1,
              "region": {"top_left_x": 0, "top_left_y": 0,
                         "width": 45.0, "height": 37.8}},
             {"row": 0, "col": 1, "row_span": 1, "col_span": 1,
              "region": {"top_left_x": 45, "top_left_y": 0,
                         "width": 42.7, "height": 37.8}},
             {"row": 1, "col": 0, "row_span": 1, "col_span": 1,
              "region": {"top_left_x": 0, "top_left_y": 37.8,
                         "width": 45.0, "height": 23.8}}]
    m = ink_tables.grid_metrics(cells)
    assert m["col_widths"] == [45.0, 42.7]
    assert m["row_heights"] == [37.8, 23.8]


def test_a_spanning_cell_is_not_used_as_a_column_width():
    """A cell covering three columns would otherwise report the span as one
    column's width, and every downstream number would inherit it."""
    cells = [{"row": 0, "col": 0, "row_span": 1, "col_span": 3,
              "region": {"top_left_x": 0, "top_left_y": 0,
                         "width": 300.0, "height": 20.0}},
             {"row": 1, "col": 0, "row_span": 1, "col_span": 1,
              "region": {"top_left_x": 0, "top_left_y": 20,
                         "width": 100.0, "height": 20.0}}]
    assert ink_tables.grid_metrics(cells)["col_widths"] == [100.0]


def test_hole_count_travels_so_the_discriminator_is_visible():
    """52 versus 0 is the whole decision; it must be in the report, not
    recomputed by a reader."""
    cells = [_cell(0, 0, 0, 0), _cell(0, 1, 10, 0)]
    ink = ink_tables.tables_of(
        _ink_doc([_table_line(0, 0, 20, 20, holes=52, rows=13, cols=4)] + cells),
        page=1)
    assert ink[0]["holes"] == 52
    assert ink[0]["ink_rows"] == 13 and ink[0]["ink_columns"] == 4


# ------------------------------------------------- the per-table precondition
def test_cells_from_mathpix_cannot_tell_two_tables_apart():
    """`parent_id` is on every MathPix line and this reader does not read it.

    Measured on 2409.18839 p9: feeding both tables' children at once gives
    7x7 / 61 cells where the truth is 7x7 and 4x5, and 16 of the 45 occupied
    slots then hold two cells — one from each table, silently overwriting in
    `grid()`. Both real callers group first (`children_ids` per table;
    geometric containment), so this is a precondition rather than a live
    defect — and it is pinned here so it stays one.
    """
    a = [_cell(r, c, c * 10, r * 10) for r in range(2) for c in range(2)]
    b = [_cell(r, c, c * 10, 500 + r * 10) for r in range(2) for c in range(2)]
    _, nr_a, nc_a = cells_from_mathpix(a)
    cells_both, nr, nc = cells_from_mathpix(a + b)
    assert (nr_a, nc_a) == (2, 2)
    assert (nr, nc) == (2, 2)          # the grid does NOT grow...
    assert len(cells_both) == 8        # ...but every slot is now doubly filled
    occupied = {(c["row"], c["col"]) for c in cells_both}
    assert len(occupied) == 4 and len(cells_both) == 8


def test_the_containment_reader_keeps_two_tables_apart():
    """`tables_of` satisfies the precondition by geometry, which is why the
    same reader is safe there."""
    doc = _ink_doc([_table_line(0, 0, 20, 20), _table_line(0, 500, 20, 520),
                    _cell(0, 0, 0, 0), _cell(0, 1, 10, 0),
                    _cell(0, 0, 0, 500)])
    got = ink_tables.tables_of(doc, page=1)
    assert [len(t["cells"]) for t in got] == [2, 1]
