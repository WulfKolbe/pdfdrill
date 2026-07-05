"""
docmodel.mathpix.image_ref — source-aware crop reference. MathPix regions are
page-image PIXELS served from cdn.mathpix.com; a pdfminer (DRILLPDFse) lines.json
carries regions in PDF POINTS served from OUR local pyramid. The application
never mixes the two coordinate systems — image_ref picks the right one from the
source, and the local URL carries `units=pt` so the pyramid server scales points
→ pixels by pyramid_dpi/72 (never MathPix's pixel DPI).
"""
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel import mathpix as M

REGION = {"top_left_x": 197.5, "top_left_y": 302.98, "width": 190.9, "height": 10.9}


def test_mathpix_source_is_cdn_pixels():
    url = M.image_ref("img-42", REGION, source="mathpix")
    assert url.startswith("https://cdn.mathpix.com/cropped/img-42.jpg")
    q = parse_qs(urlparse(url).query)
    assert "units" not in q                     # MathPix has no units marker
    assert q["top_left_x"] == ["197.5"]


def test_pdfminer_source_is_local_pyramid_points():
    url = M.image_ref("pdfminer-p0", REGION, source="pdfminer")
    # NOT a MathPix CDN URL — our local pyramid route
    assert "cdn.mathpix.com" not in url
    assert url.startswith("/cropped/pdfminer-p0.")
    q = parse_qs(urlparse(url).query)
    assert q["units"] == ["pt"]                 # OUR coordinate system: PDF points
    assert q["top_left_x"] == ["197.5"] and q["width"] == ["190.9"]


def test_default_and_empty():
    # default source is mathpix (back-compat for old callers)
    assert M.image_ref("i", REGION).startswith("https://cdn.mathpix.com/")
    # missing id/region → ''
    assert M.image_ref("", REGION, source="pdfminer") == ""
    assert M.image_ref("i", None, source="pdfminer") == ""


def test_crop_url_unchanged_for_mathpix():
    # the existing MathPix builder is byte-identical (regression guard)
    assert M.image_ref("i", REGION, source="mathpix") == M.crop_url("i", REGION)


def test_is_local_crop_helper():
    assert M.is_local_crop(M.image_ref("p", REGION, source="pdfminer")) is True
    assert M.is_local_crop(M.image_ref("p", REGION, source="mathpix")) is False
    assert M.is_local_crop("") is False


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try:
            t(); print(f"PASS {name}")
        except AssertionError as e:
            failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e:
            failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
