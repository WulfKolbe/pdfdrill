"""
reconcile — parallel MathPix + pdfminer.six dual-route reconciliation.

Two routes are COMPLEMENTARY, not competing (grounded on 2607.02234): the pdfminer
route wins STRUCTURE (citations / figrefs / transclusions / front-matter) + GEOMETRY
(PDF points → self-contained inspect), but garbles the MATH at the source; MathPix
wins clean math. Reconciliation is per-ASPECT best-of: math ← MathPix (region-
matched), geometry ← pdfminer (never mix coordinate systems), structure ← pdfminer.

This module holds the PURE pieces:
  P1  to_page_fraction / iou / match_equations — match a pdfminer equation to the
      MathPix equation over the same page region, normalising BOTH to page-fraction
      [0,1] (comparison-only conversion; the app keeps each system's own coords).
  P3  is_char_spaced / is_truncated / math_qc — flag the pdfminer math garble
      (char-spacing `_{O P S D}`, truncation) so it is VISIBLE and correctable at
      the source (DRILLPDFse), and so reconciliation knows which bodies to replace.
"""
from __future__ import annotations

import re
from typing import Optional

# --- P3: math-garble QC --------------------------------------------------------
# 3+ single alpha chars separated by single spaces — the extraction spaced out a
# multi-char identifier (`O P S D`→OPSD, `l o g`→log). Normal single-char sub/
# superscripts (`_{0}`, `\pi_{\theta}`) do NOT match.
_CHAR_SPACED = re.compile(r"(?:\b[A-Za-z]\s){2,}[A-Za-z]\b")


def is_char_spaced(latex: str) -> bool:
    """True when a multi-char identifier was spaced char-by-char (extraction
    artifact) — the dominant pdfminer garble."""
    return bool(_CHAR_SPACED.search(latex or ""))


def is_truncated(latex: str) -> bool:
    """True when the LaTeX is cut off — unbalanced `{}` or `\\left`/`\\right`."""
    s = latex or ""
    # ignore escaped braces \{ \}
    plain = re.sub(r"\\[{}]", "", s)
    if plain.count("{") != plain.count("}"):
        return True
    if len(re.findall(r"\\left\b", s)) != len(re.findall(r"\\right\b", s)):
        return True
    return False


def math_qc(latex: str) -> dict:
    """Per-equation QC verdict: {char_spaced, truncated, garbled}. `garbled` is
    True if ANY signal fires — the body a reconciliation should replace with
    MathPix, and a concrete extraction bug for DRILLPDFse."""
    cs = is_char_spaced(latex)
    tr = is_truncated(latex)
    return {"char_spaced": cs, "truncated": tr, "garbled": bool(cs or tr)}


# --- P1: region matching across the two coordinate systems ---------------------
def _num(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def to_page_fraction(region: dict, page_w: float, page_h: float):
    """A region → (x0,y0,x1,y1) in page fractions [0,1]. Works for EITHER system
    (pdfminer points ÷ page-points, MathPix pixels ÷ MathPix-page-pixels) — this
    normalisation is comparison-only; the app never mixes the raw coordinates."""
    x = _num(region.get("top_left_x")); y = _num(region.get("top_left_y"))
    w = _num(region.get("width")); h = _num(region.get("height"))
    if None in (x, y, w, h) or not page_w or not page_h:
        return None
    return (x / page_w, y / page_h, (x + w) / page_w, (y + h) / page_h)


def iou(a, b) -> float:
    """Intersection-over-union of two [0,1] boxes (x0,y0,x1,y1)."""
    if not a or not b:
        return 0.0
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def match_equations(pm_eqs: list, mp_eqs: list, pm_pages: dict, mp_pages: dict,
                    min_iou: float = 0.3) -> list:
    """Greedy best-IoU pairing of pdfminer equations to MathPix equations, per
    page, in page-fraction space. `*_pages` maps page → (page_w, page_h) for each
    side. Returns [(pm_eq, mp_eq, iou)] for pairs above `min_iou`; each MathPix
    equation is used at most once."""
    pairs = []
    used = set()
    for pe in pm_eqs:
        pg = pe.get("page")
        pw, ph = pm_pages.get(pg, (None, None))
        pf = to_page_fraction(pe.get("region") or {}, pw, ph) if pw else None
        if pf is None:
            continue
        best, best_iou = None, min_iou
        for i, me in enumerate(mp_eqs):
            if i in used or me.get("page") != pg:
                continue
            mw, mh = mp_pages.get(pg, (None, None))
            mf = to_page_fraction(me.get("region") or {}, mw, mh) if mw else None
            score = iou(pf, mf)
            if score > best_iou or (best is None and score >= min_iou):
                best, best_iou, best_i = me, score, i
        if best is not None:
            used.add(best_i)
            pairs.append((pe, best, round(best_iou, 3)))
    return pairs


# --- P2: adopt MathPix math onto the region-matched pdfminer equations ----------
def plan_adoptions(pm_eqs: list, mp_eqs: list, pm_pages: dict, mp_pages: dict,
                   min_iou: float = 0.3) -> list:
    """For each region-matched pair, plan the reconciliation: adopt the MathPix
    (clean) LaTeX onto the pdfminer equation, KEEPING its geometry + structure.
    Returns [{pm_id, mathpix_latex, iou, was_garbled}] — the caller sets each
    object's latex to mathpix_latex (preserving latex_pdfminer). Geometry is never
    touched; MathPix is math-body-only."""
    out = []
    for pe, me, sc in match_equations(pm_eqs, mp_eqs, pm_pages, mp_pages, min_iou):
        out.append({
            "pm_id": pe.get("id"),
            "mathpix_latex": me.get("latex", ""),
            "iou": sc,
            "was_garbled": math_qc(pe.get("latex", ""))["garbled"],
        })
    return out
