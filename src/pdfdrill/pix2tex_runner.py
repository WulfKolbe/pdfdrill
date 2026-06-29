"""pix2tex integration — render PDF crops to PNG, run LatexOCR, return LaTeX.

Module-level lazy singleton for the LatexOCR model: loading it costs
~5s and ~1.5GB RAM, so we want exactly one load per process.

The model is invoked from cmd_pix2tex on:
  - auto-detected candidates from images_layer (small bitmap images), or
  - explicit (page, rect) supplied by the caller.

Each call:
  1. Renders the page at PPI_RENDER via pdftoppm.
  2. Crops the requested rectangle (PDF pts → image pixels).
  3. Runs LatexOCR on the crop.
  4. Returns the LaTeX string plus the crop path (kept in <pdf>.drill/).
"""

from __future__ import annotations

import os
import subprocess
import time
import warnings
from pathlib import Path
from typing import Any


# Default render resolution. 300 dpi gives ~4x the pdfplumber pt grid,
# which is the sweet spot for pix2tex per the LatexOCR docs.
PPI_RENDER = 300

# How much to dilate the crop around the requested rect, in PDF points.
CROP_PADDING_PT = 4


_model = None


def _get_model():
    """Lazily import and instantiate the LatexOCR model."""
    global _model
    if _model is None:
        # pix2tex emits a wall of pydantic/albumentations warnings on first
        # import. Hide them from the prose output.
        warnings.filterwarnings("ignore")
        os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
        from pix2tex.cli import LatexOCR  # type: ignore
        _model = LatexOCR()
    return _model


# ---------------------------------------------------------------------------
# Page rendering & cropping
# ---------------------------------------------------------------------------

def render_page_to_png(pdf: Path, page: int, out_dir: Path, ppi: int = PPI_RENDER) -> Path:
    """Render a single PDF page to PNG via Ghostscript (>= 400 DPI; the only
    rasterizer). Returns the file path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    from . import pdf_reading
    out = out_dir / f"page-{page:04d}-{ppi}dpi.png"
    return pdf_reading.render_page(pdf, page, out, dpi=ppi)


def crop_rect_from_page(
    page_png: Path,
    page_width_pt: float,
    page_height_pt: float,
    rect_pts: tuple[float, float, float, float],
    ppi: int = PPI_RENDER,
    pad_pt: float = CROP_PADDING_PT,
) -> "Image.Image":
    """Crop a PDF rectangle out of a rendered page image.

    `rect_pts` is `(x0, y0, x1, y1)` in PDF coordinates with the same
    top-down convention pdfplumber uses (`top` increases downward, matching
    image y).
    """
    from PIL import Image

    img = Image.open(page_png)
    img_w_px, img_h_px = img.size
    # Sanity-check that the render resolution matches what we asked for.
    px_per_pt_x = img_w_px / page_width_pt if page_width_pt else ppi / 72.0
    px_per_pt_y = img_h_px / page_height_pt if page_height_pt else ppi / 72.0

    x0, y0, x1, y1 = rect_pts
    x0 = max(0.0, x0 - pad_pt)
    y0 = max(0.0, y0 - pad_pt)
    x1 = min(page_width_pt, x1 + pad_pt) if page_width_pt else x1 + pad_pt
    y1 = min(page_height_pt, y1 + pad_pt) if page_height_pt else y1 + pad_pt

    left = int(round(x0 * px_per_pt_x))
    top = int(round(y0 * px_per_pt_y))
    right = int(round(x1 * px_per_pt_x))
    bottom = int(round(y1 * px_per_pt_y))
    return img.crop((left, top, right, bottom))


def run_latex_ocr(image) -> str:
    """Run pix2tex on a PIL.Image, return the predicted LaTeX string."""
    model = _get_model()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return model(image)


# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------

def process_rect(
    pdf: Path,
    page: int,
    rect_pts: tuple[float, float, float, float],
    page_width_pt: float,
    page_height_pt: float,
    out_dir: Path,
    ppi: int = PPI_RENDER,
    save_crop: bool = True,
) -> dict[str, Any]:
    """Render+crop+OCR one rectangle. Returns a dict with results and timing."""
    t_render0 = time.monotonic()
    page_png = render_page_to_png(pdf, page, out_dir, ppi=ppi)
    t_render = time.monotonic() - t_render0

    crop = crop_rect_from_page(
        page_png, page_width_pt, page_height_pt, rect_pts, ppi=ppi
    )

    crop_path = None
    if save_crop:
        x0, y0, x1, y1 = rect_pts
        crop_name = f"crop-p{page:04d}-{int(x0)}_{int(y0)}_{int(x1)}_{int(y1)}.png"
        crop_path = out_dir / crop_name
        crop.save(crop_path)

    pdf_dir = pdf.resolve().parent
    rel_crop = None
    if crop_path is not None:
        try:
            rel_crop = str(crop_path.resolve().relative_to(pdf_dir))
        except ValueError:
            rel_crop = str(crop_path)

    t_ocr0 = time.monotonic()
    latex = run_latex_ocr(crop)
    t_ocr = time.monotonic() - t_ocr0

    return {
        "page": page,
        "rect": list(rect_pts),
        "latex": latex,
        "crop_path": rel_crop,
        "ppi": ppi,
        "render_ms": round(t_render * 1000, 1),
        "ocr_ms": round(t_ocr * 1000, 1),
    }
