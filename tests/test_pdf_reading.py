"""
Tests for the file-based pdf-reading primitives (pdfdrill.pdf_reading) —
parity with the Claude.ai pdf-reading skill. Pure helpers are tested directly;
the tool-backed paths use a minimal pypdf-built PDF and guard on tool presence.
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import pdf_reading as pr


# ---- pure helpers ---------------------------------------------------------

def test_parse_pages():
    assert pr.parse_pages(None) is None
    assert pr.parse_pages("all") is None
    assert pr.parse_pages("3") == [3]
    assert pr.parse_pages("2-5") == [2, 3, 4, 5]
    assert pr.parse_pages("5-2") == [2, 3, 4, 5]        # order-insensitive
    assert pr.parse_pages("1,3,5-7") == [1, 3, 5, 6, 7]
    assert pr.parse_pages("1,3,99", total=10) == [1, 3]  # clamp to total
    assert pr.parse_pages("0") is None                   # invalid → None


def test_parse_pdfdetach_list():
    txt = "2 embedded files\n1: report.xlsx\n2: data file.csv\n"
    items = pr.parse_pdfdetach_list(txt)
    assert items == [{"index": 1, "name": "report.xlsx"},
                     {"index": 2, "name": "data file.csv"}]
    assert pr.parse_pdfdetach_list("0 embedded files\n") == []


def test_filter_real_images():
    with tempfile.TemporaryDirectory() as d:
        big = Path(d) / "img-000.png"; big.write_bytes(b"x" * 5000)
        tiny = Path(d) / "img-001.png"; tiny.write_bytes(b"x" * 10)
        kept, dropped = pr.filter_real_images([big, tiny])
        assert kept == [big] and dropped == 1


def test_tables_to_markdown():
    tables = [{"page": 2, "index": 0, "n_rows": 2, "n_cols": 2,
               "rows": [["Pos", "Preis"], ["1", "9,99"]]}]
    md = pr.tables_to_markdown(tables)
    assert "| Pos | Preis |" in md and "| --- | --- |" in md
    assert "| 1 | 9,99 |" in md and "Table p2.0" in md


# ---- tool-backed paths on a minimal pypdf-built PDF -----------------------

def _blank_pdf(path: Path):
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(width=300, height=300)
    w.add_blank_page(width=300, height=300)
    with open(path, "wb") as f:
        w.write(f)


def test_read_form_fields_no_form():
    """A non-form PDF → ([], None): graceful, not an error."""
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"; _blank_pdf(pdf)
        fields, err = pr.read_form_fields(pdf)
        assert fields == [] and err is None


def test_extract_tables_no_tables():
    """pdfplumber on a blank PDF → ([], None)."""
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"; _blank_pdf(pdf)
        tables, err = pr.extract_tables(pdf)
        assert tables == [] and err is None


_SPAN_TABLE_TEX = r"""
\documentclass{article}
\pagestyle{empty}
\usepackage{multirow}
\begin{document}
\begin{tabular}{|l|l|l|}
\hline
\multicolumn{2}{|l|}{Group} & C \\ \hline
\multirow{2}{*}{A} & b1 & c1 \\ \cline{2-3}
                   & b2 & c2 \\ \hline
\end{tabular}
\end{document}
"""


def test_extract_tables_span_aware_cells():
    """A \\multicolumn/\\multirow tabular → span-aware cells + named columns."""
    if shutil.which("pdflatex") is None:
        print("SKIP span tables (no pdflatex)"); return
    import subprocess
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "t.tex").write_text(_SPAN_TABLE_TEX)
        subprocess.run(["pdflatex", "-interaction=nonstopmode", "t.tex"],
                       cwd=d, capture_output=True, timeout=120)
        pdf = Path(d) / "t.pdf"
        assert pdf.exists()
        tables, err = pr.extract_tables(pdf)
        assert err is None and len(tables) == 1
        t = tables[0]
        assert t["rows"]                      # naive matrix kept (compat)
        by = {(c["row"], c["col"]): c for c in t["cells"]}
        assert by[(0, 0)]["col_span"] == 2    # the \multicolumn header
        assert by[(0, 0)]["text"] == "Group"
        assert by[(1, 0)]["row_span"] == 2    # the \multirow label
        assert t["columns"]                   # findable column names
        assert t["header_rows"] >= 1


def test_tables_to_html_spans():
    tables = [{"page": 3, "index": 0, "n_rows": 2, "n_cols": 2,
               "rows": [["H", ""], ["a", "b"]],
               "cells": [
                   {"row": 0, "col": 0, "row_span": 1, "col_span": 2, "text": "H"},
                   {"row": 1, "col": 0, "row_span": 1, "col_span": 1, "text": "a"},
                   {"row": 1, "col": 1, "row_span": 1, "col_span": 1, "text": "b"}],
               "columns": ["H", "H"], "header_rows": 1}]
    html = pr.tables_to_html(tables)
    assert 'colspan="2"' in html and "<caption>" in html
    assert "p. 3" in html
    # a table without cells (old shape) degrades to the naive grid
    html2 = pr.tables_to_html([{"page": 1, "index": 0, "n_rows": 1, "n_cols": 2,
                                "rows": [["x", "y"]]}])
    assert "<td>x</td>" in html2 or "<th>x</th>" in html2


def test_rasterize_roundtrip():
    if shutil.which("pdftoppm") is None:
        print("SKIP rasterize (no pdftoppm)"); return
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"; _blank_pdf(pdf)
        imgs = pr.rasterize(pdf, Path(d) / "out", pages=[2], dpi=72)
        assert len(imgs) == 1 and imgs[0].suffix == ".png" and imgs[0].exists()


def test_list_attachments_none():
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"; _blank_pdf(pdf)
        items, src = pr.list_attachments(pdf)
        assert items == [] and src in ("pdfdetach", "pypdf", "none")


if __name__ == "__main__":
    test_parse_pages(); print("PASS parse_pages")
    test_parse_pdfdetach_list(); print("PASS parse_pdfdetach_list")
    test_filter_real_images(); print("PASS filter_real_images")
    test_tables_to_markdown(); print("PASS tables_to_markdown")
    test_read_form_fields_no_form(); print("PASS form_fields_no_form")
    test_extract_tables_no_tables(); print("PASS tables_no_tables")
    test_extract_tables_span_aware_cells(); print("PASS tables_span_aware")
    test_tables_to_html_spans(); print("PASS tables_to_html")
    test_rasterize_roundtrip(); print("PASS rasterize_roundtrip")
    test_list_attachments_none(); print("PASS attachments_none")
    print("\nAll tests passed.")
