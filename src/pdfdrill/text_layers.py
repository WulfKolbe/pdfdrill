"""Text + position layers from pdftotext -tsv and (optionally) tesseract.

pdftotext -tsv emits a 12-column TSV with bounding boxes per word. Same
schema as tesseract TSV, so both produce records of the same shape.

Schema (per word):
    page, par, block, line, word, left, top, width, height, conf, text

Tesseract is opt-in: if not on PATH the cmd warns and stops at pdfplumber.
Use it when the PDF has no text layer (pdffonts returned nothing). The
state machine consults `has_text_layer` evidence before choosing.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# pdftotext -tsv
# ---------------------------------------------------------------------------

def fetch_pdftotext_tsv(pdf: Path) -> list[dict[str, Any]]:
    """Return a list of word records with bounding boxes."""
    out = _run(["pdftotext", "-tsv", str(pdf), "-"], timeout=120)
    return _parse_tsv(out)


def _parse_tsv(stdout: str) -> list[dict[str, Any]]:
    lines = stdout.splitlines()
    if not lines:
        return []
    header = lines[0].split("\t")
    # Find columns we care about — names match for both pdftotext and tesseract.
    idx = {name: header.index(name) for name in header}
    if "text" not in idx or "page_num" not in idx:
        return []

    words: list[dict[str, Any]] = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < len(header):
            continue
        try:
            level = int(parts[idx["level"]])
        except (ValueError, KeyError):
            level = 0
        # level 5 = word in both tools
        if level != 5:
            continue
        text = parts[idx["text"]]
        if not text:
            continue
        try:
            words.append({
                "page": int(parts[idx["page_num"]]),
                "left": float(parts[idx["left"]]),
                "top": float(parts[idx["top"]]),
                "width": float(parts[idx["width"]]),
                "height": float(parts[idx["height"]]),
                "conf": float(parts[idx["conf"]]),
                "text": text,
            })
        except (ValueError, KeyError):
            continue
    return words


def summarize_tsv(words: list[dict[str, Any]]) -> dict[str, Any]:
    if not words:
        return {"words": 0, "pages": 0, "avg_conf": 0.0}
    pages = {w["page"] for w in words}
    confs = [w["conf"] for w in words if w["conf"] >= 0]
    return {
        "words": len(words),
        "pages": len(pages),
        "avg_conf": round(sum(confs) / len(confs), 1) if confs else 0.0,
        "low_conf_words": sum(1 for w in words if 0 <= w["conf"] < 60),
    }


# ---------------------------------------------------------------------------
# Tesseract OCR (opt-in fallback for scanned PDFs)
# ---------------------------------------------------------------------------

def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def fetch_tesseract_tsv(
    pdf: Path,
    out_dir: Path,
    ppi: int = 300,
    lang: str = "eng",
) -> list[dict[str, Any]]:
    """Render each page to PNG via pdftoppm and OCR with tesseract.

    Produces the same per-word record shape as pdftotext -tsv, so
    downstream consumers don't need to know which tool ran.
    """
    if not tesseract_available():
        raise RuntimeError(
            "tesseract is not on PATH. Install with `apt install tesseract-ocr` "
            "and the relevant language packs."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    # Render all pages via Ghostscript >= 400 DPI (the only rasterizer).
    from . import pdf_reading
    page_pngs = pdf_reading.rasterize(pdf, out_dir, dpi=ppi, fmt="png")

    all_words: list[dict[str, Any]] = []
    for png in page_pngs:
        page_num = _page_num_from_filename(png.name)
        result = subprocess.run(
            ["tesseract", str(png), "-", "-l", lang, "--psm", "1", "tsv"],
            capture_output=True, text=True, timeout=120,
        )
        page_words = _parse_tsv(result.stdout)
        # Patch the page_num: tesseract emits page=1 for every call
        for w in page_words:
            w["page"] = page_num
            # Convert pixel coordinates to PDF points for consistency
            for k in ("left", "top", "width", "height"):
                w[k] = w[k] / ppi * 72.0
        all_words.extend(page_words)
    return all_words


def _page_num_from_filename(name: str) -> int:
    # pdftoppm names: page-NN.png or page-NNN.png
    digits = "".join(c for c in name if c.isdigit())
    return int(digits) if digits else 0


# ---------------------------------------------------------------------------
# Subprocess wrapper
# ---------------------------------------------------------------------------

def _run(cmd: list[str], timeout: int = 30) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except (subprocess.SubprocessError, OSError):
        return ""
