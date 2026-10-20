"""Text + position layers from the PDF's own text layer.

`pdftotext -tsv` emits a 12-column TSV with a bounding box per word.

Schema (per word):
    page, par, block, line, word, left, top, width, height, conf, text

There used to be a second route here: render every page and run tesseract. It
is gone, and with it the idea that a measurement can manufacture its own
reading. A PDF with no text layer has no word boxes to give; which lane WOULD
read it is `ocr_router.choose_route`'s decision and `word_boxes.no_words_note`'s
sentence. The schema stayed because it was never tesseract's — any 12-column
TSV still parses here.
"""

from __future__ import annotations

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
# Subprocess wrapper
# ---------------------------------------------------------------------------

def _run(cmd: list[str], timeout: int = 30) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except (subprocess.SubprocessError, OSError):
        return ""
