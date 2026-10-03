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


# A scan is one full-page image per page. Below this share of the page area an
# image is a figure, not a page scan.
_PAGE_IMAGE_COVER = 0.85
# …and it has to hold for most pages: a book with a full-page cover plate or two
# is not a scanned book.
_SCAN_PAGE_SHARE = 0.8


def scan_page_set(images, page_count, page_w, page_h) -> set:
    """The pages that ARE a page-covering image. One implementation, used both
    by the scan test below and by R5's render-mode sample — a second copy of
    "which pages are the scan" is a second thing to keep in step."""
    if not images or not page_count or page_w <= 0 or page_h <= 0:
        return set()
    page_area = page_w * page_h
    return {img.get("page") for img in images
            if (float(img.get("w_pt") or 0) * float(img.get("h_pt") or 0))
            >= _PAGE_IMAGE_COVER * page_area}


def is_scanned_page_images(images, page_count, page_w, page_h) -> bool:
    """True if the document looks like a SCAN from its image geometry alone.

    Source-independent, and deliberately not a text test: a scan that someone
    already ran OCR over HAS a text layer — made of that OCR — so presence of
    text cannot distinguish "born-digital" from "scan with an OCR underlay".
    Page geometry can: a scan carries one image covering essentially the whole
    page, on essentially every page.

    `images` are dicts with `page`, `w_pt`, `h_pt` (points).
    """
    if not page_count:
        return False
    return len(scan_page_set(images, page_count, page_w, page_h)) \
        >= _SCAN_PAGE_SHARE * page_count


def choose_route(*, text_layer: Optional[bool], needs_ocr: Optional[bool],
                 page_count: Optional[int], gemma_max: int = GEMMA_MAX_PAGES,
                 scanned_images: Optional[bool] = None) -> RouteDecision:
    """Pick the OCR/extraction lane from the `size` signals. Pure.

    `scanned_images` (from `is_scanned_page_images`) overrides a text layer that
    is really an OCR underlay on a scan — otherwise the free text-layer lane is
    offered for a document whose "text" is somebody else's OCR output, described
    as "free and exact". Omitted → previous behaviour, unchanged.
    """
    pc = page_count or 0
    # A text layer sitting on full-page scans is an OCR UNDERLAY, not a born-digital
    # text layer: extracting it re-serves that OCR (and never recovers math).
    if text_layer and scanned_images:
        needs_ocr, text_layer = True, False
    # A real text layer wins outright — free, exact, no OCR (any size).
    if text_layer:
        return RouteDecision(
            lane="born_digital",
            reason=f"born-digital (has a text layer, {pc or '?'} pages)",
            command="pdfdrill model  (text-layer extraction via pdfminer — free "
                    "and exact; no OCR)",
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


def scan_pages_for(pdf, page_count) -> list:
    """The scan pages, from `pdfimages -list`. Shares `scan_page_set` with the
    scan test, so the two cannot disagree about which pages the scan is on."""
    try:
        imgs, pw, ph = _images_and_page_size(pdf)
        return sorted(p for p in scan_page_set(imgs, page_count, pw, ph) if p)
    except Exception:                                        # noqa: BLE001
        return []


def _images_and_page_size(pdf):
    from pathlib import Path as _P

    from .font_image_layers import fetch_pdfimages_list
    from .pdfinfo_layers import fetch_pdfinfo_struct
    info = fetch_pdfinfo_struct(_P(pdf)) or {}
    pw, ph = _page_size_pt(info)
    imgs = []
    for r in fetch_pdfimages_list(pdf) or []:
        xppi = float(r.get("x_ppi") or 0) or 72.0
        yppi = float(r.get("y_ppi") or 0) or 72.0
        imgs.append({"page": r.get("page"),
                     "w_pt": float(r.get("width_px") or 0) / xppi * 72.0,
                     "h_pt": float(r.get("height_px") or 0) / yppi * 72.0})
    return imgs, pw, ph


def font_names_for(pdf) -> list:
    """Embedded font names, from poppler's `pdffonts`."""
    import subprocess
    try:
        out = subprocess.run(["pdffonts", str(pdf)], capture_output=True,
                             text=True, timeout=60).stdout
    except Exception:                                        # noqa: BLE001
        return []
    return [l.split()[0] for l in out.splitlines()[2:] if l.split()]


def scanned_images_for(pdf, page_count) -> "Optional[bool]":
    """Ask `pdfimages -list` whether this document is one full-page image per page.

    Cheap and offline (poppler). Returns None when the tool or a page size is
    unavailable, so the caller falls back to the previous text-layer decision
    rather than guessing.
    """
    try:
        imgs, pw, ph = _images_and_page_size(pdf)
        if not (pw and ph):
            return None
        return is_scanned_page_images(imgs, page_count, pw, ph)
    except Exception:                                        # noqa: BLE001
        return None


def _page_size_pt(info: dict) -> "tuple[float, float]":
    """Page width/height in points from a pdfinfo dict ('612 x 792 pts')."""
    import re
    m = re.search(r"([\d.]+)\s*x\s*([\d.]+)\s*pts",
                  str(info.get("page_size") or info.get("Page size") or ""))
    return (float(m.group(1)), float(m.group(2))) if m else (0.0, 0.0)


def route_for_sidecar(sc) -> RouteDecision:
    """Build a decision from a Sidecar's `size` evidence (text_layer / needs_ocr /
    page_count). Works before `size` too (fields absent → unknown)."""
    pages = sc.get_evidence("pages", 0)
    text_layer = sc.get_evidence("text_layer")
    # Only worth asking when a text layer claims the free lane — that is the one
    # decision an OCR underlay can silently corrupt.
    scanned = scanned_images_for(sc.pdf_path, pages) if text_layer else None
    return choose_route(
        text_layer=text_layer,
        needs_ocr=sc.get_evidence("needs_ocr"),
        page_count=pages,
        scanned_images=scanned)


# ---------------------------------------------------------------------------
# R5 (CR-pdfminer-single-version) — RENDER MODE IN THE SCAN TRIAGE.
#
# The lane was already right: `is_scanned_page_images` sends all three of
# psred's scan fixtures to the scanned lane. What the triage could not say is
# WHICH KIND of scan it is — `scan_only` (no text at all) and
# `scan_ocr_invisible` (154 characters of someone's OCR, drawn invisibly over
# the raster) were reported identically, as "scanned, 1 pages".
#
# That distinction decides whether a text layer exists to be re-served, and
# the obvious test for it does not work: Tesseract's `GlyphLessFont` names
# only Tesseract. `scan_ocr_invisible.pdf` carries its OCR in CMR10 and no
# font name betrays it. What does is the PDF text rendering mode — `Tr 3`
# (neither fill nor stroke) and `Tr 7` (clip only) put no marks on the page,
# which is how an OCR layer is written over a page image.
#
# The rule is psred's, unchanged, so both sides answer the same question the
# same way (`psred/preflight.py:check`).
# ---------------------------------------------------------------------------

#: Text rendering modes that draw nothing.
INVISIBLE_MODES = (3, 7)

#: At most this many scan pages are sampled; pages 1-2 are added for context.
_SAMPLE_SCAN_PAGES = 5


def render_mode_counts(pdf, pages):
    """{render mode: characters drawn} over the given 1-based pages, or None.

    `{}` and `None` are DIFFERENT ANSWERS and the caller depends on it: an
    empty dict means the pages were read and carry no text, which is exactly
    what a scan with no OCR layer looks like; `None` means the reading itself
    failed and nothing is known. Collapsing them would report "no OCR layer"
    for a document nobody could read — absent reported as false.

    Read from the TEXT STATE rather than from `LTChar.render_mode`, so it works
    on a stock pdfminer too; the patched build carries the same value. This
    runs on documents the triage has already called scanned, so it must not
    depend on the fork being installed.
    """
    import collections
    pages = {int(p) for p in pages if p}
    if not pages:
        return {}
    try:
        from pdfminer.converter import PDFLayoutAnalyzer
        from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
        from pdfminer.pdfpage import PDFPage
    except Exception:                                        # noqa: BLE001
        return None
    cnt: "collections.Counter" = collections.Counter()

    class _Dev(PDFLayoutAnalyzer):
        def render_string(self, textstate, seq, ncs, graphicstate):
            self._tr = textstate.render
            return super().render_string(textstate, seq, ncs, graphicstate)

        def render_char(self, *a, **k):
            cnt[getattr(self, "_tr", 0)] += 1
            return super().render_char(*a, **k)

    try:
        rm = PDFResourceManager()
        dev = _Dev(rm)
        last = max(pages)
        with open(pdf, "rb") as fh:
            for i, page in enumerate(PDFPage.get_pages(fh), 1):
                if i in pages:
                    PDFPageInterpreter(rm, dev).process_page(page)
                if i >= last:
                    break
    except Exception:                                        # noqa: BLE001
        # A reader failure must not stop the triage, and must not be reported
        # as "no OCR layer" either.
        return None
    return dict(cnt)


def ocr_layer_for(pdf, *, scan_pages, page_count, font_names=(),
                  scanned=None) -> dict:
    """Does this document carry an OCR text layer? psred's rule, unchanged.

    Returns a dict rather than a bool, because "no" and "could not tell" are
    different answers and the triage must not print the first when it means
    the second.
    """
    scan_pages = sorted(int(p) for p in (scan_pages or ()) if p)
    glyphless = any("GlyphLessFont" in (n or "") for n in font_names)
    sample = set(scan_pages[:_SAMPLE_SCAN_PAGES]) | {
        p for p in (1, 2) if page_count and p <= page_count}
    modes = render_mode_counts(pdf, sample) if sample else {}
    readable = modes is not None
    modes = modes or {}
    # Counted on the SCAN pages only: pages 1-2 are sampled for context and a
    # title page of real text there would dilute the share.
    scan_modes = (render_mode_counts(pdf, scan_pages[:_SAMPLE_SCAN_PAGES])
                  if scan_pages and readable else {}) or {}
    scan_invis = sum(n for m, n in scan_modes.items() if m in INVISIBLE_MODES)
    scan_total = sum(scan_modes.values())
    invisible_majority = scan_total > 0 and scan_invis * 2 >= scan_total
    has_text = bool(font_names)
    if scanned is None:
        scanned = bool(scan_pages) and page_count and \
            len(scan_pages) >= _SCAN_PAGE_SHARE * page_count
    why = []
    if glyphless:
        why.append("a GlyphLessFont (Tesseract's OCR font)")
    if invisible_majority:
        why.append(f"{scan_invis} of {scan_total} characters on the scan pages "
                   f"are invisible (render mode 3/7)")
    if scanned and has_text and not (glyphless or invisible_majority):
        why.append("a text layer on a scan, which is somebody's OCR output")
    return {
        "ocr_layer": bool(glyphless or invisible_majority
                          or (scanned and has_text)),
        "glyphless_font": glyphless,
        "invisible_chars": scan_invis,
        "chars_on_scan_pages": scan_total,
        "pages_sampled": sorted(sample),
        "modes": modes,
        # KNOWN means the question was answered, not that the answer was yes.
        # A scan we could read that carries no text at all is a DEFINITE "no
        # OCR layer" — reporting that as unknown was the first version's bug,
        # and it left `scan_only.pdf` with nothing said about it.
        "known": readable or glyphless or bool(font_names),
        "why": why,
    }
