"""
Multi-line block reconstruction from fused geometry.

OCR/MathPix emit list entries as loose lines; the *nesting* lives in the
layout (indentation), which the geometry-fusion step exposes as
`_geom.indent_norm` per line. `nest_list_items` turns a flat, flow-ordered
sequence of ListItems (each with a page, line index, indentation, and marker)
into a recursive List tree — the same way a LaTeX list nests by indentation
depth. This is the first block detector built on the geometry substrate;
algorithm bodies will reuse the same indentation-run machinery.

Pure and side-effect free so it can be unit-tested without a Document; the
command layer materializes the returned tree into List DocObjects.
"""
from __future__ import annotations

import re
from typing import Any, Optional


_BULLET_CHARS = "•○▪-*‣◦⁃∙·–—"


def marker_family(marker: Optional[str]) -> str:
    """Coarse list family: bullet / numbered / lettered / other."""
    if not marker:
        return "other"
    c = marker[0]
    if c in _BULLET_CHARS:
        return "bullet"
    if c.isdigit():
        return "numbered"
    if c.isalpha():
        return "lettered"
    return "other"


def _segment_runs(items: list[dict], max_gap: int) -> list[list[dict]]:
    """Split items into list regions.

    A new region starts on a page change, a marker-family change, or a very
    large line gap. Moderate gaps are bridged so list items interleaved with
    answer paragraphs (e.g. a NeurIPS checklist) stay one list. Indentation is
    handled later by nesting, so a deeper indent does NOT split the run.
    """
    runs: list[list[dict]] = []
    cur: list[dict] = []
    for it in items:
        if cur:
            prev = cur[-1]
            li, pli = it.get("line_index"), prev.get("line_index")
            big_jump = (li is not None and pli is not None and (li - pli) > max_gap)
            family_change = marker_family(it.get("marker")) != marker_family(prev.get("marker"))
            if it.get("page") != prev.get("page") or family_change or big_jump:
                runs.append(cur)
                cur = []
        cur.append(it)
    if cur:
        runs.append(cur)
    return runs


def _nest_run(run: list[dict], eps: float) -> list[dict]:
    """Nest one contiguous run by indentation, returning a list of nodes,
    each {'kind': 'item', 'id', 'marker'} or {'kind': 'list', 'node': {...}}."""
    root: list[dict] = []
    sentinel = {"indent": -1.0, "children": root}
    stack = [sentinel]
    for it in run:
        ind = it.get("indent")
        # An item with no geometry stays at the current nesting level rather
        # than collapsing to 0 (which would mis-nest unmatched marker lines).
        ind = stack[-1]["indent"] if ind is None else ind
        if ind < 0:
            ind = 0.0
        # Close lists deeper than this item.
        while len(stack) > 1 and ind < stack[-1]["indent"] - eps:
            stack.pop()
        # Open a deeper list when this item is indented past the current level.
        if ind > stack[-1]["indent"] + eps:
            node = {"indent": ind, "children": []}
            stack[-1]["children"].append({"kind": "list", "node": node})
            stack.append(node)
        stack[-1]["children"].append(
            {"kind": "item", "id": it["id"], "marker": it.get("marker")})
    return root


def nest_list_items(items: list[dict], indent_eps: float = 0.02,
                    max_gap: int = 40) -> list[dict]:
    """Flow-ordered ListItems -> list of root nodes (each a 'list' node)."""
    roots: list[dict] = []
    for run in _segment_runs(items, max_gap):
        roots.extend(_nest_run(run, indent_eps))
    return roots


def max_depth(nodes: list[dict]) -> int:
    """Deepest list-nesting level in a node list (a flat list = depth 1)."""
    best = 0
    for ch in nodes:
        if ch.get("kind") == "list":
            best = max(best, 1 + max_depth(ch["node"]["children"]))
    return best


def count_lists(nodes: list[dict]) -> int:
    n = 0
    for ch in nodes:
        if ch.get("kind") == "list":
            n += 1 + count_lists(ch["node"]["children"])
    return n


# ---------------------------------------------------------------------------
# Algorithm blocks (MathPix `pseudocode` line type)
# ---------------------------------------------------------------------------

_ALGO_CAPTION = re.compile(r"^\s*Algorithm\s+(\d+)\s*[:.]?\s*(.*)$")


def _x_levels(xs: list[float], tol: float) -> dict[float, int]:
    """Map sorted-unique x positions to integer indent levels."""
    levels: dict[float, int] = {}
    lvl = 0
    prev: Optional[float] = None
    for x in xs:
        if prev is not None and x - prev > tol:
            lvl += 1
        levels[x] = lvl
        prev = x
    return levels


def detect_algorithms(lines: list[dict], x_tol: float = 20.0) -> list[dict]:
    """Group flow-ordered `pseudocode` lines into algorithm blocks.

    `lines`: [{id, page, line_index, text, x}] — only pseudocode lines.
    A line matching `Algorithm N: title` starts a new block; following
    pseudocode lines are its body, with an integer `depth` derived from the
    left-x indentation (so if/else/end nesting is preserved). Returns
    [{number, title, page, caption_id, steps:[{id, text, depth}]}].
    """
    algos: list[dict] = []
    cur: Optional[dict] = None
    for ln in lines:
        text = ln.get("text") or ""
        m = _ALGO_CAPTION.match(text)
        if m:
            if cur:
                algos.append(cur)
            cur = {"number": int(m.group(1)), "title": m.group(2).strip(),
                   "page": ln.get("page"), "caption_id": ln["id"],
                   "_body": [], "_xs": []}
            continue
        if cur is None:
            cur = {"number": None, "title": "", "page": ln.get("page"),
                   "caption_id": None, "_body": [], "_xs": []}
        cur["_body"].append(ln)
        cur["_xs"].append(ln.get("x"))
    if cur:
        algos.append(cur)

    for a in algos:
        xs = sorted({x for x in a["_xs"] if x is not None})
        lv = _x_levels(xs, x_tol)
        a["steps"] = [{"id": b["id"], "text": b.get("text") or "",
                       "depth": lv.get(b.get("x"), 0)} for b in a["_body"]]
        del a["_body"], a["_xs"]
    return algos


def algorithm_max_depth(algos: list[dict]) -> int:
    return max((s["depth"] for a in algos for s in a["steps"]), default=0)


# ---------------------------------------------------------------------------
# Geometry re-split: recover bullets the OCR merged onto one line (no linefeed)
# ---------------------------------------------------------------------------

def resplit_list_items_by_geometry(doc, eps: float = 0.004) -> int:
    """Split a `ListItem` whose MathPix line genuinely spans several lines.

    A real OCR merge has a region tall enough to cover multiple visual lines.
    So we only act when the item's region height is >= ~1.5x the page line
    spacing AND its band covers >=2 `pdf_lines` that each start with a bullet.
    (Without the height gate a normal one-line item's band can bleed into the
    next line via `eps` and duplicate it.) We rewrite the original item to the
    first visual line and add a `ListItem` per remaining one, taking text +
    indentation from each pdf_line. Returns the number of items added.
    """
    from collections import defaultdict
    from statistics import median
    from docmodel.core import DocObject, Realization
    from docmodel.modules.list_items import _detect_marker
    import re as _re

    pl = doc.streams.get("pdf_lines")
    mp = doc.streams.get("mathpix_lines")
    if pl is None or mp is None:
        return 0

    by_page: dict = defaultdict(list)
    for a in pl.anchors:
        p = pl.payload[a]
        by_page[p.get("page")].append((p.get("y_norm"), p.get("x0_norm"), p.get("text") or ""))
    for v in by_page.values():
        v.sort(key=lambda t: (t[0] if t[0] is not None else 1e9))

    def line_spacing(page) -> float:
        ys = [y for y, _, _ in by_page.get(page, []) if y is not None]
        gaps = [b - a for a, b in zip(ys, ys[1:]) if 0 < (b - a) < 0.1]
        return median(gaps) if gaps else 0.02

    pages = {p["page"]: p for p in doc.meta.get("pages", [])}
    body_left = (doc.meta.get("geometry", {}) or {}).get("body_left_norm", {})

    def indent_of(x0n, page):
        if x0n is None:
            return None
        return round(x0n - (body_left.get(str(page), 0.0) or 0.0), 4)

    def strip_marker(text):
        t = text.strip()
        m = _detect_marker(t)
        return (m or ""), (_re.sub(r"^" + _re.escape(m) + r"\s+", "", t).strip() if m else t)

    added = 0
    for li in list(doc.objects.values()):
        if li.type != "ListItem" or li.props.get("provenance") == "geometry_resplit":
            continue
        sr = next((r for r in li.realizations
                   if r.stream == "mathpix_lines" and r.start is not None), None)
        if sr is None:
            continue
        payload = mp.payload.get(sr.start) or {}
        region = payload.get("region")
        page = payload.get("_page")
        pm = pages.get(page)
        if not region or not pm or not pm.get("page_height"):
            continue
        ph = pm["page_height"]
        y0 = (region.get("top_left_y") or 0) / ph
        h_norm = (region.get("height") or 0) / ph
        y1 = y0 + h_norm
        if y1 <= y0:
            continue
        # Gate: only a region clearly taller than one line can be a merge.
        if h_norm < 1.5 * line_spacing(page):
            continue
        covered = [t for t in by_page.get(page, [])
                   if t[0] is not None and y0 - eps <= t[0] <= y1 + eps]
        bulleted = [t for t in covered if _detect_marker(t[2].strip())]
        if len(bulleted) < 2:
            continue                       # single visual line — nothing merged

        m0, c0 = strip_marker(bulleted[0][2])
        li.props["marker"] = m0 or li.props.get("marker")
        li.props["content"] = c0
        li.props["_resplit_indent"] = indent_of(bulleted[0][1], page)
        for (yn, x0n, txt) in bulleted[1:]:
            mk, content = strip_marker(txt)
            n = DocObject(type="ListItem", props={
                "marker": mk, "content": content, "page": page,
                "line_index": li.props.get("line_index"),
                "provenance": "geometry_resplit",
                "_resplit_indent": indent_of(x0n, page),
                "bibkey": li.props.get("bibkey")})
            n.add_realization(Realization(stream="mathpix_lines", start=sr.start,
                                          end=sr.start, role="surface",
                                          provenance="geometry_resplit"))
            doc.add(n)
            added += 1
    return added
