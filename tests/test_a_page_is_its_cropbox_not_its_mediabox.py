r"""A reading's frame is the page's CropBox, which is what anyone renders.

lib:d68e0271bd4d p334 was the board's worst ours page: residual 1.4311 against
MathPix's 0.0391, with every glyph unpaired. The cause is not the reading of the
glyphs, it is the frame they are reported in. That page has

    MediaBox  0 87 595 842       CropBox  43 87 473 747

and pdfminer's `LTPage.bbox` is the MediaBox, so the reading declared a
595 x 842 page -- 2066 x 2924 px at our scale -- and placed every region at
MediaBox-absolute coordinates. Ghostscript, MathPix and every other renderer
crop to the CropBox and produce 430 x 660 pt, so the two frames differ by both a
scale and a (43, 87) origin, and nothing in either picture says so.

`PDFPage.cropbox` states it. With the frame corrected, inkdrill-10 measured
0 unpaired glyphs, 0 glyph findings and residual 0.0249 on that page.

Note which coordinate needed what: y is already measured DOWN FROM `p.rect[3]`,
so making `p.rect` the CropBox fixes y and the page size on its own. Only x is
absolute, and only x needs the origin subtracted.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from pdfreader import docmodel_six as dm

#: A whole PDF, written out rather than fetched: one page, a MediaBox of
#: 0 0 300 400, a CropBox inset by (20, 30) and 200 x 300 in size, and the word
#: "Hi" at 50 60 in MEDIABOX coordinates — so inside the crop it sits at
#: (30, 30) from the crop's bottom-left.
_PDF = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 400]/CropBox[20 30 220 330]/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>endobj
4 0 obj<</Length 44>>stream
BT /F1 12 Tf 50 60 Td (Hi) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
trailer<</Root 1 0 R>>
"""


@pytest.fixture()
def cropped(tmp_path):
    p = tmp_path / "crop.pdf"
    p.write_bytes(_PDF)
    # qpdf rewrites it into a well-formed file with an xref; the boxes survive.
    out = tmp_path / "ok.pdf"
    r = subprocess.run(["qpdf", str(p), str(out)], capture_output=True)
    if not out.exists():
        pytest.skip("qpdf could not normalise the hand-written fixture")
    got = subprocess.run(["pdfinfo", "-box", str(out)], capture_output=True, text=True).stdout
    assert "CropBox" in got and "20.00" in got, got
    return out


def test_the_page_rect_is_the_cropbox(cropped):
    page = dm.build(str(cropped))[0]
    w = page.rect[2] - page.rect[0]
    h = page.rect[3] - page.rect[1]
    assert (round(w), round(h)) == (200, 300), (
        "the frame must be the CropBox's 200x300, not the MediaBox's 300x400")


def test_the_reading_states_the_cropbox_size(cropped):
    out = dm.read(str(cropped)) if hasattr(dm, "read") else None
    if out is None:
        pytest.skip("no reading entry point on this module")
    pg = out["pages"][0]
    k = pg["px_per_pt"]
    assert round(pg["page_width"] / k) == 200
    assert round(pg["page_height"] / k) == 300


def test_a_region_is_relative_to_the_cropbox_origin(cropped):
    page = dm.build(str(cropped))[0]
    glyphs = [g for line in page.lines for g in line.glyphs]
    assert glyphs, "the fixture's text must be read"
    x0 = min(g.rect[0] for g in glyphs)
    # the glyph is at x=50 in MediaBox coordinates, 30 inside a crop starting at 20
    assert 25 <= x0 - page.rect[0] <= 35, (
        "x must be measured from the CropBox origin, got %.1f with origin %.1f"
        % (x0, page.rect[0]))
