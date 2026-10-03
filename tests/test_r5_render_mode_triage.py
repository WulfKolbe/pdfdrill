r"""R5 — render mode in the scan triage.

CR-pdfminer-single-version R5. The LANE was already right: pdfdrill sent all
three of psred's scan fixtures to the scanned lane on page geometry alone.
What the triage could not say is WHICH KIND of scan it is, and that decides
whether a text layer exists to be re-served:

    scan_only.pdf             a scan, no text at all
    scan_ocr.pdf              a scan with an OCR text layer
    scan_ocr_invisible.pdf    the same, drawn in render mode 3

All three were reported identically, as "scanned, N pages".

THE OBVIOUS TEST DOES NOT WORK. Tesseract's `GlyphLessFont` names only
Tesseract; `scan_ocr_invisible.pdf` carries 154 characters of OCR in CMR10
and no font name betrays it. What does is the PDF text rendering mode: `Tr 3`
(neither fill nor stroke) and `Tr 7` (clip only) put no marks on the page,
which is how an OCR layer is written over a page raster.

The rule is psred's, unchanged (`psred/preflight.py:check`), so both sides
answer the same question the same way — which is the point of the request.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfdrill import ocr_router as R                          # noqa: E402

FIX = Path("/tmp/claude-1000/-home-wkolbe-MX-PDFDRILL/"
           "ae99387a-8fcf-4b96-b9d9-5dc00cc6f8da/scratchpad")
PSRED = Path.home() / "psred" / "fixtures" / "scan"


def _fixture(name: str) -> Path:
    for base in (PSRED, FIX):
        p = base / name
        if p.exists():
            return p
    pytest.skip(f"psred scan fixture not available: {name}")


# --------------------------------------------------------------------------
# The acceptance criterion.
# --------------------------------------------------------------------------

def test_the_invisible_ocr_fixture_is_classified_as_having_an_ocr_layer():
    """THE CR's criterion. 154 characters in mode 3, CMR10, no GlyphLessFont."""
    pdf = _fixture("scan_ocr_invisible.pdf")
    info = R.ocr_layer_for(pdf, scan_pages=[1], page_count=1,
                           font_names=R.font_names_for(pdf), scanned=True)
    assert info["ocr_layer"] is True
    assert info["glyphless_font"] is False, (
        "the point of the fixture: no font name gives it away")
    assert info["invisible_chars"] == 154, info
    assert info["chars_on_scan_pages"] == 154, info
    assert any("render mode" in w for w in info["why"]), info["why"]


def test_a_scan_with_no_text_is_a_definite_no_not_an_unknown():
    """`scan_only.pdf` carries no text at all. That is an ANSWER — the pages
    were read and hold nothing — and a first version of this reported it as
    unknown, so the triage said nothing about the document at all."""
    pdf = _fixture("scan_only.pdf")
    info = R.ocr_layer_for(pdf, scan_pages=[1, 2], page_count=2,
                           font_names=R.font_names_for(pdf), scanned=True)
    assert info["ocr_layer"] is False
    assert info["known"] is True, "read and empty is knowledge, not ignorance"
    assert info["chars_on_scan_pages"] == 0


def test_a_visible_ocr_layer_is_caught_by_the_text_on_a_scan_arm():
    """`scan_ocr.pdf` draws its OCR visibly, so the render-mode share does not
    fire; a text layer on a scan is still somebody's OCR."""
    pdf = _fixture("scan_ocr.pdf")
    info = R.ocr_layer_for(pdf, scan_pages=[1], page_count=1,
                           font_names=R.font_names_for(pdf), scanned=True)
    assert info["ocr_layer"] is True


# --------------------------------------------------------------------------
# The rule itself, where it can be exercised without a file.
# --------------------------------------------------------------------------

def test_the_invisible_modes_are_three_and_seven():
    assert R.INVISIBLE_MODES == (3, 7)


def test_an_unreadable_document_is_unknown_not_a_no():
    """`render_mode_counts` returns None when the READING failed and `{}` when
    the pages were read and carry no text. Collapsing the two would report
    "no OCR layer" for a document nobody could open."""
    assert R.render_mode_counts("/nonexistent/nothing.pdf", [1]) is None
    info = R.ocr_layer_for("/nonexistent/nothing.pdf", scan_pages=[1],
                           page_count=1, font_names=(), scanned=True)
    assert info["ocr_layer"] is False
    assert info["known"] is False, "nothing was established; say so"


def test_the_scan_page_set_has_one_implementation():
    """`scan_page_set` is shared by the scan test and by R5's sample. A second
    copy of "which pages are the scan" is a second thing to keep in step."""
    imgs = [{"page": 1, "w_pt": 600, "h_pt": 800},
            {"page": 2, "w_pt": 600, "h_pt": 800},
            {"page": 3, "w_pt": 60, "h_pt": 80}]      # a figure, not a page
    assert R.scan_page_set(imgs, 3, 612, 792) == {1, 2}
    assert R.is_scanned_page_images(imgs, 3, 612, 792) is False   # 2 of 3 < 0.8
    assert R.is_scanned_page_images(imgs[:2], 2, 612, 792) is True


def test_only_the_scan_pages_decide_the_share():
    """Pages 1-2 are sampled for context, but a title page of real text there
    must not dilute the invisible share measured on the scan."""
    import inspect
    src = inspect.getsource(R.ocr_layer_for)
    assert "scan_pages[:_SAMPLE_SCAN_PAGES]" in src
    assert "scan_modes" in src


def test_half_is_the_threshold():
    """psred's rule, so both sides answer the same question the same way."""
    import inspect
    assert "scan_invis * 2 >= scan_total" in inspect.getsource(R.ocr_layer_for)
