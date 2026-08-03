"""A scan carrying a third-party OCR underlay must not be routed as born-digital.

`route` infers born-digital from the mere PRESENCE of a text layer. But a scanned
document that someone already ran OCR over has a text layer made OF that OCR — so
the free "text-layer extraction, free and exact" lane re-extracts somebody else's
OCR output and calls it exact. It can never recover mathematics, and the caller is
told no OCR is needed.

The source-independent signal is geometric: a scan is one full-page image per
page. Measured on USRE41428 (a reissued US patent, Producer ImageMagick, 19 pages
/ 19 full-page images, Courier as its only font) — routed born-digital, so the
lane that could actually read it was never offered.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.ocr_router import choose_route, is_scanned_page_images


def test_full_page_image_on_every_page_is_a_scan():
    # 19 pages, each with one image covering essentially the whole page
    imgs = [{"page": p, "w_pt": 600.0, "h_pt": 780.0} for p in range(1, 20)]
    assert is_scanned_page_images(imgs, page_count=19,
                                  page_w=612.0, page_h=792.0)


def test_figures_in_a_real_paper_are_not_a_scan():
    """A born-digital paper has small figures on some pages, not full-page ones."""
    imgs = [{"page": 1, "w_pt": 200.0, "h_pt": 150.0},
            {"page": 3, "w_pt": 260.0, "h_pt": 180.0},
            {"page": 3, "w_pt": 90.0, "h_pt": 90.0}]
    assert not is_scanned_page_images(imgs, page_count=12,
                                      page_w=612.0, page_h=792.0)


def test_a_few_full_page_images_do_not_make_a_scan():
    """One full-page cover plate in a 30-page book is not a scanned book."""
    imgs = [{"page": 1, "w_pt": 610.0, "h_pt": 790.0},
            {"page": 2, "w_pt": 610.0, "h_pt": 790.0}]
    assert not is_scanned_page_images(imgs, page_count=30,
                                      page_w=612.0, page_h=792.0)


def test_route_prefers_ocr_when_the_text_layer_sits_on_a_scan():
    d = choose_route(text_layer=True, needs_ocr=False, page_count=19,
                     scanned_images=True)
    assert d.lane != "born_digital", "a scan must not take the text-layer lane"
    assert "ocr" in d.reason.lower() or "scan" in d.reason.lower()


def test_a_genuine_born_digital_doc_is_unaffected():
    d = choose_route(text_layer=True, needs_ocr=False, page_count=19,
                     scanned_images=False)
    assert d.lane == "born_digital" and d.cost == "free"


def test_scanned_flag_defaults_to_the_old_behaviour():
    """Callers that don't pass the new signal keep the previous decision."""
    d = choose_route(text_layer=True, needs_ocr=False, page_count=19)
    assert d.lane == "born_digital"
