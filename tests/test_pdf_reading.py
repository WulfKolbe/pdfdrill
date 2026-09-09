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


def test_table_quality_filters():
    """Artifact/junk gates for the keyless route: an all-empty lattice grid is
    a figure frame, not a table; a text-strategy fallback table must look like
    a real table (>=3x3, mostly filled) so prose never becomes a 70x1 'table'."""
    empty = {"n_rows": 4, "n_cols": 4, "cells": [
        {"row": r, "col": c, "row_span": 1, "col_span": 1, "text": ""}
        for r in range(4) for c in range(4)]}
    real = {"n_rows": 3, "n_cols": 3, "cells": [
        {"row": r, "col": c, "row_span": 1, "col_span": 1, "text": f"v{r}{c}"}
        for r in range(3) for c in range(3)]}
    assert not pr.table_has_text(empty)
    assert pr.table_has_text(real)
    # a frame with ONE stray label is still a figure artifact, not a table
    one_label = {"n_rows": 2, "n_cols": 2, "cells": [
        {"row": 0, "col": 0, "row_span": 1, "col_span": 1, "text": "Mathematical"},
        {"row": 1, "col": 0, "row_span": 1, "col_span": 1, "text": ""}]}
    assert not pr.table_has_text(one_label)
    # pdfplumber collapses spaces: "Table2." must still gate the fallback
    assert pr._TABLE_CAPTION.search("Table2. DetailedPerformanceofVLMs")
    assert pr._TABLE_CAPTION.search("Table 12: results")
    assert not pr._TABLE_CAPTION.search("the table below shows")
    # fallback plausibility: shape + fill ratio
    assert pr.plausible_text_table(real)
    one_col = {"n_rows": 70, "n_cols": 1, "cells": [
        {"row": r, "col": 0, "row_span": 1, "col_span": 1, "text": "prose"}
        for r in range(70)]}
    assert not pr.plausible_text_table(one_col)          # p5 junk shape
    sparse = {"n_rows": 5, "n_cols": 5, "cells": [
        {"row": 0, "col": 0, "row_span": 1, "col_span": 1, "text": "x"}]}
    assert not pr.plausible_text_table(sparse)           # mostly holes


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
    if not any(shutil.which(t) for t in ("gs", "gswin64c", "gswin32c")):
        print("SKIP rasterize (no ghostscript)"); return
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"; _blank_pdf(pdf)
        imgs = pr.rasterize(pdf, Path(d) / "out", pages=[2], dpi=72)
        assert len(imgs) == 1 and imgs[0].suffix == ".png" and imgs[0].exists()


def test_rasterize_uses_ghostscript_at_400_floor():
    """Every rasterize task must use Ghostscript at >= 400 DPI (measured-best
    OCR/vision fidelity) — even when a caller passes a lower dpi (floored)."""
    captured = []

    def fake_run(cmd, *a, **k):
        captured.append(cmd)
        for c in cmd:
            if isinstance(c, str) and c.startswith("-sOutputFile="):
                of = c.split("=", 1)[1]
                # honour cwd like a real subprocess: the output template is
                # RELATIVE so gs never parses a caller path with `%` in it.
                Path(k.get("cwd") or ".", of.replace("%04d", "0001")).write_bytes(b"\x89PNG")
        class _R:
            returncode = 0; stdout = b""; stderr = b""
        return _R()

    owhich, orun = pr.shutil.which, pr.subprocess.run
    try:
        pr.shutil.which = lambda t: "/usr/bin/gs" if t == "gs" else None
        pr.subprocess.run = fake_run
        with tempfile.TemporaryDirectory() as d:
            imgs = pr.rasterize(Path(d) / "x.pdf", Path(d) / "out",
                                pages=[1], dpi=150)          # 150 → must floor to 400
        cmd = captured[0]
        assert cmd[0] == "/usr/bin/gs"
        assert "-r400" in cmd                                # floored
        assert "-sDEVICE=png16m" in cmd
        # Actual-page naming is a guarantee about the FILES, not about the gs
        # argv: pages are rendered in parallel SHARDS into a temp directory and
        # moved to their true page numbers afterwards, because gs restarts its
        # `%d` counter at 1 per invocation and parallel shards sharing one
        # output template overwrite each other.
        assert imgs and imgs[0].name == "page-0001.png"
    finally:
        pr.shutil.which, pr.subprocess.run = owhich, orun


# ---- 654: MathPix pixel -> raster pixel, and the -dUseCropBox raster ------

def _pdf_with_cropbox(path: Path, *, mediabox=(493, 700),
                      cropbox=(13.68, 30.24, 452.68, 692.80)):
    """A two-page PDF: page 1 has an inset CropBox (gilmore-lie-groups p15's
    own numbers), page 2 has none (CropBox == MediaBox)."""
    from pypdf import PdfWriter
    from pypdf.generic import RectangleObject
    w = PdfWriter()
    p1 = w.add_blank_page(width=mediabox[0], height=mediabox[1])
    p1.cropbox = RectangleObject(cropbox)
    w.add_blank_page(width=mediabox[0], height=mediabox[1])   # equal boxes
    with open(path, "wb") as f:
        w.write(f)


def test_mathpix_to_raster_scales_axes_independently():
    # raster 2439 x 3681 (gilmore p15's own -dUseCropBox render at 400 dpi),
    # MathPix page 1525 x 2301 (its lines.json) — the FO0006 region.
    box = pr.mathpix_to_raster(136, 1599, 1254, 43,
                               raster_size=(2439, 3681),
                               mathpix_size=(1525, 2301))
    assert box == (217, 2557, 2223, 2626)


def test_mathpix_to_raster_a_single_factor_would_get_wrong():
    # width and height scale by DIFFERENT factors here (2x vs 3x): a
    # single width-derived factor (the pre-654 bug) would place y at
    # 10*2=20, not 10*3=30.
    box = pr.mathpix_to_raster(10, 10, 5, 5,
                               raster_size=(200, 300),
                               mathpix_size=(100, 100))
    assert box == (20, 30, 30, 45)


def test_mathpix_to_raster_refuses_without_mathpix_dims():
    assert pr.mathpix_to_raster(0, 0, 10, 10, raster_size=(100, 100),
                                mathpix_size=(0, 100)) is None
    assert pr.mathpix_to_raster(0, 0, 10, 10, raster_size=(100, 100),
                                mathpix_size=(100, 0)) is None


def test_mathpix_to_raster_refuses_an_empty_result():
    # a region entirely past the raster's edge clamps to nothing
    assert pr.mathpix_to_raster(999, 999, 10, 10, raster_size=(100, 100),
                                mathpix_size=(100, 100)) is None


def test_gs_base_use_cropbox_flag():
    assert "-dUseCropBox" not in pr._gs_base("gs", 400, "png")
    assert "-dUseCropBox" in pr._gs_base("gs", 400, "png", use_cropbox=True)


def test_use_cropbox_renders_the_smaller_box():
    """Real Ghostscript: page 1's CropBox (439x662.56pt) rasterizes smaller
    than its MediaBox (493x700pt) at the same dpi when use_cropbox=True."""
    if not any(shutil.which(t) for t in ("gs", "gswin64c", "gswin32c")):
        print("SKIP use_cropbox (no ghostscript)"); return
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"
        _pdf_with_cropbox(pdf)
        cropped = pr.rasterize(pdf, Path(d) / "crop", pages=[1], dpi=400,
                               use_cropbox=True)
        full = pr.rasterize(pdf, Path(d) / "full", pages=[1], dpi=400,
                            use_cropbox=False)
        wc, hc = Image.open(cropped[0]).size
        wf, hf = Image.open(full[0]).size
        assert (wc, hc) == (2439, 3681)          # 439 x 662.56 pt @ 400dpi
        assert (wf, hf) == (2739, 3889)          # 493 x 700 pt @ 400dpi
        assert (wc, hc) != (wf, hf)


def test_use_cropbox_is_byte_identical_when_boxes_agree():
    """The 'Before You Begin' gate: a page whose CropBox equals its MediaBox
    must rasterize identically with and without -dUseCropBox — required
    before this flag can touch the shared rasterizer the ink chain also
    uses (regionink's report.pdf pages always have equal boxes)."""
    if not any(shutil.which(t) for t in ("gs", "gswin64c", "gswin32c")):
        print("SKIP use_cropbox byte-identity (no ghostscript)"); return
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"
        _pdf_with_cropbox(pdf)                    # page 2 has equal boxes
        cropped = pr.rasterize(pdf, Path(d) / "crop", pages=[2], dpi=400,
                               use_cropbox=True)
        full = pr.rasterize(pdf, Path(d) / "full", pages=[2], dpi=400,
                            use_cropbox=False)
        assert cropped[0].read_bytes() == full[0].read_bytes()


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
    test_table_quality_filters(); print("PASS table_quality_filters")
    test_tables_to_html_spans(); print("PASS tables_to_html")
    test_rasterize_roundtrip(); print("PASS rasterize_roundtrip")
    test_rasterize_uses_ghostscript_at_400_floor(); print("PASS rasterize_gs_400")
    test_list_attachments_none(); print("PASS attachments_none")
    print("\nAll tests passed.")
