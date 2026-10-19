r"""The model lane scored against MathPix's own reading of the same pages.

WHY THIS IS THE ACCEPTANCE TEST
-------------------------------
A new reader cannot be checked against a hand transcription at any useful
scale: the two reference documents are 2,000 printed lines and a hand
reference exists for eight of them. What does exist is MathPix's reading of
exactly those pages, bought already — and its GEOMETRY is precisely the half a
language model does not return, so it is the half most likely to be wrong.

It is also free. The Markdown was read once (0.034 EUR for the 48-page
document) and is on disk; the comparison renders pages with Ghostscript and
compares boxes. Nothing here touches the metered account, which is the only
reason a geometry change can be re-verified at all.

SKIPS, DELIBERATELY, when the corpora are absent. Neither the library PDFs nor
the model's Markdown is in this repository — the library holds documents that
must not be published — so the floors below are claims about this machine's
corpus, pinned so that a regression in the reader fails rather than passes
quietly. The numbers in each docstring are what was measured on 2026-10-19.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("PIL.Image")

from pdfdrill import gemma_reader as gr
from pdfdrill import linescmp, pdf_reading

_LIB = Path.home() / "pdfdrill-library"
_RUNS = Path.home() / "Gemma4" / "testpool" / "ocr-runs"

#: (label, pdf, the model's Markdown for it, MathPix's reading of it)
_CASES = {
    "killing48": (
        _LIB / "mathann33-m01-die-zusammensetzung-der-stetigen-endlichen"
             / "mathann33-m01-die-zusammensetzung-der-stetigen-endlichen.pdf",
        _RUNS / "ocr-markdown-math.v0.8.mk.killing48.r1",
        _LIB / "mathann33-m01-die-zusammensetzung-der-stetigen-endlichen"
             / "mathann33-m01-die-zusammensetzung-der-stetigen-endlichen.lines.json",
    ),
    "hilbert10": (
        _LIB / "hilbert1902-foundations-math10"
             / "hilbert1902-foundations-math10.pdf",
        _RUNS / "ocr-markdown-math.hilbert.v0.3.mk.hilbert10pdf.r1",
        _LIB / "hilbert1902-foundations-math10"
             / "hilbert1902-foundations-math10.lines.json",
    ),
}


def _build(case: str, tmp_path: Path) -> dict:
    pdf, md_dir, _ref = _CASES[case]
    renders = pdf_reading.rasterize(pdf, tmp_path / "pages", dpi=gr.DPI,
                                    gray=True)
    by_no = {pdf_reading.page_of(p): p for p in renders}
    triples = []
    for f in sorted(md_dir.glob("page-*.md")):
        n = int(f.stem.split("-")[1])
        triples.append((n, f.read_text(encoding="utf-8"), by_no.get(n)))
    return gr.assemble(triples, prompt_name="page-ocr-markdown")


@pytest.fixture(scope="module")
def _have_gs():
    if pdf_reading.gs_binary() is None:
        pytest.skip("Ghostscript is the only rasterizer and it is absent")


def _require(case: str):
    pdf, md_dir, ref = _CASES[case]
    for p in (pdf, md_dir, ref):
        if not p.exists():
            pytest.skip(f"local corpus absent: {p}")


def _score(case: str, tmp_path: Path) -> dict:
    _require(case)
    doc = _build(case, tmp_path)
    ref = _CASES[case][2]
    import json
    return linescmp.compare(
        doc, json.loads(ref.read_text(encoding="utf-8")))


# ── the German 19th-century mathematics journal, 48 pages ─────────────────

def test_killing_finds_the_reference_lines_where_mathpix_put_them(
        _have_gs, tmp_path):
    """MEASURED 2026-10-19: 1,576 of 1,694 reference lines found at IoU>=0.5
    (93%), median IoU 0.825. The floor is set below that, not at it: the
    point is to catch a regression, and the reading is of a scan."""
    res = _score("killing48", tmp_path)
    assert res["pages"] == 48
    assert res["lines"] > 1600, "the reference reading changed"
    assert res["hit_rate"] >= 0.88, (
        f"found only {res['hit']}/{res['lines']} ({res['hit_rate']:.0%})")
    assert res["median_iou"] >= 0.78, res["median_iou"]


def test_killing_agrees_with_mathpix_on_what_each_line_is(_have_gs, tmp_path):
    """MEASURED: 1,566 of 1,572 found lines typed alike (100%). A box in the
    right place with the wrong type is still a line the transclusion gate,
    the caption anchors and the furniture checks will treat wrongly."""
    res = _score("killing48", tmp_path)
    assert res["type_rate"] >= 0.95, (
        f"typed alike {res['type_ok']}/{res['hit']} "
        f"({res['type_rate']:.0%})")


def test_killing_finds_the_equation_numbers_as_their_own_lines(
        _have_gs, tmp_path):
    """MEASURED: 40 of 51. They are printed BESIDE a display, so each one is
    cut out of the display's own row; the first version of that split, which
    took a geometric fraction of the host box instead of its narrow
    component cluster, found 1."""
    res = _score("killing48", tmp_path)
    total, found, _typed = res["by_type"]["equation_number"]
    assert total >= 50
    assert found >= 30, f"only {found}/{total} equation numbers placed"


def test_killing_finds_the_footnote_blocks(_have_gs, tmp_path):
    """MEASURED: 3 of 4, and 4 of 4 containers emitted. The container shape
    is what `FootnoteProcessor` needs; the box is the union of its
    children."""
    res = _score("killing48", tmp_path)
    total, found, _typed = res["by_type"]["footnote"]
    assert total == 4 and found >= 3


def test_killing_emits_two_page_info_lines_per_page(_have_gs, tmp_path):
    """The folio and the running head, printed at opposite ends of one row.
    MEASURED: 94 ours (two per page, less the pages with no running head)
    against 103 — the reference also types the printer's sheet signature."""
    res = _score("killing48", tmp_path)
    assert 80 <= res["page_info_ours"] <= res["page_info_theirs"] + 4


def test_killing_does_not_flood_the_page_with_boxes(_have_gs, tmp_path):
    """A reader that emits far more boxes than the reference would score well
    on recall while being useless. MEASURED: 1,740 ours against 1,694."""
    res = _score("killing48", tmp_path)
    assert res["ours_lines"] <= res["lines"] * 1.15


# ── the English geometry book, 10 pages, greyscale with a scan band ───────

def test_hilbert_is_read_despite_the_scan_band_at_its_gutter(
        _have_gs, tmp_path):
    """MEASURED 2026-10-19: 224 of 306 (73%), median IoU 0.729. Lower than
    the other document for reasons that are the MODEL's reading and not the
    geometry — it transcribed a ruled table as four display equations, so
    the reference's 15 `simple_cell` lines have no counterpart at all.

    What this test guards is the page itself: a 97 x 3413 dark band at the
    gutter and the slivers it broke into. With neither cleanup the score was
    6%; with the row-collapse fix alone, 42%.
    """
    res = _score("hilbert10", tmp_path)
    assert res["pages"] == 10
    assert res["hit_rate"] >= 0.65, (
        f"found only {res['hit']}/{res['lines']} ({res['hit_rate']:.0%})")
    assert res["median_iou"] >= 0.62, res["median_iou"]
    assert res["type_rate"] >= 0.88, res["type_rate"]


def test_hilbert_boxes_stay_inside_the_printed_area(_have_gs, tmp_path):
    """The slivers the gutter band broke into each joined a different text
    row and stretched it to the page edge: the right margin moved from 0.94
    of the page to 1.00, which is every box on the page slightly wrong."""
    _require("hilbert10")
    doc = _build("hilbert10", tmp_path)
    worst = 0.0
    for pg in doc["pages"]:
        w = pg["page_width"]
        for l in pg["lines"]:
            r = l["region"]
            if r["width"]:
                worst = max(worst, (r["top_left_x"] + r["width"]) / w)
    assert worst < 0.99, f"a box reaches {worst:.3f} of the page width"
