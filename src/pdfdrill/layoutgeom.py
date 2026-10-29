r"""The OCR path used for NOTHING BUT GEOMETRY — the detector's boxes put on a
model that was built from something else.

WHY THIS EXISTS
---------------
A model built from the author's LaTeX knows what every object IS and has never
seen a rendered page. A model built from the PDF's own text layer knows where
every GLYPH is and nothing about structure. `merge_page_geometry` joins them by
matching an object's opening words against the page's text, which works for
prose and cannot work for anything whose printed form is not its text:

    MEASURED on arXiv 2402.13444v1 (9 pages, the merged route): 131 elements,
    54 of them with no box at all — 27 Reference STUBS, which are not printed
    at all, and 21 Formula, 3 Table and 2 Section, which are. An inline
    formula's text is `ax^2+bx+c = 0` and the page carries a picture of it;
    there is nothing to match.

The detector answers exactly those. It is offline and free, so the geometry
half of the OCR path is available on a document that will never be OCR'd —
which is the whole idea: `yololayout` is run for its boxes, the words come from
the source, and nothing is bought.

HOW A BOX IS CHOSEN
-------------------
By a MONOTONE WALK between anchors, not by a per-page free-for-all. An object
with no box usually has no page either (the text match that failed to place it
is the same one that would have given it a page), so "which page" cannot be
asked directly. What is known is READING ORDER: the objects the text match DID
place are anchors with a real (page, y), and an unplaced object lies between
its neighbours. So each unboxed object may only take a detector box of its own
class that lies after the previous anchor and before the next one, and each box
is taken once.

That is the same discipline `gemma_reader.align_anchored` uses on the ink, for
the same reason: a single monotone pass accumulates its errors, and an anchor
is what stops one object's wrong box from shifting every box below it.

NO BOX IS BETTER THAN A WRONG ONE. Where the window holds no box of the right
class, the object keeps no box — `merge_page_geometry`'s rule for floats, kept
here, because a wrong box cannot be detected downstream.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterable, Optional, Sequence

Box = tuple[float, float, float, float]

#: Object type → the detector family that can box it. A type absent from this
#: map is never given a detector box: the detector has no class for a
#: Paragraph that the ink rows of a prose block do not already answer better,
#: and a Reference stub is not printed anywhere.
FAMILY = {
    "Equation": "display",
    "Formula": "formula",          # by its own `display` flag, see `_family`
    "Table": "table",
    "Diagram": "figure",
    "Picture": "figure",
    "Chart": "figure",
    "Figure": "figure",
    "Section": "title",
}


def _family(obj) -> Optional[str]:
    """Which detector family may box this object."""
    fam = FAMILY.get(obj.type)
    if fam != "formula":
        return fam
    # A Formula is inline or display and the two have different detectors. The
    # display one is also what an Equation uses, so a numbered equation and a
    # display formula compete for the same boxes — which is correct: they are
    # the same printed thing seen by two builders.
    return "display" if (obj.props or {}).get("display") else "inline"


def families(dets: Sequence) -> dict:
    """`{family: [box, …]}` in reading order, from one page's detections."""
    from . import yololayout as Y
    return {
        "display": Y.display_boxes(dets),
        "inline": Y.inline_boxes(dets),
        "table": Y.figure_boxes(dets, classes=("table",)),
        "figure": Y.figure_boxes(dets, classes=("figure",)),
        "title": sorted((d.box for d in dets
                         if d.model == "layout" and d.cls == "title"),
                        key=lambda b: b[1]),
    }


def png_size(path: Path) -> Optional[tuple[int, int]]:
    """A PNG's pixel size from its IHDR — stdlib only.

    Needed because a detection is in the RENDER's pixels and a model region is
    in the model's own page units, and the ratio between them is the one number
    that makes a detector box placeable. Reading it from the file rather than
    recomputing it from a DPI: the render is on disk and its header cannot be
    out of step with itself.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(24)
        if head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
            return None
        w, h = struct.unpack(">II", head[16:24])
        return int(w), int(h)
    except (OSError, struct.error):
        return None


def _page_sizes(doc) -> dict:
    """`{page number: (width, height)}` from the model's own Page objects."""
    out: dict = {}
    for o in doc.objects.values():
        if o.type != "Page":
            continue
        p = o.props or {}
        n = p.get("page_number")
        if n is None:
            continue
        w, h = p.get("page_width"), p.get("page_height")
        if w and h:
            out[int(n)] = (float(w), float(h))
    return out


def _anchor(obj) -> Optional[tuple[int, float, float]]:
    """An object's place in reading order as `(page, top, bottom)`, or None.

    BOTH edges, because a window built from the tops alone is wrong in exactly
    the case this pass exists for: an inline formula sits INSIDE its host
    paragraph, so its box is below that paragraph's top and above its bottom,
    while the next anchor's top is below it again. Measured on 2402.13444v1:
    with tops only, 23 of 26 candidates found no box in their window — the
    window for four formulas on page 5 was 14 points tall.
    """
    p = obj.props or {}
    reg = p.get("region") or {}
    page = p.get("page")
    if page is None or not reg:
        return None
    try:
        top = float(reg.get("top_left_y") or 0)
        return (int(page), top, top + float(reg.get("height") or 0))
    except (TypeError, ValueError):
        return None


def _flow(doc) -> list:
    """The model's objects in reading order — `flow_index` where it is set, the
    stored order otherwise. A model with no flow is still walkable, and a walk
    in file order is the order the builder created them in."""
    objs = [o for o in doc.objects.values() if o.type not in ("Document", "Page")]

    def key(o):
        fi = (o.props or {}).get("flow_index")
        try:
            return (0, int(fi))
        except (TypeError, ValueError):
            return (1, 0)
    return sorted(objs, key=key)


def candidate_count(doc) -> int:
    """How many objects the layout pass would TRY to box.

    The same predicate `place` applies — no `region` of its own, and a family
    the detector has boxes for — asked before the 400 dpi rasterize and the
    detector run instead of after. It is the question "would this pass change
    anything", and it costs a walk over the model.

    `drill` asks it. Measured 2026-10-29 on 2016icpr: 0 candidates, and
    `geometry --layout` duly reported "boxed 0 of 0" after spending 56.84 s —
    263.93 s before the imposition fix, 97% of the whole drill. On a document
    whose text match CANNOT place its objects — a scan, the geometry lane —
    this is where the pass earns its cost, and there the count is positive.
    """
    return sum(1 for o in _flow(doc)
               if not (o.props or {}).get("region") and _family(o))


def place(doc, dets_by_page: dict, sizes_by_page: dict) -> dict:
    """Give every unboxed object a detector box, by the monotone walk above.

    `dets_by_page` — `{page: [Det, …]}`. `sizes_by_page` — `{page: (px_w, px_h)}`,
    the render the detections are in. Mutates `doc`; returns counts.
    """
    page_pt = _page_sizes(doc)
    boxes: dict = {}
    used: dict = {}
    for pno, dets in dets_by_page.items():
        px = sizes_by_page.get(pno)
        pt = page_pt.get(pno)
        if not px or not pt or not px[0] or not px[1]:
            continue
        sx, sy = pt[0] / px[0], pt[1] / px[1]
        fam = families(dets)
        boxes[pno] = {k: [(b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy)
                          for b in v] for k, v in fam.items()}
        used[pno] = {k: set() for k in fam}

    flow = _flow(doc)
    # For each position in the flow, the nearest anchor before and after it.
    before: list = [None] * len(flow)
    after: list = [None] * len(flow)
    last = None
    for i, o in enumerate(flow):
        before[i] = last
        a = _anchor(o)
        if a:
            last = a
    nxt = None
    for i in range(len(flow) - 1, -1, -1):
        after[i] = nxt
        a = _anchor(flow[i])
        if a:
            nxt = a

    stats = {"boxed": 0, "by_type": {}, "no_window": 0, "no_box": 0,
             "candidates": 0}
    for i, o in enumerate(flow):
        p = o.props or {}
        if p.get("region"):
            continue
        fam = _family(o)
        if not fam:
            continue
        stats["candidates"] += 1
        lo, hi = before[i], after[i]
        if lo is None and hi is None:
            stats["no_window"] += 1
            continue
        pick = _first_in_window(boxes, used, fam, lo, hi)
        if pick is None:
            stats["no_box"] += 1
            continue
        pno, box = pick
        p["page"] = pno
        p["region"] = {"top_left_x": round(box[0], 2),
                       "top_left_y": round(box[1], 2),
                       "width": round(box[2] - box[0], 2),
                       "height": round(box[3] - box[1], 2)}
        p["region_via"] = "yolo"
        o.props = p
        stats["boxed"] += 1
        stats["by_type"][o.type] = stats["by_type"].get(o.type, 0) + 1
    return stats


#: How far past an anchor's own edge a box may still belong to the object
#: between the anchors. One line, because the anchor's rectangle is the union of
#: ITS lines and a formula set a shade higher than the x-height of the line it
#: sits on would otherwise fall outside its own paragraph.
EDGE_SLACK = 14.0


def _first_in_window(boxes: dict, used: dict, fam: str,
                     lo: Optional[tuple], hi: Optional[tuple]):
    """The first unused box of `fam` inside the window the anchors leave.

    The window runs from the PREVIOUS anchor's top edge to the NEXT anchor's
    bottom edge — both edges, see `_anchor`. An open end is open: an object
    before the first anchor may take anything up to it, and one after the last
    may take anything from it on. That is what makes a model whose text match
    placed little still get boxes.
    """
    for pno in sorted(boxes):
        if lo and pno < lo[0]:
            continue
        if hi and pno > hi[0]:
            break
        for n, box in enumerate(boxes[pno].get(fam) or ()):
            if n in used[pno][fam]:
                continue
            if lo and pno == lo[0] and box[3] < lo[1] - EDGE_SLACK:
                continue                      # ends above the window
            if hi and pno == hi[0] and box[1] > hi[2] + EDGE_SLACK:
                continue                      # starts below the window
            used[pno][fam].add(n)
            return pno, box
    return None


#: A Reference the bibliography builder made from a `\cite` key is a PLACEHOLDER
#: for an entry nobody has read — `stub: True`, no title, no printed form. It is
#: not an object with a missing box; it is an object with nothing to box, and
#: counting it among the former makes a model look worse the more citations it
#: has. Named here so the inspector's audit and this pass agree.
def not_printed(obj_type: str, props: Optional[dict] = None) -> bool:
    """True when this object has no printed form, so no box is expected.

    Takes the type and the props rather than the object, because its two
    callers hold different things: this module walks `DocObject`s and the
    inspector walks the serialized dicts.
    """
    p = props or {}
    if obj_type == "Citation":
        return True                      # an inline marker, not a printed line
    if obj_type == "Reference" and p.get("stub"):
        return True
    return False
