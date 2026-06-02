"""
Margin-aware continuity extraction (the scan-triage blocker).

MathPix crops to the main content block, so the page-sequence markers German
documents print in the MARGIN — "Seite N von M", "Fortsetzung (siehe) Seite N",
bare "Seite N", and Druck-/Kontrollnummern — are dropped or misfiled. This
module OCRs the FULL page (margins included) with tesseract, reusing the
page-render + TSV plumbing from `ocr_lines`/`geometry`, and classifies the
continuity tokens with their margin position. It NEVER routes through the
MathPix content crop.

Pure helpers (`classify_lines`, the regexes) are unit-testable without tesseract;
`extract_continuity` does the render+OCR.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from . import geometry, ocr_lines

# "Seite 2 von 6" (this page's number + the doc's total).
_SEITE_VON = re.compile(r"\bSeite\s+(\d{1,3})\s+von\s+(\d{1,3})\b", re.I)
# "Fortsetzung [siehe] Seite 3" (footer pointer to the NEXT physical page).
_FORTSETZUNG = re.compile(r"\bFortsetzung\b[^\n]{0,20}?\bSeite\s+(\d{1,3})", re.I)
# bare "Seite 3" / "- 3 -" page number, no "von".
_SEITE_BARE = re.compile(r"\bSeite\s+(\d{1,3})\b(?!\s+von)", re.I)
# Labelled control numbers (Druck-/Kontroll-/Beleg-/Dokumentnummer …). The value
# is a single no-space token so it doesn't run into the following words.
_CONTROL = re.compile(
    r"\b(?:Druck|Kontroll|Beleg|Dokument|Sendungs|Auftrags)\s*-?\s*(?:nummer|nr\.?)"
    r"\s*[:#]?\s*([A-Z0-9][A-Z0-9./\-]{2,})", re.I)


def _margin(x0: float, y0: float, x1: float, y1: float,
            w: float, h: float) -> str:
    """Where on the page a box sits: top/bottom/left/right margin, else body."""
    if not (w and h):
        return "body"
    cy = (y0 + y1) / 2.0
    cx = (x0 + x1) / 2.0
    if cy < 0.12 * h:
        return "top"
    if cy > 0.88 * h:
        return "bottom"
    if cx < 0.10 * w:
        return "left"
    if cx > 0.90 * w:
        return "right"
    return "body"


def classify_lines(lines: list[dict], dims: tuple[float, float]) -> dict[str, Any]:
    """Classify one page's OCR lines into continuity metadata.

    `lines` are geometry.group_lines records ({x0,y0,x1,y1,text}); `dims` is the
    page (w, h). Returns {seq_in_doc, doc_total, is_continuation, next_seite,
    control_no, markers:[{text,kind,where}]}.
    """
    w, h = dims if dims else (0.0, 0.0)
    info: dict[str, Any] = {
        "seq_in_doc": None, "doc_total": None, "is_continuation": False,
        "next_seite": None, "control_no": None, "markers": [],
    }
    for ln in lines:
        text = (ln.get("text") or "").strip()
        if not text:
            continue
        where = _margin(ln.get("x0", 0), ln.get("y0", 0),
                        ln.get("x1", 0), ln.get("y1", 0), w, h)

        m = _SEITE_VON.search(text)
        if m:
            info["seq_in_doc"] = info["seq_in_doc"] or int(m.group(1))
            info["doc_total"] = info["doc_total"] or int(m.group(2))
            info["markers"].append({"text": m.group(0), "kind": "seite_von", "where": where})

        m = _FORTSETZUNG.search(text)
        if m:
            info["is_continuation"] = True
            info["next_seite"] = info["next_seite"] or int(m.group(1))
            info["markers"].append({"text": m.group(0).strip(), "kind": "fortsetzung", "where": where})

        if info["seq_in_doc"] is None:
            m = _SEITE_BARE.search(text)
            if m and "fortsetzung" not in text.lower():
                info["seq_in_doc"] = int(m.group(1))
                info["markers"].append({"text": m.group(0), "kind": "seite", "where": where})

        if info["control_no"] is None:
            m = _CONTROL.search(text)
            if m:
                info["control_no"] = m.group(1).strip()
                info["markers"].append({"text": m.group(0).strip(), "kind": "control", "where": where})
    return info


def extract_continuity(pdf, out_dir, ppi: int = 250,
                       lang: str = "deu+eng") -> dict[int, dict[str, Any]]:
    """Render every page, OCR the FULL page (margins included) with tesseract,
    and classify continuity metadata per page. Returns {page_no: info}."""
    words, page_dims = ocr_lines._render_and_ocr(pdf, out_dir, ppi, lang)
    by_page: dict[int, list[dict]] = {}
    for ln in geometry.group_lines(words):
        by_page.setdefault(ln["page"], []).append(ln)
    out: dict[int, dict] = {}
    for page, dims in sorted(page_dims.items()):
        out[page] = classify_lines(by_page.get(page, []), dims)
    # Pages with words but no level-1 dims (rare) still get classified.
    for page, lns in by_page.items():
        if page not in out:
            out[page] = classify_lines(lns, page_dims.get(page, (0, 0)))
    return out


def tools_available() -> tuple[bool, str]:
    return ocr_lines.tools_available()
