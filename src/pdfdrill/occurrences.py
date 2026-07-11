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

# tiddler title scheme per type (flow order) — matches tiddlywiki.py / distill so a
# record round-trips to its tiddler by title.
_TITLE_FMT = {
    "Equation": "{b}_EQ{i:04d}", "Table": "{b}_TAB_{i:03d}",
    "Picture": "{b}_PIC_{i:04d}", "Diagram": "{b}_DIA_{i:04d}",
}
REGION_TYPES = tuple(_TITLE_FMT)


def _titles(objects: list, bibkey: str) -> dict:
    flow = lambda o: getattr(o, "props", {}).get("flow_index") or 0
    titles: dict = {}
    for typ, fmt in _TITLE_FMT.items():
        for i, o in enumerate(sorted((o for o in objects
                                      if getattr(o, "type", "") == typ), key=flow), 1):
            titles[getattr(o, "id", "")] = fmt.format(b=bibkey, i=i)
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
