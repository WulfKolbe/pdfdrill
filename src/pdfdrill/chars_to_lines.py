"""
chars_to_lines — convert a pdfplumber CHARACTER dump to a MathPix-shape
lines.json, so a born-digital PDF (one that already has a text layer) becomes
drillable OFFLINE with no MathPix spend.

Input shape (pdfplumber chars, PDF bottom-left origin):
    {"source", "total_pages", "pages":[{"page_number","width","height",
                                         "chars":[{"x0","y0","x1","y1","text",...}]}]}

We flip each char to the MathPix top-left origin (y down), group chars into
visual lines by baseline, split lines into words on x-gaps, and hand the word
records to `ocr_lines.lines_json_from_words` (the proven offline assembler —
line grouping + region + out-of-column tagging), tagged source
"pdfplumber-chars". Pure + unit-testable.
"""
from __future__ import annotations

import statistics
from typing import Any

from . import ocr_lines


def _page_words(page: dict[str, Any]) -> list[dict[str, Any]]:
    pg = page.get("page_number")
    ph = float(page.get("height") or 0)
    chars = [c for c in (page.get("chars") or []) if (c.get("text") or "") != ""]
    if not chars:
        return []
    # to top-left origin (y down): top = ph - y1, bottom = ph - y0
    items = [{"x0": float(c["x0"]), "x1": float(c["x1"]),
              "top": ph - float(c["y1"]), "bottom": ph - float(c["y0"]),
              "t": c["text"]} for c in chars]
    heights = [i["bottom"] - i["top"] for i in items if i["bottom"] > i["top"]]
    tol = (statistics.median(heights) * 0.6) if heights else 3.0
    items.sort(key=lambda i: (round(i["top"] / max(tol, 0.1)), i["x0"]))

    # cluster into lines by baseline proximity
    lines: list[list[dict]] = []
    for it in items:
        if lines and abs(it["top"] - lines[-1][0]["top"]) <= tol:
            lines[-1].append(it)
        else:
            lines.append([it])

    words: list[dict[str, Any]] = []
    for li, line in enumerate(lines):
        line.sort(key=lambda i: i["x0"])
        widths = [i["x1"] - i["x0"] for i in line if i["x1"] > i["x0"]]
        gap = (statistics.median(widths) * 0.4) if widths else 1.5
        cur: list[dict] = []

        def flush(wi: int) -> None:
            if not cur:
                return
            words.append({
                "page": pg, "block": 0, "line": li,
                "x0": min(c["x0"] for c in cur), "x1": max(c["x1"] for c in cur),
                "y0": min(c["top"] for c in cur), "y1": max(c["bottom"] for c in cur),
                "text": "".join(c["t"] for c in cur).strip(),
            })

        prev_x1 = None
        for c in line:
            if c["t"].isspace():
                flush(0); cur = []; prev_x1 = c["x1"]; continue
            if prev_x1 is not None and (c["x0"] - prev_x1) > gap and cur:
                flush(0); cur = []
            cur.append(c); prev_x1 = c["x1"]
        flush(0)
    return [w for w in words if w["text"]]


def chars_to_lines_json(data: dict[str, Any]) -> dict[str, Any]:
    """Born-digital char dump → MathPix-compatible lines.json dict. The dump's own
    `source` label is preserved (pdfminer-chars / pdfplumber-chars)."""
    words: list[dict] = []
    dims: dict[int, tuple[float, float]] = {}
    for page in data.get("pages", []):
        pg = page.get("page_number")
        dims[pg] = (float(page.get("width") or 0), float(page.get("height") or 0))
        words.extend(_page_words(page))
    return ocr_lines.lines_json_from_words(
        words, dims, source=data.get("source", "pdfplumber-chars"))
