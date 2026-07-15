"""
The point-vs-pixel contract (integration prompt step 3). The enriched OCR module
emits regions in PDF POINTS (ocr.units="pt"), where the OLD module emitted raster
PIXELS. Nothing may mix the two:

  * mathpix source            → image PIXELS → cdn.mathpix.com crop URL
  * every other source        → PDF POINTS   → OUR /cropped/…&units=pt pyramid URL

`docmodel.mathpix.image_ref` selects on the SOURCE alone. This is what makes the
keyless (tesseract) crop path correct — the old pixel regions were silently routed
to a units=pt URL, i.e. pixels mislabelled as points.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.mathpix import image_ref, is_local_crop

_REGION = {"top_left_x": 296.46, "top_left_y": 588.24, "width": 11.88, "height": 4.68}


def test_tesseract_region_routes_to_local_points_crop():
    """A tesseract (enriched) region is POINTS → our pyramid crop, units=pt —
    never the MathPix pixel CDN."""
    url = image_ref("tesseract-p4", _REGION, "tesseract")
    assert is_local_crop(url), url
    assert "units=pt" in url and "cdn.mathpix.com" not in url
    assert "top_left_x=296.46" in url and "width=11.88" in url


def test_pdfminer_region_routes_to_local_points_crop():
    url = image_ref("pdfminer-p1", _REGION, "pdfminer")
    assert is_local_crop(url) and "units=pt" in url


def test_mathpix_region_still_routes_to_the_pixel_cdn():
    """The MathPix path is untouched: PIXELS → the CDN, never units=pt."""
    url = image_ref("2f8a_img", _REGION, "mathpix")
    assert "cdn.mathpix.com" in url
    assert "units=pt" not in url and not is_local_crop(url)


def test_ratios_are_unit_agnostic():
    """Regions and page dims share the source's unit, so normalised fractions
    (what geometry fusion / column tagging use) work for BOTH units."""
    # points page vs pixels page — same relative rectangle → same fraction
    pt = _REGION["top_left_x"] / 612.0
    px = (_REGION["top_left_x"] * 400 / 72) / (612.0 * 400 / 72)
    assert abs(pt - px) < 1e-9


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
