"""
Span-aware table structure (src/pdfdrill/table_structure.py): cells carry
{row, col, row_span, col_span, text} — a value lives ONCE at its anchor (top-
left) slot and covers a range, instead of a naive matrix with '' placeholders.
Pure tests: synthetic pdfplumber-like rects, MathPix-like cell payloads, the
column-header flattening, the HTML QA projection, grid round-trip, validation.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import table_structure as ts


# ---------------------------------------------------------------- fakes
class FakePlumberTable:
    """Duck-type of pdfplumber.table.Table: .cells rects + .extract() matrix.

    Layout (3 cols x 3 rows, edges x=0,10,20,30 / y=0,10,20,30):
      row 0:  [  Group (colspan 2)  ][ C ]
      row 1:  [ A(rowspan 2) ][ b1  ][ c1 ]
      row 2:  [   (covered)  ][ b2  ][ c2 ]
    """
    cells = [
        (0, 0, 20, 10),    # Group: cols 0-1, row 0
        (20, 0, 30, 10),   # C
        (0, 10, 10, 30),   # A: rows 1-2
        (10, 10, 20, 20), (20, 10, 30, 20),   # b1 c1
        (10, 20, 20, 30), (20, 20, 30, 30),   # b2 c2
    ]

    def extract(self):
        return [["Group", None, "C"],
                ["A", "b1", "c1"],
                [None, "b2", "c2"]]


def _mathpix_children():
    return [
        {"type": "table_spanning_cell", "text": "Group",
         "cell_row": 0, "cell_column": 0, "cell_row_span": 1, "cell_col_span": 2,
         "region": {"top_left_x": 0, "top_left_y": 0, "width": 20, "height": 10}},
        {"type": "simple_cell", "text": "C",
         "cell_row": 0, "cell_column": 2, "cell_row_span": 1, "cell_col_span": 1},
        {"type": "table_row", "text": ""},          # rows are skipped
        {"type": "complex_cell", "text": "A",
         "cell_row": 1, "cell_column": 0, "cell_row_span": 2, "cell_col_span": 1},
        {"type": "simple_cell", "text": "b1", "cell_row": 1, "cell_column": 1,
         "cell_row_span": 1, "cell_col_span": 1},
        {"type": "simple_cell", "text": "c1", "cell_row": 1, "cell_column": 2,
         "cell_row_span": 1, "cell_col_span": 1},
        {"type": "simple_cell", "text": "b2", "cell_row": 2, "cell_column": 1,
         "cell_row_span": 1, "cell_col_span": 1},
        {"type": "simple_cell", "text": "c2", "cell_row": 2, "cell_column": 2,
         "cell_row_span": 1, "cell_col_span": 1},
    ]


def _by_pos(cells):
    return {(c["row"], c["col"]): c for c in cells}


# ---------------------------------------------------------------- plumber
def test_cells_from_plumber_reconstructs_spans():
    cells, n_rows, n_cols = ts.cells_from_plumber(FakePlumberTable())
    assert (n_rows, n_cols) == (3, 3)
    by = _by_pos(cells)
    assert by[(0, 0)]["text"] == "Group" and by[(0, 0)]["col_span"] == 2
    assert by[(1, 0)]["text"] == "A" and by[(1, 0)]["row_span"] == 2
    assert by[(1, 1)]["text"] == "b1" and by[(1, 1)]["col_span"] == 1
    # covered slots are NOT stored as cells
    assert (0, 1) not in by and (2, 0) not in by
    assert len(cells) == 7


# ---------------------------------------------------------------- mathpix
def test_cells_from_mathpix_keeps_spanning_cells():
    cells, n_rows, n_cols = ts.cells_from_mathpix(_mathpix_children())
    assert (n_rows, n_cols) == (3, 3)
    by = _by_pos(cells)
    assert by[(0, 0)]["col_span"] == 2           # the table_spanning_cell
    assert by[(1, 0)]["row_span"] == 2
    assert by[(0, 0)]["region"]["width"] == 20   # region preserved when present
    assert len(cells) == 7                       # table_row skipped


# ---------------------------------------------------------------- headers
def test_column_headers_flatten_spans_and_linefeeds():
    # 2 header rows: [ Biomedical (colspan 2) ][ Exec\nTimes ] / [ P ][ R ][(covered)]
    cells = [
        {"row": 0, "col": 0, "row_span": 1, "col_span": 2, "text": "Biomedical\nData"},
        {"row": 0, "col": 2, "row_span": 2, "col_span": 1, "text": "Exec\nTimes"},
        {"row": 1, "col": 0, "row_span": 1, "col_span": 1, "text": "P"},
        {"row": 1, "col": 1, "row_span": 1, "col_span": 1, "text": "Repre-\nsentation"},
        {"row": 2, "col": 0, "row_span": 1, "col_span": 1, "text": "1"},
        {"row": 2, "col": 1, "row_span": 1, "col_span": 1, "text": "2"},
        {"row": 2, "col": 2, "row_span": 1, "col_span": 1, "text": "3"},
    ]
    columns, header_rows = ts.column_headers(cells, 3)
    assert header_rows == 2
    assert columns[0] == "Biomedical Data P"          # linefeed -> space, flattened
    assert columns[1] == "Biomedical Data Repre-sentation"   # soft-break joined
    assert columns[2] == "Exec Times"                 # rowspan'd header appears ONCE


def test_column_headers_simple_table_is_row0():
    cells = [
        {"row": 0, "col": 0, "row_span": 1, "col_span": 1, "text": "Name"},
        {"row": 0, "col": 1, "row_span": 1, "col_span": 1, "text": "Value"},
        {"row": 1, "col": 0, "row_span": 1, "col_span": 1, "text": "x"},
        {"row": 1, "col": 1, "row_span": 1, "col_span": 1, "text": "1"},
    ]
    columns, header_rows = ts.column_headers(cells, 2)
    assert header_rows == 1 and columns == ["Name", "Value"]


# ---------------------------------------------------------------- grid / html
def test_grid_round_trip_matches_naive_matrix():
    cells, n_rows, n_cols = ts.cells_from_plumber(FakePlumberTable())
    g = ts.grid(cells, n_rows, n_cols)
    assert g[0] == ["Group", "", "C"]
    assert g[1] == ["A", "b1", "c1"]
    assert g[2] == ["", "b2", "c2"]


def test_to_html_emits_spans_and_skips_covered_slots():
    cells, n_rows, n_cols = ts.cells_from_plumber(FakePlumberTable())
    columns, header_rows = ts.column_headers(cells, n_cols)
    html = ts.to_html(cells, n_rows, n_cols, caption="p. 1", columns=columns,
                      header_rows=header_rows)
    assert 'colspan="2"' in html and 'rowspan="2"' in html
    import re
    assert len(re.findall(r"<t[dh][ >]", html)) == 7    # one element per CELL
    assert "<caption>" in html and "p. 1" in html
    assert "<thead>" in html and "<th" in html          # header rows as th
    assert 'title="' in html                            # flattened name tooltip


def test_to_html_escapes():
    cells = [{"row": 0, "col": 0, "row_span": 1, "col_span": 1, "text": "a<b&c"},
             {"row": 1, "col": 0, "row_span": 1, "col_span": 1, "text": "x"}]
    html = ts.to_html(cells, 2, 1)
    assert "a&lt;b&amp;c" in html and "<b&c" not in html


# ---------------------------------------------------------------- validation
def test_check_catches_overlap_and_overflow():
    ok = ts.check([{"row": 0, "col": 0, "row_span": 1, "col_span": 1, "text": "a"}], 1, 1)
    assert ok == []
    bad = ts.check([
        {"row": 0, "col": 0, "row_span": 1, "col_span": 2, "text": "a"},
        {"row": 0, "col": 1, "row_span": 1, "col_span": 1, "text": "b"},   # overlap
        {"row": 0, "col": 5, "row_span": 1, "col_span": 1, "text": "c"},   # overflow
    ], 1, 2)
    assert any("overlap" in w for w in bad)
    assert any("grid" in w for w in bad)


# ---------------------------------------------------------------- wiring
def test_table_processor_stores_span_aware_cells():
    """The MathPix route: TableProcessor must keep cell coords (incl. the
    previously-dropped table_spanning_cell) and store props['cells']."""
    from docmodel.core import Document
    from docmodel.modules.page import ingest_lines_json
    from docmodel.modules.table import TableProcessor
    from docmodel.base_module import ModuleConfig

    lines = [{"id": "t1", "type": "table", "text": "",
              "children_ids": ["c1", "c2", "c3", "c4"]}]
    for ch in _mathpix_children():
        if ch["type"] == "table_row":
            continue
    cid = 0
    for ch in _mathpix_children():
        cid += 1
        ch = dict(ch); ch["id"] = f"c{cid}"
        lines.append(ch)
    lines[0]["children_ids"] = [f"c{i}" for i in range(1, cid + 1)]

    doc = Document()
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "i", "lines": lines}]})
    proc = TableProcessor(ModuleConfig(title="T", classname="TableProcessor",
                                       proc_order=4), "T")
    proc.process_document(doc)
    tables = doc.objects_of_type("Table")
    assert len(tables) == 1
    p = tables[0].props
    assert p["n_rows"] == 3 and p["n_cols"] == 3
    by = _by_pos(p["cells"])
    assert by[(0, 0)]["col_span"] == 2          # table_spanning_cell KEPT
    assert by[(1, 0)]["row_span"] == 2
    assert p["columns"][2].startswith("C")      # findable column name
    assert p["header_rows"] >= 1


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
