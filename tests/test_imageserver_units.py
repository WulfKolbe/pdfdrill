"""
imageserver /cropped `units=pt` — OUR coordinate system end to end. A pdfminer
(DRILLPDFse) model stores equation regions in PDF POINTS; the crop URL carries
`units=pt`, and the pyramid server must scale points -> pyramid pixels by
pyramid_dpi/72 (never the MathPix pixel path). This builds a REAL small DZI
pyramid with pyvips and asserts resolve_crop pulls the correctly-sized region.

Skips cleanly when pyvips/libvips is absent (the pyramid builder's dependency).
"""
import importlib.util
import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

pyvips = pytest.importorskip("pyvips")
PIL = pytest.importorskip("PIL")
from PIL import Image

# import the (non-package) imageserver module by path
_spec = importlib.util.spec_from_file_location(
    "mathpix_server", REPO / "tools" / "imageserver" / "mathpix_server.py")
srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srv)


def _build_pyramid(tiles_dir: Path, name: str, w: int, h: int):
    """Tile one synthetic w x h page image to <tiles_dir>/<name>.dzi (+ _files)."""
    tiles_dir.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (w, h), (255, 255, 255))
    png = tiles_dir / "tmp.png"
    img.save(png)
    v = pyvips.Image.new_from_file(str(png))
    v.dzsave(str(tiles_dir / name), layout="dz", suffix=".jpg", overlap=1, tile_size=254)
    png.unlink()


def test_units_pt_scales_points_by_pyramid_dpi_over_72(tmp_path):
    PYR_DPI = 600.0
    # a page rendered at 600 DPI: 8.5x11 in -> 5100 x 6600 px
    W, H = int(8.5 * PYR_DPI), int(11 * PYR_DPI)
    tiles = tmp_path / "tiles"
    _build_pyramid(tiles, "page-0", W, H)

    args = SimpleNamespace(
        root=None, tiles=str(tiles), pyramid_dpi=PYR_DPI, mathpix_dpi=None,
        cache_entries=8, pad=0, page_pattern="page-{page}.dzi", jpg_quality=80)
    index = SimpleNamespace(page_of={}, dims={}, region_of={})
    server = srv.Server(args, index)

    # a 190.9 x 10.9 pt equation box at (197.5, 302.98) pt — DRILLPDFse's shape
    qs = {"page": ["0"], "units": ["pt"], "top_left_x": ["197.5"],
          "top_left_y": ["302.98"], "width": ["190.9"], "height": ["10.9"]}
    data, ctype = server.resolve_crop("pdfminer-p0", qs)
    assert ctype == "image/jpeg"
    crop = Image.open(io.BytesIO(data))
    scale = PYR_DPI / 72.0                       # OUR conversion: pt -> pyramid px
    exp_w = round(190.9 * scale)
    exp_h = round(10.9 * scale)
    # allow +-2 px for floor/ceil rounding in Pyramid.crop
    assert abs(crop.width - exp_w) <= 2, (crop.width, exp_w)
    assert abs(crop.height - exp_h) <= 2, (crop.height, exp_h)


def test_units_pt_ignores_mathpix_dims(tmp_path):
    """With units=pt, a stray MathPix page-dims entry must NOT change the scale
    (no coordinate-system mixing)."""
    PYR_DPI = 600.0
    W, H = 5100, 6600
    tiles = tmp_path / "tiles"
    _build_pyramid(tiles, "page-0", W, H)
    args = SimpleNamespace(
        root=None, tiles=str(tiles), pyramid_dpi=PYR_DPI, mathpix_dpi=150,
        cache_entries=8, pad=0, page_pattern="page-{page}.dzi", jpg_quality=80)
    # a bogus MathPix dims that WOULD change the scale if consulted
    index = SimpleNamespace(page_of={}, dims={0: (999, 999)}, region_of={})
    server = srv.Server(args, index)
    qs = {"page": ["0"], "units": ["pt"], "top_left_x": ["100"],
          "top_left_y": ["100"], "width": ["72"], "height": ["36"]}
    data, _ = server.resolve_crop("pdfminer-p0", qs)
    crop = Image.open(io.BytesIO(data))
    # 72 pt * 600/72 = 600 px ; 36 pt -> 300 px — NOT the dims-based scaling
    assert abs(crop.width - 600) <= 2 and abs(crop.height - 300) <= 2
