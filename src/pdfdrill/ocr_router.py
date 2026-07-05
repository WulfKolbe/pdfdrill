"""
Automatic OCR-lane router — the state machine picks the extraction lane from the
cheap `size` signals and REPORTS the decision (nothing silent).

Three lanes, per the project's OCR strategy:

  * born-digital  → pdfminer / text-layer extraction (FREE, exact). A PDF with a
    real text layer is never OCR'd; DRILLPDFse's pdfminer route recovers its
    math as gold. Wins even for a huge book — a text layer beats any page count.
  * scanned, small (≤ gemma_max pages) → Gemma 4 (Novita), ~50s/page, 5-parallel
    adaptive prompt. Great on small documents.
  * scanned, large (> gemma_max) → MathPix — the only viable OCR for large books.

Unknown page count on a scan defaults to MathPix (the safe choice for a possibly
large book). `choose_route` is PURE; `format_decision` renders one line.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Default scanned-doc cutoff between Gemma (small) and MathPix (large).
GEMMA_MAX_PAGES = 20


@dataclass(frozen=True)
class RouteDecision:
    lane: str        # born_digital | gemma | mathpix | unknown
    reason: str      # why this lane (the classifying signal)
    command: str     # the concrete pdfdrill command that runs this lane
    cost: str        # free | keyed | paid | none


def choose_route(*, text_layer: Optional[bool], needs_ocr: Optional[bool],
                 page_count: Optional[int], gemma_max: int = GEMMA_MAX_PAGES
                 ) -> RouteDecision:
    """Pick the OCR/extraction lane from the `size` signals. Pure."""
    pc = page_count or 0
    # A real text layer wins outright — free, exact, no OCR (any size).
    if text_layer:
        return RouteDecision(
            lane="born_digital",
            reason=f"born-digital (has a text layer, {pc or '?'} pages)",
            command="pdfdrill model  (text-layer extraction; DRILLPDFse pdfminer "
                    "recovers the math as gold)",
            cost="free")
    # Not classified yet (size never ran).
    if not needs_ocr and text_layer is None:
        return RouteDecision(
            lane="unknown",
            reason="not classified — run `pdfdrill size` to detect text-layer vs scan",
            command="pdfdrill size <pdf>",
            cost="none")
    # A scan: split by page count.
    if needs_ocr:
        if pc and pc <= gemma_max:
            return RouteDecision(
                lane="gemma",
                reason=f"scanned, {pc} pages (≤{gemma_max}) — small enough for Gemma",
                command="pdfdrill visionocr  (Gemma 4 via Novita, 5-parallel, "
                        "adaptive prompt)",
                cost="keyed")
        if pc > gemma_max:
            return RouteDecision(
                lane="mathpix",
                reason=f"scanned, {pc} pages (>{gemma_max}) — the large-book lane",
                command="pdfdrill mathpix <pdf> --force",
                cost="paid")
        # scan with unknown page count → MathPix (safe for a possibly-large book)
        return RouteDecision(
            lane="mathpix",
            reason="scanned, page count unknown — assuming large; MathPix is the "
                   "safe lane (run `size` to enable the Gemma small-doc route)",
            command="pdfdrill mathpix <pdf> --force",
            cost="paid")
    # text_layer explicitly False but needs_ocr False (shouldn't happen) → unknown
    return RouteDecision(
        lane="unknown",
        reason="ambiguous classification — run `pdfdrill size`",
        command="pdfdrill size <pdf>",
        cost="none")


_LANE_LABEL = {
    "born_digital": "born-digital → pdfminer/text-layer",
    "gemma": "scanned → Gemma 4",
    "mathpix": "scanned → MathPix",
    "unknown": "unclassified",
}


def format_decision(d: RouteDecision, name: str) -> str:
    """One human line: `<name>: <lane label> (<cost>) — <reason>. Next: <cmd>`."""
    return (f"{name}: {_LANE_LABEL.get(d.lane, d.lane)} [{d.cost}] — {d.reason}.\n"
            f"  Next: {d.command}")


def route_for_sidecar(sc) -> RouteDecision:
    """Build a decision from a Sidecar's `size` evidence (text_layer / needs_ocr /
    page_count). Works before `size` too (fields absent → unknown)."""
    return choose_route(
        text_layer=sc.get_evidence("text_layer"),
        needs_ocr=sc.get_evidence("needs_ocr"),
        page_count=sc.get_evidence("pages", 0))
