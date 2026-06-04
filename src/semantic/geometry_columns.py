"""
Unified out-of-column geometry — source-independent.

Works on any line `region` shaped {top_left_x, top_left_y, width, height} —
MathPix AND the tesseract-OCR path produce that shape — so it is the ONE place
that reasons about which content sits outside the body column, regardless of
which OCR engine produced the lines.json. This closes the gap where the OCR path
dropped the tesseract block/column signal and where MathPix's `type='column'`
lines were flattened into role-less Sidenotes.

Why it matters: continuity numbers, control keys (Kassen-/Aktenzeichen) and page
numbers are printed in the MARGIN, outside the print column. A margin item that
looks like a footnote is often a *key* — critical confirmation data. Page numbers
recovered here are the printed numbers the TOC refers to (distinct from the
physical OCR page index).
"""
from __future__ import annotations

import re
from enum import Enum
from statistics import median
from typing import Any, Optional


class MarginRole(str, Enum):
    CONTINUITY = "continuity"          # Seite N von M / Fortsetzung
    PAGE_NUMBER = "page_number"        # printed page number (TOC-referenced)
    CONTROL_NUMBER = "control_number"  # Kassen-/Akten-/Kunden-/control key
    LABEL = "label"                    # a short marginal label
    MARGINAL = "marginal"              # unclassified out-of-column content


# ---- geometry helpers -----------------------------------------------------

def _x0(region: dict) -> float:
    return float(region.get("top_left_x", 0) or 0)


def _x1(region: dict) -> float:
    return _x0(region) + float(region.get("width", 0) or 0)


def _xc(region: dict) -> float:
    return (_x0(region) + _x1(region)) / 2.0


def body_column(regions: list[dict]) -> tuple[float, float]:
    """The (left, right) x-extent of the body text column, derived from the WIDE
    lines (body paragraphs span the column; margin items are narrow)."""
    spans = [(_x0(r), _x1(r)) for r in regions if r]
    if not spans:
        return (0.0, 0.0)
    widths = [b - a for a, b in spans]
    medw = median(widths)
    wide = [s for s, w in zip(spans, widths) if w >= medw] or spans
    return (median([a for a, _ in wide]), median([b for _, b in wide]))


def out_of_column(region: dict, body: tuple[float, float],
                  tol: float = 0.02) -> Optional[str]:
    """Return 'left'/'right' if the line does NOT overlap the body column — its
    whole span sits left of the column's left edge, or right of its right edge
    (with a small `tol`·width epsilon). Indentation within the column is not
    flagged; only genuinely out-of-column margin content is."""
    left, right = body
    width = right - left
    eps = tol * width if width > 0 else tol * 1000
    if _x1(region) < left - eps:
        return "left"
    if _x0(region) > right + eps:
        return "right"
    return None


# ---- margin-item classification -------------------------------------------

_CONT = re.compile(r"\b(Seite|Blatt)\s*\d+\s*von\s*\d+|\bFortsetzung\b", re.I)
_CTRL_KW = re.compile(r"\b(Kassenzeichen|Kundennummer|Aktenzeichen|Steuernummer|"
                      r"Kontrollnummer|Rechnungsnummer|Belegnummer|Referenz|"
                      r"Druck-?Nr|Buchungs)", re.I)
_CTRL_ID = re.compile(r"\d{1,3}(?:[.\-/ ]\d{2,}){2,}|\b\d{6,}\b")
_PAGE = re.compile(r"\b(Seite|Page|S\.)\s*\d+\b", re.I)
_BARE_NUM = re.compile(r"^\s*\d{1,4}\s*$")
_HAS_ALPHA = re.compile(r"[A-Za-zÄÖÜäöüß]{2,}")


def classify_margin_item(text: str) -> MarginRole:
    t = text or ""
    if _CONT.search(t):
        return MarginRole.CONTINUITY
    if _CTRL_KW.search(t) or _CTRL_ID.search(t):
        return MarginRole.CONTROL_NUMBER
    if _PAGE.search(t) or _BARE_NUM.match(t):
        return MarginRole.PAGE_NUMBER
    if _HAS_ALPHA.search(t):
        return MarginRole.LABEL
    return MarginRole.MARGINAL


def tag_out_of_column(lines: list[dict[str, Any]], tol: float = 0.02
                      ) -> list[dict[str, Any]]:
    """Tag each out-of-column line in place with `out_of_column` (left/right) and
    a `margin_role`. Body lines are left untouched. `lines` carry {text, region}.
    Apply per page (regions share a coordinate space)."""
    body = body_column([l.get("region") for l in lines if l.get("region")])
    for l in lines:
        region = l.get("region")
        if not region:
            continue
        side = out_of_column(region, body, tol)
        if side:
            l["out_of_column"] = side
            l["margin_role"] = classify_margin_item(l.get("text", "")).value
    return lines
