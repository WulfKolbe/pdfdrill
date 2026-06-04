"""
Special-image delivery via `snip` — the state-machine fix so a consumer
interested in ANY specific image (not just equations) gets it delivered.

`cmd_snip` gains two modes beyond the equation loop:
  * --image <path|url|data:> : OCR an arbitrary image (snip() already accepts it).
  * --page N --rect x0,y0,x1,y1 : rasterize that region, DELIVER the crop PNG
    (so the LLM can Read it), then OCR it — and deliver the crop even when OCR is
    unavailable (the "deliver what we can" principle).
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import shutil


def _blank_pdf(path: Path):
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(width=400, height=300)
    with open(path, "wb") as f:
        w.write(f)


def test_deliver_region_crop_writes_a_png():
    if shutil.which("pdftoppm") is None:
        print("SKIP (no pdftoppm)"); return
    from pdfdrill.commands import _deliver_region_crop, Sidecar
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"; _blank_pdf(pdf)
        sc = Sidecar(pdf)
        crop = _deliver_region_crop(pdf, sc, page=1, rect=(10, 10, 120, 60), ppi=100)
        assert crop.exists() and crop.suffix == ".png"


def test_cmd_snip_image_mode_ocrs_any_image(monkeypatch):
    from pdfdrill import commands
    import pdfdrill.mathpix_snip as ms
    monkeypatch.setattr(ms, "snip_result",
                        lambda image, **k: {"latex": "E=mc^2", "text": "E=mc^2", "confidence": 0.97})
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"; _blank_pdf(pdf)
        out = commands.cmd_snip(pdf, image="https://cdn.example.com/crop.png")
    assert "E=mc^2" in out and "0.97" in out


def test_cmd_snip_region_delivers_crop_even_if_ocr_fails(monkeypatch):
    if shutil.which("pdftoppm") is None:
        print("SKIP (no pdftoppm)"); return
    from pdfdrill import commands
    import pdfdrill.mathpix_snip as ms

    def _boom(image, **k):
        raise RuntimeError("no MathPix key")
    monkeypatch.setattr(ms, "snip_result", _boom)
    with tempfile.TemporaryDirectory() as d:
        pdf = Path(d) / "x.pdf"; _blank_pdf(pdf)
        out = commands.cmd_snip(pdf, page=1, rect=(10, 10, 120, 60), ppi=100)
    # the crop is still DELIVERED (a path to Read) even though OCR failed
    assert "crop delivered" in out.lower() or ".png" in out


if __name__ == "__main__":
    test_deliver_region_crop_writes_a_png(); print("PASS region-crop")
    class _MP:
        def setattr(self, o, n, v): setattr(o, n, v)
    test_cmd_snip_image_mode_ocrs_any_image(_MP()); print("PASS image-mode")
    test_cmd_snip_region_delivers_crop_even_if_ocr_fails(_MP()); print("PASS region-delivers")
    print("\nAll tests passed.")
