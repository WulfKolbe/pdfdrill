"""
pdfimg_locate (src/pdfdrill/pdfimg_locate.py): locate embedded raster images on
PDF pages in ONE canonical coordinate system (points, top-left origin, y-down —
the MathPix lines.json orientation), compare them to MathPix regions (IoU /
fraction-inside), and extract. Pure-function characterization + a built-PDF
round-trip; the tool-backed path guards on poppler presence.
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import pdfimg_locate as L


# ---- pure parsers ---------------------------------------------------------
_PDFINFO = """Title:          x
Pages:          2
Page    1 size: 612 x 792 pts (letter)
Page    2 size: 612 x 792 pts (letter)
"""

_PDFIMAGES = """page   num  type   width height color comp bpc  enc interp  object ID x-ppi y-ppi size ratio
--------------------------------------------------------------------------------------------
   1     0 image    1440   810  rgb     3   8  jpeg  no        11  0   144   144  213K 8.3%
   1     1 image     100   100  gray    1   8  image no        12  0    72    72  1.0K 10%
"""


def test_parse_pdfinfo_pages():
    pages = L.parse_pdfinfo(_PDFINFO)
    assert set(pages) == {1, 2}
    assert round(pages[1].width_pt) == 612 and round(pages[1].height_pt) == 792


def test_parse_pdfimages_list_columns_and_object_num():
    rows = L.parse_pdfimages_list(_PDFIMAGES)
    assert len(rows) == 2
    r = rows[0]
    assert r.page == 1 and r.num == 0 and r.enc == "jpeg"
    assert r.width_px == 1440 and r.height_px == 810
    assert r.object_num == 11                       # join key into pdfdrill
    assert r.x_ppi == 144.0


def test_iou_and_fraction_inside():
    a = [0, 0, 10, 10]
    assert L.iou(a, a) == 1.0
    assert L.iou(a, [20, 20, 30, 30]) == 0.0
    half = L.iou([0, 0, 10, 10], [5, 0, 15, 10])
    assert 0.3 < half < 0.34                        # 50/150
    # a small box fully inside a big one
    assert L.fraction_inside([2, 2, 4, 4], [0, 0, 10, 10]) == 1.0
    assert L.fraction_inside([8, 8, 12, 12], [0, 0, 10, 10]) == 0.25


def test_bbox_to_mathpix_px_uniform_scale():
    # a half-width, top-left-quarter box at 2x page-image scale
    px = L.bbox_to_mathpix_px([0, 0, 306, 396], 612, 792, 1224, 1584)
    assert px == [0, 0, 612, 792]


def test_mathpix_region_to_norm():
    norm = L.mathpix_region_to_norm(
        {"top_left_x": 100, "top_left_y": 200, "width": 400, "height": 400},
        800, 1000)
    assert norm == [0.125, 0.2, 0.625, 0.6]


# ---- tool-backed: built PDF round-trip ------------------------------------
def _png_pdf(path: Path):
    """A 1-page PDF with one embedded PNG, via reportlab if present else skip."""
    try:
        from PIL import Image
    except Exception:
        return False
    import struct
    # build a tiny PNG
    img = Image.new("RGB", (64, 48), (200, 40, 40))
    png = path.with_suffix(".png"); img.save(png)
    try:
        from pypdf import PdfWriter
    except Exception:
        return False
    # pypdf can't easily place an image; use reportlab if available
    try:
        from reportlab.pdfgen import canvas
    except Exception:
        return False
    c = canvas.Canvas(str(path), pagesize=(612, 792))
    c.drawImage(str(png), 100, 600, width=128, height=96)
    c.showPage(); c.save()
    return True


def test_locate_on_built_pdf():
    if shutil.which("pdfimages") is None or shutil.which("pdfinfo") is None:
        print("SKIP (poppler missing)"); return
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"
        if not _png_pdf(pdf):
            print("SKIP (PIL/reportlab missing)"); return
        res = L.locate_pdf_images(str(pdf))
        assert res["pages"]
        imgs = [im for pg in res["pages"] for im in pg["images"]]
        assert imgs and imgs[0]["object_num"] is not None
        assert "bbox_norm" in imgs[0]


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
