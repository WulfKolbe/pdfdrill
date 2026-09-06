"""
occurrences — a clean per-element region list (page + bbox + tiddler title) for the
OPTIONAL external image-enrichment tools (e.g. enrich_table_tiddlers.py, a future
fraction position/length fixer). Each tool reads this instead of parsing the full
tiddlers.json, and locates the element on the rendered page by its region — no
content matching.

Scoped to REGION-BEARING element types: Equation by default (Table/Picture/Diagram
opt-in via `types`). Inline Formula is intentionally EXCLUDED — it is content-deduped
(one object, many occurrences), so it has no single per-object region; MathPix gives
none, and the pdfminer.six CTM chain is the intended future source of those.
"""
from __future__ import annotations

# 644 — the region-bearing types this module names. The SHAPES come from
# `docops…tiddlywiki.TITLE_SHAPES` via `title_for`, so a record round-trips to
# its tiddler by title without a second copy of the scheme living here.
REGION_TYPES = ("Equation", "Table", "Picture", "Diagram")


def _titles(objects: list, bibkey: str) -> dict:
    from docops.projectors.tiddlywiki import title_for

    flow = lambda o: getattr(o, "props", {}).get("flow_index") or 0
    titles: dict = {}
    for typ in REGION_TYPES:
        for i, o in enumerate(sorted((o for o in objects
                                      if getattr(o, "type", "") == typ), key=flow), 1):
            titles[getattr(o, "id", "")] = title_for(bibkey, typ, i)
    return titles


def occurrence_records(objects, bibkey: str,
                       types: "tuple[str, ...]" = ("Equation",)) -> list:
    """Region records for the requested region-bearing types, in flow order.
    Each: {title, id, type, page, top_left_x/y, width, height, [refnum],
    [equation_number], [latex]}. Objects without a `region` are skipped."""
    objects = list(objects)
    titles = _titles(objects, bibkey)
    out = []
    for o in objects:
        t = getattr(o, "type", "")
        if t not in types:
            continue
        p = getattr(o, "props", {})
        reg = p.get("region")
        if not reg:
            continue
        rec = {
            "title": titles.get(getattr(o, "id", ""), ""),
            "id": getattr(o, "id", ""),
            "type": t,
            "page": p.get("page"),
            "top_left_x": reg.get("top_left_x"),
            "top_left_y": reg.get("top_left_y"),
            "width": reg.get("width"),
            "height": reg.get("height"),
        }
        for k in ("refnum", "equation_number", "latex"):
            if p.get(k) not in (None, ""):
                rec[k] = p[k]
        out.append(rec)
    return out
