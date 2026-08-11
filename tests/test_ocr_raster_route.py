"""OCR page rendering goes through the one rasterizer, and asks for grayscale.

`ocr_lines._rasterize` carried its own Ghostscript invocation — a second one,
against the repo's rule that every raster task routes through
`pdf_reading.rasterize` — and it rendered the WHOLE document in a single gs
call. That call is the one place sharding pays most: measured elsewhere in
pdf_reading, 32 pages at 400 DPI go from 8.7 s in one process to 1.4 s across
16. OCR never got any of it.

Device, scored against the born-digital text layer (the only ground truth
available), pages 8-15 of the Infineon handbook: png16m 91.29%, pnggray
91.14%, pgmraw 92.82%. So grayscale does not cost fidelity — and it is 2.5x
(pnggray) to 7.8x (pgmraw) cheaper to render and read.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import ocr_lines


def test_ocr_rendering_delegates_to_the_single_rasterizer(monkeypatch, tmp_path):
    calls = {}

    def fake(pdf, out_dir, *, pages=None, dpi=400, fmt="png", gray=False):
        calls.update(pdf=pdf, out_dir=out_dir, dpi=dpi, fmt=fmt, gray=gray)
        f = Path(out_dir) / "page-0001.png"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"")
        return [f]

    monkeypatch.setattr(ocr_lines.pdf_reading, "rasterize", fake)
    monkeypatch.setattr(ocr_lines.subprocess, "run", _no_subprocess)
    out = ocr_lines._rasterize(Path("x.pdf"), tmp_path, 300)

    assert [p.name for p in out] == ["page-0001.png"]
    assert calls["gray"] is True               # OCR never wanted colour
    assert calls["dpi"] == 300                 # the floor is the rasterizer's job


def _no_subprocess(*a, **k):
    raise AssertionError("ocr_lines ran its own Ghostscript")


def test_the_page_number_still_parses_whatever_the_extension(tmp_path):
    """Downstream keys everything by true page number, so the naming contract
    must survive a device change."""
    assert ocr_lines._page_num_from_png(tmp_path / "page-0042.png") == 42
    assert ocr_lines._page_num_from_png(tmp_path / "page-0042.pgm") == 42


def test_every_tesseract_consumer_asks_for_grayscale(monkeypatch, tmp_path):
    """Three modules render pages only to hand them to tesseract. The evidence
    that grayscale is free is the same for all three, so the choice should be
    too — a per-module decision is how one of them ends up on colour by
    accident."""
    from pdfdrill import text_layers, layout_elements, pdf_reading

    seen = []

    def fake(pdf, out_dir, *, pages=None, dpi=400, fmt="png", gray=False):
        seen.append(gray)
        return []

    monkeypatch.setattr(pdf_reading, "rasterize", fake)
    monkeypatch.setattr(text_layers, "tesseract_available", lambda: True)
    for fn in (lambda: text_layers.fetch_tesseract_tsv(tmp_path / "x.pdf",
                                                       out_dir=tmp_path),
               lambda: layout_elements.build_combined_tsv(tmp_path / "x.pdf",
                                                          tmp_path)):
        try:
            fn()
        except Exception:                       # noqa: BLE001  (no pages -> raises)
            pass
    assert seen and all(seen), f"a tesseract consumer still renders in colour: {seen}"
