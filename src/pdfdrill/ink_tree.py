r"""B1/B2 — the merged tree: ink blobs under the MathPix regions that contain
them, and the three residual classes that audit the result.

THE TREE IS THE PRODUCT; THE RESIDUALS ARE THE AUDIT. Neither is optional.

Shape: a FLAT list of nodes, each carrying `parent` = the containing region's
id. Physical nesting does not survive a round trip through JSON, an ordered
projection, or an edit; a parent reference does. Each node also carries
`parent_type`, so "which of these blobs are body text" is one field lookup
rather than a walk — on the measured page that is 2,736 blobs under `text`.

Attachment is to the DEEPEST containing region. A cell inside a row inside a
table has all three containing the blob, and attaching to the outermost would
throw away the structure MathPix did get right. Depth is containment, not
area: the parent is the containing region that contains no other containing
region.

The three residuals, none of which may be silently dropped:

* ORPHAN — no region contains or even meets it. On a page MathPix partly
  misses, these ARE the finding.
* STRADDLER — it crosses a boundary, so NO correct parent exists. It is not
  assigned. A blob crossing a region edge is evidence the BOUNDARY is wrong,
  and attaching it to whichever region it overlaps most destroys exactly that
  evidence — which is how a clipped integral sign stops being visible.
* TIE — two containing regions at the same depth, neither inside the other.
  Rare (12 on the measured page), but there is genuinely no deepest, so it is
  recorded with its candidates instead of resolved by whatever the sort put
  first. A coin toss must not be able to look like a measurement.

Counts reconcile to the component total, and that is asserted in the tests: a
partition that quietly lost blobs would report a cleaner tree for having
dropped the awkward ones.

Note on containers: `ink_coverage` DROPS `table`/`table_row`/`table_column`
because it is measuring how much of the page MathPix saw, and nesting would
count one blob twice. Here containers are KEPT, because nesting is what
supplies the depth. Same two inputs, opposite treatment, different questions.
"""
from __future__ import annotations

from typing import Any, Sequence

ORPHAN = "orphan"
STRADDLER = "straddler"
TIE = "tie"
RESIDUAL_CLASSES = (ORPHAN, STRADDLER, TIE)

Rect = tuple[float, float, float, float]


def _contains(outer: Rect, inner: Rect) -> bool:
    return (inner[0] >= outer[0] and inner[1] >= outer[1]
            and inner[2] <= outer[2] and inner[3] <= outer[3])


def _intersects(a: Rect, b: Rect) -> bool:
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def build_tree(boxes: Sequence[tuple[Any, Rect, int]],
               regions: Sequence[tuple[Any, Rect, str]]) -> dict:
    """Attach each blob to its deepest containing region.

    `boxes` are `(id, rect, area)`; `regions` are `(id, rect, type)`, both in
    ONE coordinate space — convert before calling, never inside.
    """
    regs = sorted(regions, key=lambda r: (r[1][1], r[1][0], str(r[0])))
    items = sorted(boxes, key=lambda b: (b[1][1], b[1][0], str(b[0])))
    rtype = {rid: typ for rid, _rect, typ in regs}

    nodes: list[dict] = []
    residuals: dict[str, list] = {k: [] for k in RESIDUAL_CLASSES}
    tie_candidates: dict[str, list] = {}
    # A residual blob is not a node, so it has no rect anywhere else — and the
    # residuals are the AUDIT. Without this, "1 straddler" is a number nobody
    # can go and look at.
    residual_rects: dict[str, list] = {}
    children: dict[Any, list] = {rid: [] for rid, _r, _t in regs}
    by_parent_type: dict[str, int] = {}

    for bid, rect, area in items:
        holding = [(rid, rrect) for rid, rrect, _t in regs
                   if _contains(rrect, rect)]
        if not holding:
            meets = any(_intersects(rrect, rect) for _rid, rrect, _t in regs)
            residuals[STRADDLER if meets else ORPHAN].append(bid)
            residual_rects[str(bid)] = list(rect)
            continue
        # deepest = contains no OTHER containing region
        deepest = [rid for rid, rrect in holding
                   if not any(other_id != rid and _contains(rrect, other_rect)
                              for other_id, other_rect in holding)]
        if len(deepest) != 1:
            residuals[TIE].append(bid)
            tie_candidates[str(bid)] = sorted(str(r) for r in deepest)
            residual_rects[str(bid)] = list(rect)
            continue
        parent = deepest[0]
        typ = rtype.get(parent, "")
        nodes.append({"id": bid, "parent": parent, "parent_type": typ,
                      "rect": list(rect), "area": int(area)})
        children[parent].append(bid)
        by_parent_type[typ] = by_parent_type.get(typ, 0) + 1

    return {
        "components": len(items),
        "regions": len(regs),
        "nodes": nodes,
        "children": children,
        "by_parent_type": by_parent_type,
        "residuals": residuals,
        "tie_candidates": tie_candidates,
        "residual_rects": residual_rects,
        "counts": {"attached": len(nodes),
                   **{k: len(v) for k, v in residuals.items()}},
    }
