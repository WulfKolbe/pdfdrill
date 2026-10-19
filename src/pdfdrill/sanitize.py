r"""One last pass over a lines.json's BOXES, against the page's own ink.

WHOEVER MADE THE BOX, THE INK IS THE ARBITER
--------------------------------------------
The readers before this decide WHAT each line is — the model's text, the
detector's types, the ink alignment's order. This step only decides WHERE it
is, and it decides it from one source: the 8-connected ink components of the
page image. That separation is the point. A box arrives here from an ink row
(too loose: the row's slack, a neighbour's descender), from a detector (too
loose at the left and right: the box is drawn around a region, not around
glyphs), or from an interpolation (roughly right). All three are repaired by
the same three questions, and none of them needs to know which produced it.

    claim   every component belongs to at most ONE line: the smallest line box
            holding its centre. Smallest, so an equation number beats the
            formula block drawn around it.
    grow    an UNCLAIMED component beside a line, on its band, joins it. This
            is what recovers the characters a detector box clipped — the model
            read them, the box left them out — and the italic tail a tight ink
            row cut.
    shrink  each box becomes the tight bounding box of the components it owns.

MEASURED on penev_A's 22 sheets, with the sheet reading as the lane wrote it:
832 of 3,007 lines carried `geometry: "none"` — no box at all — and a further
104 carried `pending-split`, which is an INTERNAL marker of `align` meaning "a
later pass will divide this row" and should never have reached a file. This
pass cannot invent a position for a line the alignment never placed (that is
`nup` and the detector anchors), but it does say so, once, per line, in
`checks` — the difference between a reading that is wrong and a reading that
is wrong and silent.

WHAT IT REFUSES TO TOUCH
------------------------
A `diagram`, `table` or `chart` keeps its box and swallows its own ink, so a
figure's strokes can never join a text line. A container — a MathPix
`footnote` or `section_header` with `children_ids` — holds no ink of its own
and takes the union of its children AFTER they are repaired. A `simple_cell`
keeps its box, because a table cell's geometry comes from the grid and a cell
that owns no ink is an EMPTY CELL, which is correct and not a defect: asking
the ink to confirm it cost 735 cells their geometry once already.
"""
from __future__ import annotations

import statistics
from pathlib import Path
from typing import Iterable, Optional, Sequence

from . import inkbox

Box = tuple[float, float, float, float]

#: A component smaller than this x line height in BOTH directions is noise —
#: the same yardstick `inkbox` uses, and for the same reason: a scan's flecks
#: arrive in clusters and a fixed pixel size is wrong at every other dpi.
SPECK = 0.12

#: An unclaimed component joins a line across a horizontal gap of at most this
#: x line height. Wider than a word space (about 0.3) and narrower than the
#: space between an equation and its number (about 3 on a measured page), so
#: growing recovers a clipped glyph without swallowing the neighbour.
GAP = 0.9

#: Vertical slack when testing whether a component lies on a line's band.
BAND = 0.15

#: A `text` line taller than this x line height holds two printed lines.
TALL = 1.9

#: Two boxes overlapping by more than this share of the smaller are reported.
OVERLAP = 0.5

#: Only these types grow. A container, a cell and a figure must not: each has
#: a box that means something other than "the extent of my ink".
GROW_TYPES = frozenset({
    "text", "math", "equation_number", "section_header", "footnote",
    "page_info", "figure_label", "title", "authors", "abstract",
})

#: Types whose box is the detector's region and whose ink is their own.
FIGURE_TYPES = frozenset({"diagram", "table", "chart"})

#: Types whose box comes from the grid, not from ink.
GRID_TYPES = frozenset({"simple_cell", "table_spanning_cell"})


def _box_of(line: dict) -> Box:
    r = line.get("region") or {}
    x = r.get("top_left_x", 0)
    y = r.get("top_left_y", 0)
    return (x, y, x + r.get("width", 0), y + r.get("height", 0))


def _region(b: Box) -> dict:
    return {"top_left_x": int(round(b[0])), "top_left_y": int(round(b[1])),
            "width": int(round(b[2] - b[0])),
            "height": int(round(b[3] - b[1]))}


def _cnt(b: Box) -> list[list[int]]:
    x0, y0, x1, y1 = (int(round(v)) for v in b)
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def _area(b: Box) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inter(a: Box, b: Box) -> float:
    return (max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
            * max(0.0, min(a[3], b[3]) - max(a[1], b[1])))


def _empty(b: Box) -> bool:
    return not (b[2] > b[0] and b[3] > b[1])


def sanitize_page(page: dict, gray, stats: dict) -> list[str]:
    """Repair one page's boxes in place; return the checks it raises."""
    lines = page.get("lines") or []
    if not lines:
        return []
    ih, iw = gray.shape
    pw = page.get("page_width") or iw or 1
    ph = page.get("page_height") or ih or 1
    sx, sy = iw / float(pw), ih / float(ph)   # lines.json pixels -> image

    boxes = [tuple(v for v in (b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy))
             for b in (_box_of(l) for l in lines)]

    text_h = [b[3] - b[1] for b, l in zip(boxes, lines)
              if l.get("type") == "text" and b[3] > b[1]]
    comps_all = inkbox.components(gray)
    lh = (statistics.median(text_h) if text_h
          else inkbox.median_height(comps_all))
    comps = [c for c in comps_all
             if max(c[2] - c[0], c[3] - c[1]) >= SPECK * lh]

    figures = {i for i, l in enumerate(lines)
               if l.get("type") in FIGURE_TYPES}
    parents = {i for i, l in enumerate(lines)
               if l.get("children_ids") and l.get("type") not in FIGURE_TYPES}
    grid = {i for i, l in enumerate(lines) if l.get("type") in GRID_TYPES}
    frozen = parents | grid

    # A container holds no ink of its own and a cell's box is the grid's, so
    # neither competes for a component. Emptying their boxes for the claim is
    # how that is said once instead of at every comparison below.
    claimable = [((0.0, 0.0, 0.0, 0.0) if i in frozen else b)
                 for i, b in enumerate(boxes)]

    owner = [-1] * len(comps)
    for ci, c in enumerate(comps):
        cx, cy = (c[0] + c[2]) / 2.0, (c[1] + c[3]) / 2.0
        holders = [i for i, b in enumerate(claimable)
                   if not _empty(b) and b[0] <= cx <= b[2] and b[1] <= cy <= b[3]]
        if holders:
            # A figure wins over anything drawn around it, then the smallest
            # box wins: an equation number inside a formula block's box is the
            # case this ordering exists for.
            owner[ci] = min(holders,
                            key=lambda i: (i not in figures, _area(claimable[i])))

    # Start growing from the CLAIMED ink rather than from the box, so a loose
    # box does not reach further than the glyphs it actually holds.
    grown = [list(b) for b in claimable]
    for i in range(len(lines)):
        if i in frozen or i in figures:
            continue
        own = [comps[ci] for ci, o in enumerate(owner) if o == i]
        if own:
            grown[i] = [min(c[0] for c in own), min(c[1] for c in own),
                        max(c[2] for c in own), max(c[3] for c in own)]

    changed = True
    while changed:
        changed = False
        for ci, c in enumerate(comps):
            if owner[ci] != -1:
                continue
            cy = (c[1] + c[3]) / 2.0
            best, bgap = None, GAP * lh
            for i, b in enumerate(grown):
                if lines[i].get("type") not in GROW_TYPES:
                    continue
                if _empty(tuple(b)):
                    continue
                if not (b[1] - BAND * lh <= cy <= b[3] + BAND * lh):
                    continue
                gap = max(b[0] - c[2], c[0] - b[2], 0.0)
                if gap <= bgap:
                    best, bgap = i, gap
            if best is not None:
                owner[ci] = best
                b = grown[best]
                grown[best] = [min(b[0], c[0]), min(b[1], c[1]),
                               max(b[2], c[2]), max(b[3], c[3])]
                stats["components_grown"] += 1
                changed = True

    checks: list[str] = []
    pno = page.get("page")
    for i, line in enumerate(lines):
        if i in frozen or i in figures:
            continue
        own = [comps[ci] for ci, o in enumerate(owner) if o == i]
        if not own:
            which = line.get("geometry") or "?"
            checks.append(
                f"p{pno} line {line.get('line')} ({line.get('type')}, "
                f"geometry {which}): no ink in its box")
            stats["no_ink"] += 1
            stats["no_ink_by_geometry"][which] = (
                stats["no_ink_by_geometry"].get(which, 0) + 1)
            continue
        nb = (min(c[0] for c in own) / sx, min(c[1] for c in own) / sy,
              max(c[2] for c in own) / sx, max(c[3] for c in own) / sy)
        old = _box_of(line)
        if [int(v) for v in nb] != [int(v) for v in old]:
            line["geometry_before"] = line.get("region")
            line["region"] = _region(nb)
            line["cnt"] = _cnt(nb)
            stats["boxes_changed"] += 1
            t = line.get("type") or "?"
            stats["by_type"][t] = stats["by_type"].get(t, 0) + 1
            if nb[0] < old[0] - 2 or nb[2] > old[2] + 2:
                stats["widened"] += 1
        if line.get("type") == "text" and (nb[3] - nb[1]) * sy > TALL * lh:
            checks.append(
                f"p{pno} line {line.get('line')} (text): "
                f"{int((nb[3] - nb[1]) * sy)} px tall against a line height of "
                f"{int(lh)} — two printed lines in one?")
            stats["tall_text"] += 1

    by_id = {l.get("id"): l for l in lines if l.get("id")}
    for i in parents:
        kids = [_box_of(by_id[c]) for c in (lines[i].get("children_ids") or [])
                if c in by_id]
        kids = [k for k in kids if not _empty(k)]
        if not kids:
            continue
        u = (min(k[0] for k in kids), min(k[1] for k in kids),
             max(k[2] for k in kids), max(k[3] for k in kids))
        if [int(v) for v in u] != [int(v) for v in _box_of(lines[i])]:
            lines[i]["geometry_before"] = lines[i].get("region")
            lines[i]["region"] = _region(u)
            lines[i]["cnt"] = _cnt(u)
            stats["containers_unioned"] += 1

    overlap_candidates = [(i, _box_of(l)) for i, l in enumerate(lines)
                          if i not in frozen and i not in figures
                          and not _empty(_box_of(l))]
    for a in range(len(overlap_candidates)):
        i, p = overlap_candidates[a]
        for b in range(a + 1, len(overlap_candidates)):
            j, q = overlap_candidates[b]
            small = min(_area(p), _area(q))
            if small and _inter(p, q) > OVERLAP * small:
                checks.append(
                    f"p{pno} lines {lines[i].get('line')}/{lines[j].get('line')} "
                    f"({lines[i].get('type')}/{lines[j].get('type')}) overlap "
                    f"{_inter(p, q) / small:.0%} of the smaller")
                stats["overlaps"] += 1
    return checks


def new_stats() -> dict:
    return {"pages": 0, "boxes_changed": 0, "widened": 0,
            "components_grown": 0, "containers_unioned": 0, "no_ink": 0,
            "tall_text": 0, "overlaps": 0, "by_type": {},
            "no_ink_by_geometry": {}}


def sanitize(doc: dict, images: dict[int, Path], *,
             max_checks: int = 200) -> dict:
    """Repair every page of `doc` for which `images` has that page's render.

    `images` maps the lines.json `page` to the image the boxes are in. A page
    with no image is left exactly as it is — a reading whose boxes were not
    checked is better than a reading whose boxes were checked against the
    wrong picture.
    """
    stats = new_stats()
    checks: list[str] = []
    for page in doc.get("pages") or []:
        png = images.get(page.get("page"))
        if png is None or not Path(png).is_file():
            continue
        checks += sanitize_page(page, inkbox.load_gray(Path(png)), stats)
        stats["pages"] += 1
    doc["sanitize"] = {
        "stats": stats,
        "checks": checks[:max_checks],
        "checks_total": len(checks),
        "params": {"speck": SPECK, "gap": GAP, "band": BAND, "tall": TALL,
                   "overlap": OVERLAP},
    }
    return doc


def report(doc: dict) -> str:
    """The `sanitize` block as prose, for the command that ran it."""
    blk = doc.get("sanitize") or {}
    st = blk.get("stats") or {}
    lines = [
        f"sanitized {st.get('pages', 0)} pages: "
        f"{st.get('boxes_changed', 0)} boxes tightened "
        f"({st.get('widened', 0)} widened), "
        f"{st.get('components_grown', 0)} stray components claimed, "
        f"{st.get('containers_unioned', 0)} containers re-unioned",
    ]
    by = st.get("by_type") or {}
    if by:
        top = sorted(by.items(), key=lambda kv: -kv[1])[:8]
        lines.append("  by type: " + ", ".join(f"{t} {n}" for t, n in top))
    probs = []
    if st.get("no_ink"):
        probs.append(f"{st['no_ink']} lines with no ink in their box")
    if st.get("tall_text"):
        probs.append(f"{st['tall_text']} text lines two printed lines tall")
    if st.get("overlaps"):
        probs.append(f"{st['overlaps']} overlapping pairs")
    if probs:
        lines.append("  checks: " + "; ".join(probs))
    nig = st.get("no_ink_by_geometry") or {}
    if nig:
        lines.append("  no ink, by how the box was made: " + ", ".join(
            f"{k} {v}" for k, v in sorted(nig.items(), key=lambda kv: -kv[1])))
    return "\n".join(lines)
