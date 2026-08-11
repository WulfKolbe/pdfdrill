"""Split an inkdrill-scale page into a STRUCTURE layer and a BLOB layer.

inkdrill produces 3,390-4,105 components per page, of which 33-154 are
structural. `docinspect` emits one DOM div per object with two categories and a
free-text filter — right for tens of objects, a rendering problem at thousands,
and a page uniformly covered in rectangles shows nothing at all.

So the payload is split at build time rather than filtered at view time:

  structure  frames, rules, cells, coverage residuals — TENS. Keep the DOM and
             the right-panel linkage: these are what a reader inspects.
  blobs      the thousands. One flat typed array, drawn to a single <canvas>
             and hit-tested through a grid index. No DOM node each.

And the default view is SUSPICIOUS ONLY. Every class below was measured on real
pages and is a QC target; on a 3,390-component page there are tens of them,
which is the number a person can look at.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

# data-cat values the client toggles over. `glyph` is off by default: it is the
# bulk of the blob layer and the least likely to be what a reader is hunting.
CATEGORIES = ("frame", "rule", "cell", "tick", "raster", "glyph")
DEFAULT_OFF = ("glyph",)

# The blob layer is for INKDRILL COMPONENTS, not for pdfdrill objects. Every
# type pdfdrill's own model produces is something a reader inspects and keeps
# its DOM node; the thousands are the connected components inkdrill adds.
#
# Getting this backwards routed `Formula` into the blob layer and dropped it
# from the inspector on all 3,300 existing documents — none of which have any
# inkdrill data at all. The default has to be structure.
_BLOB_TYPES = {"Blob", "Component", "InkComponent", "Ink", "Glyph", "Stroke"}

# The six measured suspicion classes.
NO_REGION = "ink with no region"
STRADDLES = "blob straddling a region edge"
NON_WHITE = "ink on non-white ground"
REJECTED = "classification rejected"
INVERTED = "row with inverted body_height"
HOLE_DISAGREE = "hole-count disagreement"


def category(obj_type: str, props: Optional[dict]) -> str:
    """`data-cat` for one element. inkdrill states it; otherwise infer."""
    props = props or {}
    stated = props.get("ink.kind") or props.get("ink.category")
    if stated in CATEGORIES:
        return stated
    if obj_type in ("TableCell",):
        return "cell"
    if obj_type in ("Picture", "Diagram", "Chart", "Figure"):
        return "raster"
    if obj_type in ("Table", "TableRow", "Page", "Section"):
        return "frame"
    if props.get("ink.is_rule"):
        return "rule"
    return "glyph"


def suspicions(props: Optional[dict], *, has_region: bool) -> list[str]:
    """Which of the six classes this element falls into. Empty is the norm.

    Each is a POSITIVE signal from inkdrill or the model — never "we could not
    tell", which would make every unmeasured element suspicious and drown the
    view it exists to keep small.
    """
    p = props or {}
    out: list[str] = []
    if not has_region:
        out.append(NO_REGION)
    if p.get("ink.straddles_region"):
        out.append(STRADDLES)
    if p.get("ink.ground") not in (None, "white"):
        out.append(NON_WHITE)
    if p.get("ink.classification") == "rejected" or p.get("ink.rejected"):
        out.append(REJECTED)
    bh = p.get("ink.body_height")
    if isinstance(bh, (int, float)) and bh < 0:
        out.append(INVERTED)
    a, b = p.get("ink.holes"), p.get("ink.holes_expected")
    if isinstance(a, int) and isinstance(b, int) and a != b:
        out.append(HOLE_DISAGREE)
    return out


def is_structure(obj_type: str, props: Optional[dict]) -> bool:
    """Does this element earn a DOM node?"""
    p = props or {}
    if p.get("ink.structural"):
        return True                      # inkdrill promoted it
    if obj_type in _BLOB_TYPES:
        return False
    return True                          # a pdfdrill object: always inspectable


def blob_arrays(blobs: Iterable[dict]) -> dict:
    """The blob layer as flat arrays — one canvas draw, no DOM.

    Flat and parallel rather than a list of objects: 4,000 dicts is ~1 MB of
    JSON and 4,000 GC objects in the client; six flat arrays are a tenth of
    that and go straight into typed arrays.
    """
    xs: list[float] = []; ys: list[float] = []
    ws: list[float] = []; hs: list[float] = []
    cats: list[int] = []; susp: list[int] = []; ids: list[str] = []
    cat_index = {c: i for i, c in enumerate(CATEGORIES)}
    for b in blobs:
        box = b.get("bbox") or {}
        xs.append(float(box.get("x") or 0)); ys.append(float(box.get("y") or 0))
        ws.append(float(box.get("w") or 0)); hs.append(float(box.get("h") or 0))
        cats.append(cat_index.get(b.get("cat", "glyph"), len(CATEGORIES) - 1))
        susp.append(1 if b.get("suspicions") else 0)
        ids.append(b.get("id", ""))
    return {"n": len(ids), "x": xs, "y": ys, "w": ws, "h": hs,
            "cat": cats, "susp": susp, "id": ids,
            "categories": list(CATEGORIES)}
