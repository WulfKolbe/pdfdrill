"""
Tesseract OCR → MathPix-compatible `lines.json`.

This is the **MathPix-free OCR input path**, so the toolkit runs end-to-end on
any PDF without a MathPix key: render each page, OCR it with tesseract (which is
in the sandbox and ships `tsv`/`makebox` outputs), group the word boxes into
text lines, and emit a `lines.json` of the *same shape* the docmodel pipeline
already ingests. `pdfdrill model` then consumes it exactly as if MathPix had
produced it, and every downstream layer (geometry, lists, nlp, tiddlers,
report, …) works unchanged.

Why TSV over makebox: tesseract's TSV carries the full block/paragraph/line/word
hierarchy + per-word confidence + bounding boxes, which is precisely what we
need to reconstruct *lines* (makebox is per-glyph, no line grouping, no
confidence). The TSV parser + line grouping already exist in `geometry.py`
(used for pdftotext fusion); we reuse them so there is one code path.

Limits (documented, not hidden): tesseract emits **plain text only** — no LaTeX
and no figure/equation typing. Every line is `type="text"`; there are no MathPix
CDN crops, so the math-comparison columns are empty on this path. Math fidelity
remains MathPix-only. Pass `lang="eng+equ"` (the `equ` model) to bias toward
mathematical glyphs, or `eng+deu` for German documents.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from . import geometry


def tools_available() -> tuple[bool, str]:
    """Return (ok, message). Needs both pdftoppm (poppler) and tesseract."""
    missing = [t for t in ("pdftoppm", "tesseract") if shutil.which(t) is None]
    if missing:
        return False, (
            f"OCR needs {' and '.join(missing)} on PATH. Install poppler-utils "
            f"and tesseract-ocr (plus a language pack, e.g. tesseract-ocr-eng)."
        )
    return True, ""


# ---------------------------------------------------------------------------
# Pure assembler: words (+ page dims) -> MathPix-shaped lines.json dict
# ---------------------------------------------------------------------------

def lines_json_from_words(
    words: list[dict[str, Any]],
    page_dims: dict[int, tuple[float, float]],
    *,
    source: str = "tesseract",
) -> dict[str, Any]:
    """Assemble a `lines.json` dict from parsed TSV words + page dimensions.

    `words` are geometry.parse_tsv word records ({page, block, line, x0, y0,
    x1, y1, text}); `page_dims` maps page → (width, height) in the same pixel
    units. Each grouped line becomes a `type="text"` line with a MathPix-style
    `region` (top_left_x/y, width, height). Pure — no subprocess — so it is
    unit-testable with synthetic input.
    """
    lines = geometry.group_lines(words)
    by_page: dict[int, list[dict]] = {}
    for i, ln in enumerate(lines):
        pg = ln["page"]
        x0, y0, x1, y1 = ln["x0"], ln["y0"], ln["x1"], ln["y1"]
        by_page.setdefault(pg, []).append({
            "id": f"ocr_p{pg}_l{len(by_page.get(pg, []))}",
            "type": "text",
            "text": ln["text"],
            "text_display": ln["text"],
            "region": {
                "top_left_x": round(x0, 2),
                "top_left_y": round(y0, 2),
                "width": round(x1 - x0, 2),
                "height": round(y1 - y0, 2),
            },
        })

    # Drive page list from page_dims so blank pages still appear.
    all_pages = sorted(set(page_dims) | set(by_page))
    pages = []
    for pg in all_pages:
        w, h = page_dims.get(pg, (0.0, 0.0))
        pages.append({
            "page": pg,
            "image_id": None,            # no CDN crop on the OCR path
            "page_width": round(w, 2),
            "page_height": round(h, 2),
            "lines": by_page.get(pg, []),
        })
    return {"source": source, "pages": pages}


# ---------------------------------------------------------------------------
# Impure: render pages + run tesseract
# ---------------------------------------------------------------------------

def _render_and_ocr(
    pdf: Path, out_dir: Path, ppi: int, lang: str,
) -> tuple[list[dict], dict[int, tuple[float, float]]]:
    """Render each page to PNG (pdftoppm) and OCR it (tesseract tsv).

    Returns (words, page_dims) in pixel units, page numbers patched to the real
    page (tesseract reports page 1 for every single-image call).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    root = out_dir / "page"
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(ppi), str(pdf), str(root)],
        check=True, capture_output=True, timeout=900,
    )

    all_words: list[dict] = []
    page_dims: dict[int, tuple[float, float]] = {}
    for png in sorted(out_dir.glob("page-*.png")):
        digits = "".join(c for c in png.stem if c.isdigit())
        page_num = int(digits) if digits else 0
        res = subprocess.run(
            ["tesseract", str(png), "-", "-l", lang, "--psm", "1", "tsv"],
            capture_output=True, text=True, timeout=300,
        )
        words, dims = geometry.parse_tsv(res.stdout)  # page=1 within this call
        for w in words:
            w["page"] = page_num
        all_words.extend(words)
        if 1 in dims:
            page_dims[page_num] = dims[1]
    return all_words, page_dims


def build_lines_json(
    pdf: Path, out_dir: Path, *, ppi: int = 300, lang: str = "eng",
) -> dict[str, Any]:
    """Render + OCR `pdf` and return a MathPix-compatible lines.json dict."""
    ok, msg = tools_available()
    if not ok:
        raise RuntimeError(msg)
    words, page_dims = _render_and_ocr(pdf, out_dir, ppi, lang)
    return lines_json_from_words(words, page_dims)
