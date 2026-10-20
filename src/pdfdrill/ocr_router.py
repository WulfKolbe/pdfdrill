"""
The LANE CONTRACT — which reading pdfdrill uses for a document, decided once,
in one pure function, and reported in the same words by `route`, `drill` and
`doctor`.

Five lanes, in a FIXED ORDER. The order is the contract: a lane is taken only
because every cheaper one above it is unavailable, so the same document always
gets the same answer and the answer never depends on who asked.

  1. born_digital  — the PDF carries its OWN text layer (and is not a scan with
     somebody's OCR underlaid). FREE and exact: the glyphs are the author's,
     with their coordinates. Wins at any page count — a text layer beats a page
     count. On an arXiv document the author's LaTeX merges into it, so this lane
     gives geometry AND gold math.
  2. source        — no text layer, but the document is an arXiv e-print, so the
     author's LaTeX is downloadable once and free. Gold structure and gold math;
     no page geometry of its own (see `geometry`).
  3. gemma         — a scan, and a Makora/Novita key is present. METERED, at a
     measured 0.000718 EUR per printed page, refused against
     PDFDRILL_OCR_BUDGET_EUR before the first call.
  4. mathpix       — a scan, no Makora key, a MathPix key present. PAID, and the
     richest reading there is; it is lane 4 and not lane 3 because gemmaocr
     measured 88% of its boxes on penev_A at about a fortieth of the price.
  5. geometry      — a scan and NO reading key at all: the sandbox's default.
     The layout detector is offline and free, so the page's STRUCTURE can still
     be had — a lines.json of typed boxes with no text in them — without a word
     being read. What it does not give is the words, and it says so. `model` is
     not its consumer (a model keeps what has prose); `linescmp`,
     `geometry --layout` and the detector cache are.

OCR IS THE LAST RESORT, NOT THE FIRST. Lanes 3-5 are reached only when the
document has neither a text layer of its own nor an author's source. That is
the whole of the rule the previous version got wrong in two ways: it offered
MathPix (paid) above the free source lane, and it split the scan lanes by page
count — "> 20 pages means MathPix" — a threshold set when the only alternative
to MathPix was a 50 s/page vision call, and left standing after gemmaocr made
the large book the CHEAP case.

`choose_route` is PURE: it reads no file and makes no call. Everything it needs
is passed in, which is why `PDFDRILL_SANDBOX=1` can ask a keyed machine what
the keyless one will do and get a true answer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Lane names, in contract order. The tuple IS the order — a reader deciding
# whether a lane is "above" another must not have to read the function.
LANES = ("born_digital", "source", "gemma", "mathpix", "geometry")

#: What a lane costs. `metered` is its own answer and not a synonym for `paid`:
#: gemmaocr's rate is MEASURED (0.000718 EUR per printed page over 390 pages)
#: and guarded by a budget, so a caller can decide; MathPix's is not.
COSTS = ("free", "metered", "paid", "none")

#: The reading keys a lane can need. `route_for_sidecar` fills this from the
#: environment; a test passes it literally.
MATHPIX_KEY = "mathpix"
GEMMA_KEY = "gemma"


def keys_present() -> frozenset:
    """Which reading keys this install has. Honours `PDFDRILL_SANDBOX=1`, so the
    answer is the one the sandbox would give."""
    from .env import get
    out = set()
    if get("MATHPIX_APP_ID") and get("MATHPIX_APP_KEY"):
        out.add(MATHPIX_KEY)
    if get("MAKORA_API_KEY") or get("NOVITA_API_KEY"):
        out.add(GEMMA_KEY)
    return frozenset(out)


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
                 page_count: Optional[int],
                 scanned_images: Optional[bool] = None,
                 arxiv_source: Optional[bool] = None,
                 keys: Optional[frozenset] = None,
                 detector: Optional[bool] = None) -> RouteDecision:
    """Pick the lane. PURE — see the module docstring for the contract.

    `scanned_images` (from `is_scanned_page_images`) overrides a text layer that
    is really an OCR underlay on a scan: extracting it re-serves somebody
    else's reading and never recovers math, so it is not the free lane it looks
    like.

    `arxiv_source` — the document is an arXiv e-print, so the author's LaTeX is
    free (downloaded once, cached). `keys` — the reading keys present
    (`keys_present()`). `detector` — whether the layout detector is installed,
    which is what makes lane 5 worth offering.

    Every optional argument defaults to the ANSWER THAT ASSUMES LEAST: no
    source, no keys, no detector. A caller that knows nothing is told to use
    the free lanes, never to spend.
    """
    pc = page_count or 0
    keys = frozenset(keys or ())
    # A text layer sitting on full-page scans is an OCR UNDERLAY, not a born-digital
    # text layer: extracting it re-serves that OCR (and never recovers math).
    underlay = bool(text_layer and scanned_images)
    if underlay:
        needs_ocr, text_layer = True, False

    # 0 — not classified yet. `size` is free and cheap and decides everything
    # below, so it is never guessed around.
    if text_layer is None and not needs_ocr:
        return RouteDecision(
            lane="unknown",
            reason="not classified — `size` reads the page count and whether "
                   "there is a text layer, and every lane below turns on that",
            command="pdfdrill size <pdf>",
            cost="none")

    # 1 — THE PDF'S OWN TEXT. Free, exact, and it carries coordinates.
    if text_layer:
        if arxiv_source:
            return RouteDecision(
                lane="born_digital",
                reason=f"born-digital, {pc or '?'} pages, and an arXiv e-print — "
                       f"the text layer gives the geometry, the author's LaTeX "
                       f"gives the structure and the math, and `model` merges "
                       f"both. No OCR, nothing to pay",
                command="pdfdrill model <pdf>   (free: own text layer + the "
                        "author's LaTeX)",
                cost="free")
        return RouteDecision(
            lane="born_digital",
            reason=f"born-digital (its own text layer, {pc or '?'} pages) — free "
                   f"and exact at any page count; a text layer beats a page count",
            command="pdfdrill model <pdf>   (free: the PDF's own text layer)",
            cost="free")

    # 2 — THE AUTHOR'S SOURCE. A scan with no text of its own, but an arXiv id:
    # the e-print is gold and free. OCR would be reading a worse copy of a
    # document we can have the source of.
    if arxiv_source:
        return RouteDecision(
            lane="source",
            reason=f"no text layer, but an arXiv e-print is available ({pc or '?'} "
                   f"pages) — the author's LaTeX is gold and free, so there is "
                   f"nothing for OCR to add but geometry",
            command="pdfdrill model <pdf>   (free: the author's LaTeX e-print)",
            cost="free")

    # 3-5 — ONLY NOW is this an OCR document: no text of its own, no source.
    if needs_ocr or text_layer is False:
        if GEMMA_KEY in keys:
            return RouteDecision(
                lane="gemma",
                reason=f"a scan with no text layer and no author's source, "
                       f"{pc or '?'} sheets — the model lane reads it at a "
                       f"measured 0.000718 EUR per printed page, and refuses "
                       f"against PDFDRILL_OCR_BUDGET_EUR before the first call",
                command="pdfdrill gemmaocr <pdf>   (METERED; add --nup 1 if the "
                        "sheets are not imposed)",
                cost="metered")
        if MATHPIX_KEY in keys:
            return RouteDecision(
                lane="mathpix",
                reason=f"a scan with no text layer, no author's source and no "
                       f"MAKORA_API_KEY, {pc or '?'} pages — MathPix is the "
                       f"reading that is left, and it is the richest one",
                command="pdfdrill mathpix <pdf>   (PAID)",
                cost="paid")
        if detector is False:
            return RouteDecision(
                lane="geometry",
                reason=f"a scan with no text layer, no author's source and no "
                       f"reading key, {pc or '?'} pages — and no layout detector "
                       f"either, so there is no free lane on this install",
                command="set MAKORA_API_KEY (metered, cheapest) or "
                        "MATHPIX_APP_ID/KEY, or install the detector "
                        "(PDFDRILL_YOLO_PYTHON; `pdfdrill doctor`) for the free "
                        "geometry-only lane",
                cost="none")
        return RouteDecision(
            lane="geometry",
            reason=f"a scan with no text layer, no author's source and no "
                   f"reading key, {pc or '?'} pages — so the words cannot be had "
                   f"for free, but the STRUCTURE can: the layout detector is "
                   f"offline and free, and gives a lines.json in which every "
                   f"line has a box and a type and no text, to score with "
                   f"`linescmp` or lay on a model with `geometry --layout`",
            command="pdfdrill gemmaocr <pdf> --geometry-only   (FREE, offline: "
                    "boxes and types, no words)",
            cost="free")

    # text_layer is False and needs_ocr is False — the two signals disagree.
    return RouteDecision(
        lane="unknown",
        reason="the text-layer and scan signals disagree — re-run `size`",
        command="pdfdrill size <pdf>",
        cost="none")


_LANE_LABEL = {
    "born_digital": "born-digital → its own text layer",
    "source": "no text layer → the author's LaTeX",
    "gemma": "scanned → the model lane (gemmaocr)",
    "mathpix": "scanned → MathPix",
    "geometry": "scanned, keyless → geometry only",
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


def arxiv_source_for(pdf, sc) -> bool:
    """Is the author's LaTeX reachable for this document? True iff an arXiv id is
    known for it — the e-print is then one cached download away, and free.

    Asked here rather than inside `choose_route` because the decision function
    is pure: this is the one lookup that touches the filename and the sidecar.
    """
    try:
        from .commands import _arxiv_id_for
        return bool(_arxiv_id_for(pdf, sc))
    except Exception:                                        # noqa: BLE001
        return False


def detector_available() -> "Optional[bool]":
    """Is the layout detector installed? None when the question itself failed."""
    try:
        from . import yololayout
        return bool(yololayout.available())
    except Exception:                                        # noqa: BLE001
        return None


def route_for_sidecar(sc) -> RouteDecision:
    """Build a decision from a Sidecar's `size` evidence (text_layer / needs_ocr /
    page_count) plus the three install facts the contract turns on: the author's
    source, the reading keys, the detector. Works before `size` too (fields
    absent → unknown)."""
    pages = sc.get_evidence("pages", 0)
    text_layer = sc.get_evidence("text_layer")
    # Only worth asking when a text layer claims the free lane — that is the one
    # decision an OCR underlay can silently corrupt.
    scanned = scanned_images_for(sc.pdf_path, pages) if text_layer else None
    return choose_route(
        text_layer=text_layer,
        needs_ocr=sc.get_evidence("needs_ocr"),
        page_count=pages,
        scanned_images=scanned,
        arxiv_source=arxiv_source_for(sc.pdf_path, sc),
        keys=keys_present(),
        detector=detector_available())


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
