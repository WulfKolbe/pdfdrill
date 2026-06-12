"""
Semantic bundles — the gluing made visible.

A bundle is the per-entity GLOBAL SECTION: everything the graph knows about
one resolved identity, assembled into a single dict — canonical name, the
aliases evidence supplied, the dual-positioned mentions (G3 occurrences,
document order), the claims (evidence rows with provenance), and the linked
nodes per predicate. It is a **derived view, never a second writable store**:
re-running `bundle()` after new sensor passes reflects the new state with no
sync problem. (The decision record: a stored bundle node would be a cached
join that drifts; everything here is recomputed from Entity + Relation +
grounding on demand.)

`all_bundles(graph)` feeds the SQLite projection (sqlite_view.load_view
`bundles=` parameter) so a query hit on ANY alias can surface the whole
bundle — the search story.
"""
from __future__ import annotations

from typing import Any, Optional

from .entity import EntityType
from .layers import occurrence

# evidence props that name the entity (alias sources, best first)
_NAME_PROPS = ("name", "title", "expansion", "latex", "citekey")


def bundle(graph, entity_id: str) -> Optional[dict[str, Any]]:
    """The global section for one entity (None if unknown)."""
    e = graph.get(entity_id)
    if e is None:
        return None
    props = e.properties() if callable(getattr(e, "properties", None)) else {}

    canonical = next((props[p] for p in _NAME_PROPS if props.get(p)), e.id)
    aliases: list[str] = []
    for ev in e.evidence:
        if ev.prop in _NAME_PROPS and ev.value and ev.value not in aliases:
            aliases.append(str(ev.value))

    mentions = []
    for r in occurrence.occurrences(graph, entity_id):
        g = r.grounding or {}
        pdf = g.get("pdf") or {}
        mentions.append({"node": r.object_id, "role": g.get("role", ""),
                         "page": pdf.get("page"), "bbox": pdf.get("bbox"),
                         "path": g.get("path", ""), "ord": g.get("ord", "")})

    claims = [{"prop": ev.prop, "value": ev.value, "produced_by": ev.produced_by,
               "confidence": ev.confidence, "source": ev.source}
              for ev in e.evidence]

    linked: dict[str, list[str]] = {}
    for r in graph.relations_of(entity_id):
        if (r.grounding or {}).get("layer") == "occurrence":
            continue                      # mentions already carry these
        key = r.predicate.value if hasattr(r.predicate, "value") else str(r.predicate)
        linked.setdefault(key, []).append(r.object_id)
    for r in graph.relations_to(entity_id):
        if (r.grounding or {}).get("layer") == "occurrence":
            continue
        key = r.predicate.value if hasattr(r.predicate, "value") else str(r.predicate)
        linked.setdefault(key + "_of", []).append(r.subject_id)

    # consistency: no CONTRADICTS edge touches this entity, and every mention
    # is grounded in at least one coordinate system (pdf page or logical path).
    contradicted = any(
        (r.predicate.value if hasattr(r.predicate, "value") else str(r.predicate))
        == "contradicts"
        for r in graph.relations_of(entity_id) + graph.relations_to(entity_id))
    ungrounded = [m for m in mentions if m["page"] is None and not m["path"]]
    consistent = not contradicted and not ungrounded

    return {"id": entity_id, "type": e.type.value, "subtype": e.subtype,
            "canonical": str(canonical), "aliases": aliases,
            "mentions": mentions, "claims": claims, "linked": linked,
            "consistent": consistent}


def all_bundles(graph, types: tuple = (EntityType.CONCEPT, EntityType.FORMULA,
                                       EntityType.CITATION, EntityType.TABLE,
                                       EntityType.IMAGE)) -> list[dict[str, Any]]:
    """Bundles for every entity of the given types (the search index feed)."""
    out = []
    for e in graph.entities.values():
        if e.type in types:
            b = bundle(graph, e.id)
            if b is not None:
                out.append(b)
    return out
