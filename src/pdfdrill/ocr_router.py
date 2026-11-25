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
  3. gemma         — a scan, and the model lane can be reached. ONE lane, two
     hosts of the same model, and the cost is the host's: a LOCAL Ollama host
     answers for nothing (no key, no account, nothing metered — the free half
     of this lane, and the reason the keyless install is not confined to lane
     5 any more), and failing that a Makora/Novita key makes it METERED, at a
     measured 0.000718 EUR per printed page, refused against
     PDFDRILL_OCR_BUDGET_EUR before the first call. Same command, same reader,
     same artefact; `route` says which host and what it costs.
  4. mathpix       — a scan, no local host and no Makora key, a MathPix key
     present. PAID, and the
     richest reading there is; it is lane 4 and not lane 3 because gemmaocr
     measured 88% of its boxes on penev_A at about a fortieth of the price.
  5. geometry      — a scan, no local host and NO reading key at all: the
     sandbox's default.
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


def local_reader_present() -> bool:
    """Whether the model lane can be reached with NO KEY AT ALL: the same
    Gemma-4 on a local Ollama host, which charges nothing.

    It is not a key, so it is not in `keys_present()` — a set called `keys`
    whose members are not keys is how the sandbox answer stops being true. It
    is a TOOL, like poppler and the layout detector, and like them it is
    reported by `doctor` and asked for rather than assumed. Honours
    `PDFDRILL_SANDBOX=1` (the sandbox has no such host), so a keyed machine
    can still ask what the keyless one will do.
    """
    from . import ollama_client
    return ollama_client.available()


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
    #: T-0153 — THE DOCUMENT HAS A TEXT LAYER THAT THIS LANE DOES NOT BUY.
    #: A scan with somebody else's OCR underlaid. The lane ignores it for the
    #: purpose of CHOOSING a lane (it is not our reading and it never carries
    #: maths), and this module's own comment already says the layer "is also
    #: the most useful fact about the document". It was said only in prose, so
    #: `drill` could not act on it: it read "this lane buys nothing" as "this
    #: document has no reading" and dropped 5,652-7,538 free characters a page
    #: on three board pages. The fact is now ON the decision, and
    #: `free_reading_for` is the one place that turns it into a step.
    underlay: bool = False


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
                 detector: Optional[bool] = None,
                 ink: Optional[bool] = None,
                 local_reader: Optional[bool] = None) -> RouteDecision:
    """Pick the lane. PURE — see the module docstring for the contract.

    `scanned_images` (from `is_scanned_page_images`) overrides a text layer that
    is really an OCR underlay on a scan: extracting it re-serves somebody
    else's reading and never recovers math, so it is not the free lane it looks
    like.

    `arxiv_source` — the document is an arXiv e-print, so the author's LaTeX is
    free (downloaded once, cached). `keys` — the reading keys present
    (`keys_present()`). `detector` — whether the layout detector is installed,
    which is what TYPES lane 5's lines. `ink` — whether the ink half can run at
    all (`ink_available()`, i.e. NumPy), which is what FINDS them; `None` asks
    the install. The two are not interchangeable: no detector is a weaker lane,
    no ink is no lane.

    `local_reader` — the model lane on a LOCAL host (`local_reader_present()`),
    which needs no key and costs nothing. Asking costs a round trip, so this
    function does not ask: the caller does (`route_for_sidecar`), and `None`
    means no local host. It outranks the metered and paid routes for the one
    reason the contract already orders lanes by — free before metered before
    paid — and the lane it serves is the SAME lane 3, not a sixth lane: the
    same command, the same reader, the same artefact, read by a host that
    charges nothing.

    Every optional argument defaults to the ANSWER THAT ASSUMES LEAST: no
    source, no keys, no detector, no local host. A caller that knows nothing
    is told to use the free lanes, never to spend.
    """
    pc = page_count or 0
    keys = frozenset(keys or ())
    # A text layer sitting on full-page scans is an OCR UNDERLAY, not a born-digital
    # text layer: extracting it re-serves that OCR (and never recovers math).
    underlay = bool(text_layer and scanned_images)
    if underlay:
        needs_ocr, text_layer = True, False

    # HOW THE DOCUMENT'S OWN TEXT IS DESCRIBED, said once for the five OCR
    # lanes below. With an underlay they must NOT say "no text layer": `size`
    # prints "has a text layer" for the same document, and that contradiction
    # cost two sessions a morning on 2026-11-02 — both read `route` saying "a
    # scan with no text layer" about an ABBYY file, concluded the page-image
    # test was missing, and set out to add one that has been here for months
    # (`is_scanned_page_images`, _PAGE_IMAGE_COVER 0.85 of the page area on
    # _SCAN_PAGE_SHARE 0.8 of the pages). The layer is real. It is somebody
    # else's reading, and the lane ignores it on purpose; saying so is the
    # whole point, because it is also the most useful fact about the document.
    #: T-0153 — AND IT IS NOT IGNORED ANY MORE, SO IT MAY NOT SAY SO.
    #: The incident above was `route` DENYING a layer that `size` reported;
    #: that stays fixed, because the sentence still names the layer. What
    #: changed is the second half: the layer's characters are in the file and
    #: cost nothing, so `drill` reads them (`free_reading_for`). The part of
    #: the old sentence worth keeping is the part that is still true — it is
    #: somebody else's reading and it never recovers the mathematics.
    scan_text = ("a scan whose only text is an OCR UNDERLAY — somebody "
                 "else's reading, and it never recovers the maths"
                 if underlay else "a scan with no text layer")
    #: ...AND WHAT IS DONE WITH IT IS THE LANE'S OWN CLAUSE, NOT THIS ONE.
    #: The first version of this change appended "so they ARE read" to the
    #: shared sentence, which made it true on the geometry lane and false on
    #: `gemma` and `mathpix`, where `drill` runs no lane at all and reads
    #: nothing. `test_every_scanned_lane_reports_the_underlay_instead_of
    #: _denying_the_text` caught it, which is what that test is for.
    reads_it = (" — and its characters are free and already in the file, "
                "so they ARE read (`glyphlines`)" if underlay else "")
    #: ...ON EVERY LANE AN UNDERLAY CAN REACH, which is all of 3-5 except the
    #: install that has no lane. See `free_reading_for`.

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
        if local_reader:
            return RouteDecision(
                lane="gemma",
                underlay=underlay,
                reason=f"{scan_text} and no author's source, "
                       f"{pc or '?'} sheets — the model lane reads it on a "
                       f"LOCAL host, so it costs nothing: no key, no account, "
                       f"nothing metered and no budget to refuse against"
                       f"{reads_it}",
                command="pdfdrill gemmaocr <pdf>   (FREE: a local host; add "
                        "--nup 1 if the sheets are not imposed)",
                cost="free")
        if GEMMA_KEY in keys:
            return RouteDecision(
                lane="gemma",
                underlay=underlay,
                reason=f"{scan_text} and no author's source, "
                       f"{pc or '?'} sheets — the model lane reads it at a "
                       f"measured 0.000718 EUR per printed page, and refuses "
                       f"against PDFDRILL_OCR_BUDGET_EUR before the first call{reads_it}",
                command="pdfdrill gemmaocr <pdf>   (METERED; add --nup 1 if the "
                        "sheets are not imposed)",
                cost="metered")
        if MATHPIX_KEY in keys:
            return RouteDecision(
                lane="mathpix",
                underlay=underlay,
                reason=f"{scan_text}, no author's source and no "
                       f"MAKORA_API_KEY, {pc or '?'} pages — MathPix is the "
                       f"reading that is left, and it is the richest one{reads_it}",
                command="pdfdrill mathpix <pdf>   (PAID)",
                cost="paid")
        # THE INK IS THE LANE'S FLOOR, AND THE CHECK WAS IN THE WRONG PLACE.
        # 905p put it inside `if detector is False`, so it only ran on the
        # install that had neither half. With the detector present and NumPy
        # absent — which is exactly a `pip install -e .` that predates numpy
        # becoming a base dep, on a machine whose detector is a separate
        # interpreter — the route fell through to the branch below and promised
        # "a box and a type" on every line. Measured on hilbert10 in a
        # numpy-free venv: route said `[free]`, `drill` rendered 10 PNGs
        # (8.58 MB) and then died in the ink with exit 0 and no lines.json.
        #
        # The halves are not symmetric: the ink FINDS the lines, the detector
        # TYPES them. No detector is a weaker lane; no ink is NO LANE, whatever
        # the detector can do. So the ink is asked first, for both branches.
        if (ink_available() if ink is None else ink) is False:
            return RouteDecision(
                lane="geometry",
                underlay=underlay,
                reason=f"{scan_text}, no author's source and no "
                       f"reading key, {pc or '?'} pages — and no NumPy, which "
                       f"is the geometry lane's ink half (it FINDS the lines; "
                       f"the detector only types them), so there is no free "
                       f"lane on this install",
                command="`pip install numpy` (it is a BASE dependency — re-run "
                        "`pip install -e .` or `bash bootstrap.sh`), or set "
                        "MAKORA_API_KEY (metered, cheapest) or "
                        "MATHPIX_APP_ID/KEY (`pdfdrill doctor`)",
                cost="none")
        if detector is False:
            # MEASURED, after the first version of this branch said "there is no
            # free lane on this install" and `drill` then produced 355 boxed
            # lines on hilbert10 in 6.6 s anyway: without the detector the lane
            # still runs on the page's own INK, which needs nothing but numpy.
            # What it loses is the TYPES — every line comes out `text`, so a
            # figure is ink rows rather than one object. That is a weaker lane,
            # not an absent one, and the honest answer is to say which half is
            # missing.
            return RouteDecision(
                lane="geometry",
                underlay=underlay,
                reason=f"{scan_text}, no author's source and no "
                       f"reading key, {pc or '?'} pages — and no layout detector "
                       f"either, so the page's own INK gives the lane: every "
                       f"printed line gets a box and NO type (a figure arrives "
                       f"as its ink rows, not as one object) and no text. Free, "
                       f"and about 6x faster than the typed lane. Set "
                       f"PDFDRILL_YOLO_PYTHON to get the types{reads_it}",
                command="pdfdrill gemmaocr <pdf> --geometry-only   (FREE, "
                        "offline: boxes, no types, no words)",
                cost="free")
        return RouteDecision(
            lane="geometry",
            underlay=underlay,
            reason=f"{scan_text}, no author's source and no "
                   f"reading key, {pc or '?'} pages — so the words cannot be had "
                   f"for free, but the STRUCTURE can: the layout detector is "
                   f"offline and free, and gives a lines.json in which every "
                   f"line has a box and a type and no text, to score with "
                   f"`linescmp` or lay on a model with "
                   f"`geometry --layout`{reads_it}",
            command="pdfdrill gemmaocr <pdf> --geometry-only   (FREE, offline: "
                    "boxes and types, no words)",
            cost="free")

    # text_layer is False and needs_ocr is False — the two signals disagree.
    return RouteDecision(
        lane="unknown",
        reason="the text-layer and scan signals disagree — re-run `size`",
        command="pdfdrill size <pdf>",
        cost="none")


def free_reading_for(d: RouteDecision) -> "Optional[str]":
    """Which FREE reader `drill` runs for this decision — or None.

    The lane contract answers which reading to BUY. This answers a different
    question the contract never asked: are there CHARACTERS ALREADY IN THE
    FILE that cost nothing to read? Two lanes have them.

      born_digital   the author's own glyphs, with their coordinates.
      an UNDERLAY    a scan carrying somebody's OCR, WHATEVER LANE IT TOOK.
                     Not our reading and no maths in it, but 5,652-7,538
                     characters a page on the three board pages that found
                     this, free, offline, no key.

    Everything else answers None, and the difference matters in both
    directions:

      geometry, no underlay   there is nothing to read. The lane measures the
                              page and SAYS it read no words; inventing them
                              here is the defect docs/LANES.md exists to
                              prevent.
      geometry, cost="none"   there is no lane at all (no NumPy, the ink
                              half). Rendering for a reading that cannot
                              happen is work the user gets nothing for.
      source                  no text layer, so no glyphs. The author's LaTeX
                              IS the reading and `model` takes that lane.
      gemma / mathpix         ...only when there is no underlay. A reading
                              that was already BOUGHT is never replaced (that
                              guard is the caller's, `reading_producer`), but
                              a lane that merely EXISTS buys nothing: `drill`
                              never runs a metered or paid lane, so keying the
                              free reading to the lane would leave the layer
                              unread on exactly the machines that have keys.

    THE FIRST VERSION OF THIS FUNCTION GOT THAT WRONG, and the acceptance run
    hid it. It read `lane == "geometry" and underlay`, and the three board
    pages passed byte-identical — under `PDFDRILL_SANDBOX=1`, which answers
    as the KEYLESS install. Asked with the real environment, where a
    MAKORA_API_KEY is present, all three route to `gemma` and the function
    answered None: the fix would not have fired on the owner's own machine.
    A sandbox pass is not a pass on the install the user has.
      unknown                 `size` has not run.

    PURE, like `choose_route`: it reads no file and makes no call, so the
    decision `drill` acts on can be asserted without a PDF.
    """
    if d.lane == "born_digital":
        return "glyphlines"
    #: `cost="none"` is the one case an underlay cannot help: it means this
    #: install has no lane for this document at all (no NumPy), and the glyph
    #: reader is not the missing half -- it reads the text layer and never
    #: touches the ink. It is excluded because that branch's whole point is
    #: that NOTHING is run and nothing is rendered, and because the lane note
    #: there tells the user to fix the install first.
    if d.underlay and d.cost != "none":
        return "glyphlines"
    return None


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


def ink_available() -> "Optional[bool]":
    """Can the ink route run at all? It is `inkbox`, and `inkbox` is NumPy.

    None when the question itself failed, matching `detector_available`: a
    caller that could not ask is not told "no".
    """
    try:
        import importlib.util
        return importlib.util.find_spec("numpy") is not None
    except Exception:                                        # noqa: BLE001
        return None


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
        detector=detector_available(),
        ink=ink_available(),
        local_reader=local_reader_present())


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
