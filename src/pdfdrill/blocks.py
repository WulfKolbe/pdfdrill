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

from typing import Any, Optional


def _segment_runs(items: list[dict], gap: int) -> list[list[dict]]:
    """Split items into contiguous runs (a page change or a line-index jump
    larger than `gap` starts a new run — i.e. a separate list region)."""
    runs: list[list[dict]] = []
    cur: list[dict] = []
    for it in items:
        if cur:
            prev = cur[-1]
            li, pli = it.get("line_index"), prev.get("line_index")
            jump = (li is not None and pli is not None and (li - pli) > gap)
            if it.get("page") != prev.get("page") or jump:
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
        ind = 0.0 if ind is None else ind
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
                    gap: int = 3) -> list[dict]:
    """Flow-ordered ListItems -> list of root nodes (each a 'list' node)."""
    roots: list[dict] = []
    for run in _segment_runs(items, gap):
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
