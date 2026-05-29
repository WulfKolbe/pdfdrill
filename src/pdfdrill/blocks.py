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
