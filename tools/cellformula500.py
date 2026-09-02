#!/usr/bin/env python3
r"""500 — how many Formula objects sit inside a table cell, corpus-wide.

`parent`/`children` are top-level fields on a DocObject, not props. A Formula
"inside a table cell" is one whose parent chain reaches a TableCell — so the
walk is up, not down, and it stops at the first cell.

1511.08771 is skipped by size (499) and measured separately by streaming.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

MAX_MODEL_BYTES = 1_000_000_000


def measure(d: Path):
    m = d / "model.docmodel.json"
    if not m.is_file():
        return None
    if m.stat().st_size > MAX_MODEL_BYTES:
        return {"oversize": m.stat().st_size}
    try:
        model = json.loads(m.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError, MemoryError):
        return None
    objs = model["objects"]
    by_id = {o["id"]: o for o in objs}
    types = collections.Counter(o["type"] for o in objs)

    def in_cell(o):
        seen, cur = 0, o.get("parent")
        while cur and seen < 12:
            p = by_id.get(cur)
            if p is None:
                return False
            if p["type"] in ("TableCell", "TableRow", "Table"):
                return p["type"] == "TableCell" or p["type"] == "TableRow"
            cur = p.get("parent")
            seen += 1
        return False

    forms = [o for o in objs if o["type"] == "Formula"]
    incell = [o for o in forms if in_cell(o)]
    latex = [(o.get("props") or {}).get("latex", "") for o in forms]
    return {"types": dict(types), "formulas": len(forms),
            "formulas_in_cell": len(incell),
            "distinct_formula_latex": len(set(latex)),
            "bytes": m.stat().st_size}


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "pdfdrill-library"
    out, n, over = {}, 0, []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        r = measure(d)
        if r is None:
            continue
        if r.get("oversize"):
            over.append((d.name, r["oversize"]))
            continue
        n += 1
        if r["formulas_in_cell"]:
            out[d.name] = r
        print("\r%d models, %d with formulas in cells" % (n, len(out)),
              end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    json.dump({"models_read": n, "oversize_skipped": over, "documents": out},
              sys.stdout, indent=1)
