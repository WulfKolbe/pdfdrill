#!/usr/bin/env python3
r"""492 — which of the four constraints empties the bed.

The bed asked for rows that (a) sit in a document with an Abstract object,
(b) resolve through parent_section to a Section at level >= 2, (c) have a
page, and (d) do not currently render. It came back empty. Reporting "0" is
useless without saying which conjunct is responsible, so this counts the
survivors of each constraint alone and of every prefix of the conjunction.

The region join is `docinspect.object_geometry`, not `props["top_left_x"]` —
the region lives on the object's realizations and the props carry it on 0 of
70,000 objects. The first cut of this scan used the props and that is a
second reason it found nothing.
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pdfdrill import report_tex as rt                              # noqa: E402
from pdfdrill.docinspect import build_stream_index, object_geometry  # noqa: E402

ARXIV = re.compile(r"^(\d{4}\.\d{4,5}(v\d+)?|[a-z-]+(\.[A-Z]{2})?_?\d{7})$")
TYPED = re.compile(r"_(EQ|FOX?|TAB)\d")


#: 499 — a model this size is not measurable in one bite, and the guard is
#: REPORTED rather than silent. 1511.08771 is 4.96 GB, fifty-five times the
#: next largest e-print model (0.09 GB); reading it took 5.5 GB of I/O and
#: 16.4 GB of resident memory, after which the per-object loop ran at 99% CPU
#: with no further progress for over twenty minutes. A skipped document that
#: nobody is told about is a population quietly narrowed, which is the failure
#: this project keeps paying for — so it is counted and named.
MAX_MODEL_BYTES = 1_000_000_000


def per_document(d: Path):
    m = d / "model.docmodel.json"
    tp = list(d.glob("*.tiddlers.json"))
    if not m.is_file() or not tp:
        return None
    if m.stat().st_size > MAX_MODEL_BYTES:
        return {"doc": d.name, "oversize": m.stat().st_size,
                "has_abstract": None, "rows": []}
    try:
        model = json.loads(m.read_text(encoding="utf-8", errors="replace"))
        tids = json.loads(tp[0].read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return None
    tids = tids.get("tiddlers", tids) if isinstance(tids, dict) else tids
    objs = model["objects"]
    has_abstract = any(o["type"] == "Abstract" for o in objs)
    sec = {o["id"]: (o.get("props") or {}) for o in objs if o["type"] == "Section"}
    sidx = build_stream_index(model)
    level_of = {}
    for o in objs:
        if o["type"] not in ("Equation", "Formula"):
            continue
        page, bbox, _ = object_geometry(o, sidx)
        if page is None or not bbox:
            continue
        try:
            k = (int(page), int(round(bbox["x"])), int(round(bbox["y"])))
        except (KeyError, TypeError, ValueError):
            continue
        ps = sec.get((o.get("props") or {}).get("parent_section") or "")
        try:
            level_of[k] = int(ps.get("level") or 0) if ps else 0
        except (TypeError, ValueError):
            level_of[k] = 0
    rows = []
    for x in tids:
        lx = x.get("latex") or ""
        if not lx or not TYPED.search(x.get("title", "")):
            continue
        try:
            k = (int(x["page"]), int(x["top_left_x"]), int(x["top_left_y"]))
        except (KeyError, TypeError, ValueError):
            k = None
        rows.append({
            "abstract": has_abstract,
            "level2": bool(k and level_of.get(k, 0) >= 2),
            "page": bool(x.get("page")),
            "fails": not rt.renderable(lx),
            "joined": bool(k and k in level_of),
        })
    return {"doc": d.name, "has_abstract": has_abstract, "rows": rows}


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "pdfdrill-library"
    tally = collections.Counter()
    oversize = []
    docs = 0
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        if not ARXIV.match(d.name):
            continue
        r = per_document(d)
        if r is None:
            tally["no model or tiddlers"] += 1
            continue
        if r.get("oversize"):
            tally["SKIPPED oversize model"] += 1
            oversize.append((d.name, r["oversize"]))
            continue
        docs += 1
        tally["documents"] += 1
        tally["documents with an Abstract"] += bool(r["has_abstract"])
        for row in r["rows"]:
            tally["rows"] += 1
            for k in ("abstract", "level2", "page", "fails", "joined"):
                tally["alone:" + k] += bool(row[k])
            if row["fails"]:
                tally["+fails"] += 1
                if row["abstract"]:
                    tally["+fails+abstract"] += 1
                    if row["page"]:
                        tally["+fails+abstract+page"] += 1
                        if row["level2"]:
                            tally["+fails+abstract+page+level2"] += 1
        print("\r%d e-prints, %d rows" % (docs, tally["rows"]), end="",
              file=sys.stderr, flush=True)
    print(file=sys.stderr)
    json.dump({"tally": dict(tally), "oversize_skipped": oversize},
              sys.stdout, indent=1)
