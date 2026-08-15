r"""Phase 1 — classify real ink against the regions MathPix reported.

MathPix reports what it FOUND. Ink reports what is THERE. The residual between
them is the product: on 2409.18839 page 8, 3,390 ink components against 101
MathPix regions leave 35 components with no region at all — every table rule on
the page, plus the footnote separator. MathPix describes the table's logical
structure and omits the ink that draws it. That is a design boundary, not a
bug; but for a LaTeX round trip `\toprule/\midrule`, a full `\hline` grid, and
no rules at all are three different documents, and only the ink separates them.

**pdfdrill consumes inkdrill's `lines.json`; it never imports inkdrill.**
Importing would couple a stdlib-only package to a dependency-bearing one and
reverse the direction of the contract. The classification rules below are
inkdrill's (`coverage.py`, G1-G7) restated as pdfdrill behaviour, and the
restatement is under test — a silent drift would make a genuine disagreement
between the two tools indistinguishable from a difference of definition.

Two rules earn their keep:

* CONTAINMENT, NOT CENTRES. A component is INSIDE only when its box lies wholly
  within one region, and STRADDLING on any other intersection. The boundary
  crossing is the finding — it is the case that clips the limits off a tall sum
  whose region was fitted to the body of the line. Centres would call that
  comfortably inside and report nothing.
* MEMBERS, NOT MEANS. Every class reports its member ids. The per-page spread
  is the deliverable and the aggregate buries it: across measured pages the
  missed fraction runs 0.00%-100.00% against a 0.53% median, and the page that
  reports 100% (3 regions against 950 components) is the page worth looking at.

Coordinates: inkdrill declares `ocr.units == "pt"`, derived from the PNG's
`pHYs`; MathPix emits its own pixel space. `mathpix_regions_pt` converts with
the page's DECLARED pixel and point sizes. Deriving the scale from a nominal
page size instead is wrong by 0.071 pt, which is the size of the residuals
being measured. (`mathgold.floor.region_box` computes the same six lines for
the gold path. They are deliberately not shared: merging them would make the
maths gold module depend on the PDF path for no gain. A third call site is what
would change that.)
"""
from __future__ import annotations

from typing import Any, Iterable, Optional, Sequence

INSIDE = "inside"
MISSED = "missed"
STRADDLE = "straddling"
OVERLAPPING = "overlapping"
EMPTY_REGION = "empty_region"

INK_CLASSES = (INSIDE, MISSED, STRADDLE, OVERLAPPING)
ALL_CLASSES = INK_CLASSES + (EMPTY_REGION,)

# MathPix region types that CONTAIN other regions. A table's own rectangle and
# its row/column rectangles enclose the cells, so every cell's ink falls inside
# two regions at once and lands in `overlapping` — a statement about MathPix's
# nesting, not about the page. Measured on 2409.18839 p8: keeping them reports
# 36.25% inside / 63.72% overlapping; dropping them, 47.78% / 52.10%.
CONTAINER_TYPES = frozenset({"table", "table_row", "table_column"})

Rect = tuple[float, float, float, float]        # x0, y0, x1, y1


def rect_of(region: dict) -> Rect:
    """A MathPix `region` as edges. It stores an origin and EXTENTS."""
    x = float(region["top_left_x"])
    y = float(region["top_left_y"])
    return (x, y, x + float(region["width"]), y + float(region["height"]))


def mathpix_regions_pt(regions: Iterable[dict],
                       page_px: tuple[float, float],
                       page_pt: tuple[float, float],
                       ids: Optional[Sequence[Any]] = None) -> list[tuple[Any, Rect]]:
    """MathPix pixel regions in inkdrill's point space, one scale per axis."""
    px_w, px_h = page_px
    pt_w, pt_h = page_pt
    sx, sy = float(pt_w) / float(px_w), float(pt_h) / float(px_h)
    out = []
    for i, reg in enumerate(regions):
        x0, y0, x1, y1 = rect_of(reg)
        rid = ids[i] if ids is not None else i
        out.append((rid, (x0 * sx, y0 * sy, x1 * sx, y1 * sy)))
    return out


def ink_boxes(ink_lines: dict, page: int,
              kinds: Sequence[str] = ("glyph",),
              with_holes: bool = False,
              include_rules: bool = False) -> list[tuple]:
    """One inkdrill page's components as `(id, rect_pt, area)`.

    Refuses a file that does not declare points: the units travel with the data
    or the call fails. A pixel-space file read as points is a scale error that
    looks exactly like a coverage finding.
    """
    units = ((ink_lines.get("ocr") or {}).get("units") or "").lower()
    if units != "pt":
        raise ValueError(
            f"inkdrill lines.json declares ocr.units={units!r}, expected 'pt'; "
            "refusing to guess the space")
    out = []
    for rec in ink_lines.get("pages", []):
        if rec.get("page") != page:
            continue
        for line in rec.get("lines", []):
            if line.get("type") not in kinds:
                continue
            ink = line.get("ink") or {}
            rec_ = (ink.get("region_id"), rect_of(line["region"]),
                    int(ink.get("area") or 0))
            if with_holes:
                # inkdrill measures holes per component; the tree SUMMARISES
                # them, so they travel rather than being recomputed from pixels
                # we do not have.
                rec_ = rec_ + (int(ink.get("holes") or 0),)
            out.append(rec_)
    if include_rules:
        for rid, rect, area, holes in rule_boxes(all_rules(ink_lines, page)):
            out.append((rid, rect, area, holes) if with_holes
                       else (rid, rect, area))
    return out


def page_rules(ink_lines: dict, page: int) -> list[dict]:
    r"""Rules belonging to no emitted object, from `page["ink"]["rules"]`.

    THE CONTRACT GAP THIS CLOSES. inkdrill carries a rule on the line it falls
    inside, and a rule that falls inside nothing on the PAGE record. Reading
    only the per-line arrays therefore sees every rule except the ones with no
    owner — and on a booktabs page that is ALL of them, because booktabs emits
    no object for a rule to attach to.

    It is what let me report "the rules never leave inkdrill" from a `lines`
    count of 0 while the page record of the file I had just generated held all
    four. Absence is read out of the file or it is not established.
    """
    for rec in ink_lines.get("pages", []):
        if rec.get("page") == page:
            return list((rec.get("ink") or {}).get("rules") or [])
    return []


def all_rules(ink_lines: dict, page: int) -> list[dict]:
    """Every rule on a page — page-level and per-line — each tagged with the
    kind of line carrying it, so a consumer can scope by carrier without
    walking the file again."""
    out = [dict(r, carrier="page") for r in page_rules(ink_lines, page)]
    for rec in ink_lines.get("pages", []):
        if rec.get("page") != page:
            continue
        for line in rec.get("lines", []):
            for r in ((line.get("ink") or {}).get("rules") or []):
                out.append(dict(r, carrier=line.get("type") or "line"))
    return out


def rule_boxes(rules: Sequence[dict]) -> list[tuple]:
    """Rules as `(id, rect, area, holes)`, the shape the classifier takes.

    A rule IS ink, and until it is a box `inkcoverage` cannot classify it — the
    table rules MathPix omits stay invisible, which was Phase 1's headline.
    """
    out = []
    for i, r in enumerate(rules):
        x0, y0 = float(r["x0"]), float(r["y0"])
        x1, y1 = float(r["x1"]), float(r["y1"])
        area = int(max(0.0, x1 - x0) * max(0.0, y1 - y0) * 100)
        out.append((f"rule#{i}", (x0, y0, x1, y1), area, 0))
    return out


def _contains(outer: Rect, inner: Rect) -> bool:
    return (inner[0] >= outer[0] and inner[1] >= outer[1]
            and inner[2] <= outer[2] and inner[3] <= outer[3])


def _intersects(a: Rect, b: Rect) -> bool:
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def classify(boxes: Sequence[tuple[Any, Rect, int]],
             regions: Sequence[tuple[Any, Rect]],
             *, min_area: int = 1) -> dict:
    """Partition ink components over MathPix regions. Members, not means."""
    kept = [b for b in boxes if int(b[2]) >= min_area]
    kept.sort(key=lambda b: (b[1][1], b[1][0], str(b[0])))
    regs = sorted(regions, key=lambda r: (r[1][1], r[1][0], str(r[0])))

    members: dict[str, list] = {k: [] for k in ALL_CLASSES}
    touched = {rid: 0 for rid, _ in regs}

    for bid, rect, _area in kept:
        inside = [rid for rid, rrect in regs if _contains(rrect, rect)]
        meets = [rid for rid, rrect in regs if _intersects(rrect, rect)]
        for rid in meets:
            touched[rid] += 1
        if not meets:
            members[MISSED].append(bid)
        elif len(inside) > 1:
            members[OVERLAPPING].append(bid)
        elif len(inside) == 1:
            members[INSIDE].append(bid)
        else:
            members[STRADDLE].append(bid)

    members[EMPTY_REGION] = [rid for rid, n in touched.items() if n == 0]

    n_ink = sum(len(members[k]) for k in INK_CLASSES)
    fractions = {k: (len(members[k]) / n_ink if n_ink else 0.0)
                 for k in INK_CLASSES}
    fractions[EMPTY_REGION] = (len(members[EMPTY_REGION]) / len(regs)
                               if regs else 0.0)
    return {
        "boxes": len(kept),
        "dropped": len(boxes) - len(kept),
        "regions": len(regs),
        "counts": {k: len(members[k]) for k in ALL_CLASSES},
        "members": members,
        "fractions": fractions,
        "min_area": min_area,
    }
