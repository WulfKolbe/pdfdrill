"""Build a per-page Deep-Zoom (DZI) pyramid for a PDF — the local, MathPix-free
image source (Phase C of the image-server plan).

The page is rendered with **Ghostscript at >=400 DPI** (default 600 — pdfdrill's
gs-only rasterizer, `pdf_reading.rasterize`), then tiled to DZI with pyvips
`dzsave`. The deepest pyramid level IS the full render, so a 600-DPI build gives a
600-DPI full-resolution level that `eqcrop.Pyramid` reads region crops from and
the OpenSeadragon viewer deep-zooms. Output under `<out>/`:
    tiles/page01.dzi + page01_files/…   (one DZI per page)
    manifest.json                       (page → dzi/width/height/levels)

pyvips (system `libvips`) is required only here (the tiling); `eqcrop` crops with
Pillow alone. Degrades cleanly when pyvips/libvips is absent.
"""
from __future__ import annotations

import json
import math
import shutil
from pathlib import Path
from typing import Optional


def _have_pyvips() -> bool:
    try:
        import pyvips  # noqa: F401
        return True
    except Exception:
        return False


def tools_available() -> tuple[bool, str]:
    """(ok, message). Needs Ghostscript (render) + pyvips/libvips (dzsave)."""
    from . import pdf_reading
    missing = []
    if pdf_reading.gs_binary() is None:
        missing.append("ghostscript")
    if not _have_pyvips():
        missing.append("pyvips (system libvips-tools)")
    if missing:
        return False, (
            f"pyramid build needs {' and '.join(missing)}. Install: "
            f"`apt-get install ghostscript libvips-tools && pip install "
            f"'pdfdrill[imageserver]'`.")
    return True, ""


def _manifest_entry(page: int, name: str, w: int, h: int) -> dict:
    """One manifest row. `levels` = DZI level count (ceil(log2(max(w,h)))+1)."""
    return {"page": page, "dzi": f"tiles/{name}.dzi", "width": int(w),
            "height": int(h), "levels": math.ceil(math.log2(max(w, h, 1))) + 1}


def build_pyramid(pdf: Path, out_dir: Path, *, dpi: int = 600,
                  tile_size: int = 254, overlap: int = 1, quality: int = 88,
                  pages: Optional[list[int]] = None) -> dict:
    """Render the PDF with gs at `dpi` and dzsave each page to a DZI pyramid under
    `<out_dir>/tiles/`, writing `<out_dir>/manifest.json`. Returns
    {pages, dpi, tiles_dir, manifest}. Raises RuntimeError if gs/pyvips absent."""
    ok, msg = tools_available()
    if not ok:
        raise RuntimeError(msg)
    import pyvips
    from . import pdf_reading

    out_dir = Path(out_dir)
    tiles_dir = out_dir / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    raster_dir = out_dir / "_render"
    pngs = pdf_reading.rasterize(pdf, raster_dir, pages=pages, dpi=dpi)  # gs >=400
    if not pngs:
        raise RuntimeError("pyramid: no pages rendered")
    manifest = []
    for i, png in enumerate(pngs, 1):
        name = f"page{i:02d}"
        img = pyvips.Image.new_from_file(str(png), access="sequential")
        img.dzsave(str(tiles_dir / name), layout="dz",
                   suffix=f".jpg[Q={quality}]", tile_size=tile_size, overlap=overlap)
        manifest.append(_manifest_entry(i, name, img.width, img.height))
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    shutil.rmtree(raster_dir, ignore_errors=True)            # keep only the tiles
    return {"pages": len(manifest), "dpi": dpi,
            "tiles_dir": str(tiles_dir), "manifest": manifest}
