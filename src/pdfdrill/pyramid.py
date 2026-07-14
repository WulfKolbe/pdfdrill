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
    gs_missing = pdf_reading.gs_binary() is None
    pyvips_missing = not _have_pyvips()
    if gs_missing or pyvips_missing:
        parts = []
        if pyvips_missing:
            # pyvips is a PIP package (pyvips[binary] bundles libvips — no apt/root);
            # point at the one named installer, never `apt-get` / the wrong name.
            parts.append("pyvips — run:  bash tools/imageserver/install.sh   "
                         "(= pip install 'pdfdrill[imageserver]')")
        if gs_missing:
            parts.append("Ghostscript — run:  sudo apt-get install -y ghostscript")
        return False, "pyramid build needs " + "; ".join(parts) + "."
    return True, ""


def _manifest_entry(page: int, name: str, w: int, h: int) -> dict:
    """One manifest row. `levels` = DZI level count (ceil(log2(max(w,h)))+1)."""
    return {"page": page, "dzi": f"tiles/{name}.dzi", "width": int(w),
            "height": int(h), "levels": math.ceil(math.log2(max(w, h, 1))) + 1}


def _page_count(pdf: Path) -> Optional[int]:
    """Total pages via pypdf (a core dep); None if unreadable."""
    try:
        from pypdf import PdfReader
        return len(PdfReader(str(pdf)).pages)
    except Exception:
        return None


def _dzsave_page(img_path: Path, tiles_dir: Path, name: str, *,
                 tile_size: int = 254, overlap: int = 1,
                 quality: int = 88) -> tuple[int, int]:
    """Tile ONE rendered page image to `<tiles_dir>/<name>.dzi` + `_files/`.
    Returns (width, height). Factored out so tests can observe the per-page
    streaming discipline."""
    import pyvips
    img = pyvips.Image.new_from_file(str(img_path), access="sequential")
    img.dzsave(str(tiles_dir / name), layout="dz",
               suffix=f".jpg[Q={quality}]", tile_size=tile_size, overlap=overlap)
    return img.width, img.height


def build_pyramid(pdf: Path, out_dir: Path, *, dpi: int = 600,
                  tile_size: int = 254, overlap: int = 1, quality: int = 88,
                  pages: Optional[list[int]] = None) -> dict:
    """Render + tile the PDF ONE PAGE AT A TIME (render with gs at `dpi` →
    dzsave → delete the page PNG) into `<out_dir>/tiles/`, writing
    `<out_dir>/manifest.json` at the end. Streaming keeps temp disk flat at
    ~one page — a 211-page manual at 600 DPI would otherwise stage many GB of
    PNGs before tiling even starts. During the build a `build.json` progress
    marker {done, total, dpi} lets a watcher (the drillui waiting page) show
    progress; it is removed on completion. Returns {pages, dpi, tiles_dir,
    manifest}. Raises RuntimeError if gs/pyvips absent."""
    ok, msg = tools_available()
    if not ok:
        raise RuntimeError(msg)
    from . import pdf_reading

    out_dir = Path(out_dir)
    # build LOCK: a FRESH build.json means another build is running — refuse
    # instead of racing it (two concurrent builds wipe each other's temp render:
    # the "pyvips unable to open page-0049.png" / "list index out of range"
    # clash). A stale marker (dead build, >120s untouched) does not block.
    progress = out_dir / "build.json"
    if progress.exists():
        import time as _time
        try:
            age = _time.time() - progress.stat().st_mtime
            if age < 120:
                p = json.loads(progress.read_text(encoding="utf-8"))
                raise RuntimeError(
                    f"a pyramid build is already in progress "
                    f"({p.get('done', '?')}/{p.get('total', '?')} pages tiled) — "
                    f"wait for it; progress: {progress}")
        except (OSError, ValueError):
            pass                                     # unreadable marker → treat as stale

    tiles_dir = out_dir / "tiles"
    tiles_dir.mkdir(parents=True, exist_ok=True)
    progress.write_text(json.dumps({"done": 0, "total": 0, "dpi": dpi}),
                        encoding="utf-8")           # claim the lock immediately
    raster_dir = out_dir / "_render"
    shutil.rmtree(raster_dir, ignore_errors=True)   # clear a killed build's leftovers

    manifest = []
    try:                                             # lock claimed: everything below
        page_list = pages if pages else None         # runs under the finally-release
        if page_list is None:
            n = _page_count(pdf)
            if n:
                page_list = list(range(1, n + 1))
        if page_list is None:                        # unreadable count: render all,
            pngs = pdf_reading.rasterize(pdf, raster_dir, pages=None, dpi=dpi)
            page_list = [int(p.stem.split("-")[1]) for p in pngs]
            prerendered = {int(p.stem.split("-")[1]): p for p in pngs}
        else:
            prerendered = None
        total = len(page_list)
        for i, pageno in enumerate(page_list, 1):
            progress.write_text(json.dumps(
                {"done": i - 1, "total": total, "dpi": dpi}), encoding="utf-8")
            if prerendered is not None:
                png = prerendered[pageno]
            else:                                    # stream: render just this page
                rendered = pdf_reading.rasterize(pdf, raster_dir, pages=[pageno],
                                                 dpi=dpi)
                if not rendered:
                    raise RuntimeError(
                        f"gs produced no image for page {pageno} of {pdf.name} "
                        f"— the PDF may be damaged, or another process removed "
                        f"the temp render (concurrent build?)")
                png = rendered[0]
            name = f"page{i:02d}"
            w, h = _dzsave_page(png, tiles_dir, name, tile_size=tile_size,
                                overlap=overlap, quality=quality)
            manifest.append(_manifest_entry(i, name, w, h))
            try:
                png.unlink()                         # flat disk: drop the page PNG
            except OSError:
                pass
        if not manifest:
            raise RuntimeError("pyramid: no pages rendered")
        (out_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")
    finally:
        progress.unlink(missing_ok=True)
        shutil.rmtree(raster_dir, ignore_errors=True)        # keep only the tiles
    return {"pages": len(manifest), "dpi": dpi,
            "tiles_dir": str(tiles_dir), "manifest": manifest}
