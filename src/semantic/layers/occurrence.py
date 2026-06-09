"""
LAYER 3 — occurrence (dual-positioned).  (Gap 3, restated to the real spec.)

For every occurrence-bearing item (numbered equation, unreferenced math, table,
LaTeX figure, external source, bib entry, symbol/index term) this records WHERE
it occurs in BOTH coordinate systems the brief requires:

  * PDF position      grounding["pdf"]  = {"page": int, "bbox": [x0,y0,x1,y1]}
  * logical position  the edge's OBJECT = the containing structural node
                      grounding["path"] = human path, e.g. "I.2.3"  (optional)

`role` separates the defining / first occurrence ("definition") from further
ones ("reference"). A document-order key `ord` lets occurrences sort, so
"first by reading order" is the min and is independent of insertion order.

Composable & round-trip-safe: an edge on the existing REFERENCES predicate with
a grounding discriminator {"layer":"occurrence", ...}. No new enum needed; the
clean promotion later is one RelationType line (OCCURS_IN) + a search-replace.

NOTE on the nine items: items 1 (PDF pages/geometry) and 2 (logical tree) are the
TWO COORDINATE SYSTEMS occurrences point into — they are NOT occurrence-bearing.
Item 3's TOC / front matter are DERIVED VIEWS (traversals), not stored here;
symbols / index terms ARE items and use this layer. Items 4–9 are items.

    define(g, item, in_node, *, pdf=None, path="", doc_ord=None, ...)
    add_occurrence(g, item, in_node, *, pdf=None, path="", doc_ord=None, ...)
    definition(g, item)             -> the defining edge (role=definition, else min ord)
    occurrences(g, item)            -> ALL occurrence edges, in document order
    further_occurrences(g, item)    -> occurrences minus the definition
"""
from __future__ import annotations

from typing import List, Optional
from ..fracidx import key_between

# In-repo: `from semantic.relation import RelationType`.
from ..relation import RelationType

_PRED = RelationType.REFERENCES        # carrier predicate (promote to OCCURS_IN later)
_LAYER = "occurrence"


def _g(r) -> dict:
    return r.grounding or {}


def _ord(r) -> str:
    return _g(r).get("ord", "")


def _is_occ(r) -> bool:
    return _g(r).get("layer") == _LAYER


def _last_ord(graph, item_id: str) -> Optional[str]:
    ks = [_ord(r) for r in graph.relations_of(item_id, _PRED) if _is_occ(r) and _ord(r)]
    return max(ks) if ks else None


def _record(graph, item_id: str, in_node_id: str, role: str,
            pdf: Optional[dict], path: str, doc_ord: Optional[str], **kw):
    g = {"layer": _LAYER, "role": role,
         "ord": doc_ord if doc_ord is not None else key_between(_last_ord(graph, item_id), None)}
    if pdf is not None:
        g["pdf"] = pdf                       # {"page": int, "bbox": [x0,y0,x1,y1]}
    if path:
        g["path"] = path
    return graph.relate(item_id, _PRED, in_node_id, grounding=g, **kw)


def define(graph, item_id: str, in_node_id: str, *, pdf: Optional[dict] = None,
           path: str = "", doc_ord: Optional[str] = None, **kw):
    """The definition / first occurrence (where the item is introduced)."""
    return _record(graph, item_id, in_node_id, "definition", pdf, path, doc_ord, **kw)


def add_occurrence(graph, item_id: str, in_node_id: str, *, pdf: Optional[dict] = None,
                   path: str = "", doc_ord: Optional[str] = None, **kw):
    """A further occurrence (a reference / repeat appearance)."""
    return _record(graph, item_id, in_node_id, "reference", pdf, path, doc_ord, **kw)


def occurrences(graph, item_id: str) -> List:
    return sorted((r for r in graph.relations_of(item_id, _PRED) if _is_occ(r)), key=_ord)


def definition(graph, item_id: str):
    occ = occurrences(graph, item_id)
    for r in occ:
        if _g(r).get("role") == "definition":
            return r
    return occ[0] if occ else None          # fall back to first by reading order


def further_occurrences(graph, item_id: str) -> List:
    d = definition(graph, item_id)
    return [r for r in occurrences(graph, item_id) if r is not d]
