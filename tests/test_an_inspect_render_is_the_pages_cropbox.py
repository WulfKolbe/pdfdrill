r"""The inspector's page image is the CropBox, because the boxes drawn on it are.

`test_a_page_is_its_cropbox_not_its_mediabox` established the frame for the
READING, on lib:d68e0271bd4d. The inspector is the other half of the same
agreement and did not hold it: `_inspect_pages_dir` called
`pdf_reading.rasterize(...)` without `use_cropbox=True`, so the render was the
MediaBox while the reading it is annotated with was the CropBox.

Nothing reconciles them afterwards. `docinspect` scales by
`im.naturalWidth / g.pxW` (docinspect.py:1627 and :1663) and has NO origin
term, so the two frames must be the same box. On d68e p24 — MediaBox
0 0 595 842, CropBox 43 87 473 747 — that scale came out 3306/1494 = 2.21
where the truth is 1.60, and the drawn boxes of the three body paragraphs and
of footnotes 5 and 6 sat off their ink. The owner saw it in the output.

Measured on the fixture below before the fix: the render was 300 x 400 pt (the
MediaBox), its ink ran from x-fraction 0.1704, and the reading declared the
same glyph at 0.1500 of the page — 2% of the image width out, with the error
growing with the crop's inset.

A page that declares no CropBox is unaffected, since CropBox == MediaBox there;
that is why this moves d68e alone of the ten board documents.
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

#: One page: MediaBox 0 0 300 400, CropBox inset by (20, 30) and 200 x 300, and
#: the word "Hi" at 50 60 in MEDIABOX coordinates — 30 pt inside the crop. The
#: same fixture as test_a_page_is_its_cropbox_not_its_mediabox, so the two
#: halves of the frame agreement are tested against one geometry.
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

#: `rasterize` floors dpi to RASTER_MIN_DPI (400), so asking for less renders
#: higher than the number it reports back. Ask for the floor.
DPI = 400


@pytest.fixture()
def cropped(tmp_path):
    if not __import__("shutil").which("qpdf"):
        pytest.skip("qpdf absent")
    raw = tmp_path / "raw.pdf"
    raw.write_bytes(_PDF)
    out = tmp_path / "crop.pdf"
    subprocess.run(["qpdf", str(raw), str(out)], capture_output=True)
    if not out.exists():
        pytest.skip("qpdf could not normalise the hand-written fixture")
    return out


def _render(pdf):
    from pdfdrill.commands import _inspect_pages_dir
    from pdfdrill.sidecar import Sidecar
    d, dpi, reason = _inspect_pages_dir(pdf, Sidecar(pdf), "1", DPI)
    if d is None:
        pytest.skip("no rasterizer: %s" % reason)
    return d, dpi


def _ink_x_fraction(png):
    """(first, last) column holding ink, as a fraction of the image width."""
    Image = pytest.importorskip("PIL.Image", reason="Pillow absent")
    im = Image.open(png).convert("L")
    W, H = im.size
    px = im.load()
    cols = [x for x in range(W) for y in range(H) if px[x, y] < 128]
    assert cols, "the fixture's text must be rendered"
    return min(cols) / W, max(cols) / W


def test_the_render_is_the_cropbox_not_the_mediabox(cropped):
    """300 x 400 pt is the MediaBox; the reading, and so the inspector, is
    200 x 300."""
    pytest.importorskip("PIL.Image", reason="Pillow absent")
    from PIL import Image
    d, dpi = _render(cropped)
    W, H = Image.open(d / "p1.png").size
    assert (round(W / dpi * 72), round(H / dpi * 72)) == (200, 300), (
        "rendered %d x %d px at %d dpi = %.0f x %.0f pt; the CropBox is 200 x 300"
        % (W, H, dpi, W / dpi * 72, H / dpi * 72))


def test_a_drawn_box_lands_on_its_ink(cropped):
    """The gate: the box the inspector draws from the READING must fall on the
    ink of the RENDER. The inspector has no origin term, so this is exactly the
    comparison of two fractions of the image width."""
    from pdfreader import docmodel_six as dm
    d, _ = _render(cropped)
    first, last = _ink_x_fraction(d / "p1.png")

    page = dm.build(str(cropped))[0]
    glyphs = [g for line in page.lines for g in line.glyphs]
    assert glyphs, "the fixture's text must be read"
    pw = page.rect[2] - page.rect[0]
    box_x0 = (min(g.rect[0] for g in glyphs) - page.rect[0]) / pw

    assert abs(box_x0 - first) <= 0.01, (
        "the drawn box starts at %.4f of the image width, its ink at %.4f — "
        "%.1f%% of the page apart" % (box_x0, first, abs(box_x0 - first) * 100))


def test_the_manifest_says_which_frame_the_images_are_of(cropped):
    """Without this field a MediaBox render of the right document at the right
    dpi is reused forever, and the fix reaches no folder that already holds
    pages."""
    d, _ = _render(cropped)
    assert json.loads((d / "manifest.json").read_text())["frame"] == "cropbox"


def test_a_mediabox_render_is_not_reused(cropped, monkeypatch):
    """Re-render rather than serve pages from the wrong frame. A manifest that
    does not say is treated as not cropbox: it is a render that did not state
    its frame, which is not a render that stated this one."""
    from pdfdrill.commands import _pages_on_disk
    d, _ = _render(cropped)
    man = d / "manifest.json"
    got = json.loads(man.read_text())
    assert _pages_on_disk(d, cropped, [1], DPI), "a cropbox render IS reusable"

    for bad in ({k: v for k, v in got.items() if k != "frame"},
                {**got, "frame": "mediabox"}):
        man.write_text(json.dumps(bad))
        assert _pages_on_disk(d, cropped, [1], DPI) == {}, (
            "reused a render whose frame is %r" % bad.get("frame"))


def test_both_renderers_of_the_folder_use_the_cropbox():
    """`pdf2mmd.sh` renders the same folder and writes the same manifest, so it
    carries the same flag and the same field — otherwise `inspect` re-renders
    every page pdf2mmd made, once per folder, forever."""
    sh = (Path(__file__).resolve().parents[1]
          / "src" / "pdfreader" / "pdf2mmd.sh").read_text()
    assert "-dUseCropBox" in sh
    assert '"frame": "cropbox"' in sh


def test_every_renderer_of_a_page_uses_the_cropbox():
    """Three places turn this PDF into pixels and all three must agree on the
    frame, because the boxes drawn over them come from one reading:

      `_inspect_pages_dir`      the stored page images
      `pdf2mmd.sh`              the other writer of that same folder
      `inspectserver.render`    `/render/pN.png?dpi=400`, which also crops by a
                                rect a caller computed from the reading

    Two of the three were found only by looking for the first one's siblings.
    """
    root = Path(__file__).resolve().parents[1] / "src"
    body = (root / "pdfdrill" / "commands.py").read_text()
    body = body.split("def _inspect_pages_dir(", 1)[1].split("\ndef ", 1)[0]
    assert "use_cropbox=True" in body

    srv = (root / "pdfreader" / "inspectserver.py").read_text()
    srv = srv.split("    def render(", 1)[1].split("\n    def ", 1)[0]
    assert "-dUseCropBox" in srv

    assert "-dUseCropBox" in (root / "pdfreader" / "pdf2mmd.sh").read_text()
