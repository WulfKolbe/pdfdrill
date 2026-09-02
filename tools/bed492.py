#!/usr/bin/env python3
r"""492 — a recovery test bed from documents where the context actually exists.

488 measured that the context 487 wants is uneven: an abstract in 67% of
documents, `parent_section` resolving for 70% of math objects and 0% in six
whole documents, and on johnston every parent_section points at level 1,
whose caption is the book's title.

So a bed drawn from johnston cannot test a context-carrying prompt. This one
requires the context to be there, per ROW:

  the document carries an Abstract object
  the row's parent_section resolves to a Section at LEVEL >= 2
  the row has a page
  the row currently DOES NOT RENDER — there is something to improve

and draws only from arXiv e-prints, which are papers and carry the structure
textbooks do not.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pdfdrill import report_tex as rt          # noqa: E402

ARXIV = re.compile(r"^(\d{4}\.\d{4,5}(v\d+)?|[a-z-]+(\.[A-Z]{2})?_?\d{7})$")
TYPED = re.compile(r"_(EQ|FOX?|TAB)\d")


def bed_for(d: Path):
    m = d / "model.docmodel.json"
    tp = list(d.glob("*.tiddlers.json"))
    if not m.is_file() or not tp:
        return []
    try:
        model = json.loads(m.read_text(encoding="utf-8", errors="replace"))
        tids = json.loads(tp[0].read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return []
    tids = tids.get("tiddlers", tids) if isinstance(tids, dict) else tids
    objs = model["objects"]
    # THE REGION IS NOT IN props. It lives on the object's realizations, and
    # `docinspect.object_geometry` is what resolves it — the same function 471
    # used to join model objects to tiddlers at 100% on four documents. The
    # first cut of this scan looked for props["top_left_x"] and found it on 0
    # of 70,000 objects, which is why the bed came back empty.
    from pdfdrill.docinspect import build_stream_index, object_geometry
    sidx = build_stream_index(model)
    abstract = next((o for o in objs if o["type"] == "Abstract"), None)
    if abstract is None:
        return []
    sec = {o["id"]: (o.get("props") or {}) for o in objs if o["type"] == "Section"}
    # the model's math objects, keyed by their region so a tiddler can find them
    def tkey(x):
        try:
            return (int(x["page"]), int(x["top_left_x"]), int(x["top_left_y"]),
                    int(x["width"]), int(x["height"]))
        except (KeyError, TypeError, ValueError):
            return None
    by_region = {}
    for o in objs:
        if o["type"] not in ("Equation", "Formula"):
            continue
        page, bbox, _ = object_geometry(o, sidx)
        if page is None or not bbox:
            continue
        try:
            k = (int(page), int(round(bbox["x"])), int(round(bbox["y"])),
                 int(round(bbox["w"])), int(round(bbox["h"])))
        except (KeyError, TypeError, ValueError):
            continue
        by_region.setdefault(k, o)
    out = []
    for x in tids:
        title = x.get("title", "")
        lx = x.get("latex") or ""
        if not lx or not TYPED.search(title):
            continue
        if rt.renderable(lx):
            continue                       # it renders — nothing to improve
        k = tkey(x)
        o = by_region.get(k)
        if o is None:
            continue                       # 439's join: region -> title
        props = o.get("props") or {}
        ps = sec.get(props.get("parent_section") or "")
        if not ps:
            continue
        try:
            level = int(ps.get("level") or 0)
        except (TypeError, ValueError):
            level = 0
        if level < 2:
            continue                       # level 1 is the document's own title
        out.append({"doc": d.name, "id": title, "page": x.get("page"),
                    "conf": x.get("confidence"),
                    "uri": x.get("canonical_uri") or "",
                    "section": ps.get("caption", ""), "section_level": level,
                    "flow_index": props.get("flow_index"),
                    "abstract_chars": len((abstract.get("props") or {})
                                          .get("text", "")),
                    "latex": lx})
    return out


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / "pdfdrill-library"
    bed, n, seen = [], 0, 0
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        if not ARXIV.match(d.name):
            continue
        n += 1
        rows = bed_for(d)
        if rows:
            seen += 1
            bed.extend(rows)
        print("\r%d e-prints, %d qualifying, %d rows" % (n, seen, len(bed)),
              end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    json.dump({"eprints_scanned": n, "documents": seen, "rows": bed},
              sys.stdout, indent=1, ensure_ascii=False)
