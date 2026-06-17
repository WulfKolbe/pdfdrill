"""
belief — a derived REPORT COLUMN, not a source of truth.

The honesty ethos of this package keeps `status` (the kitems lattice) the only
authoritative judgement of a claim. Some downstream views still want a single
propagated confidence number; this module provides exactly one, computed lazily
over the `derived_from` DAG and exposed ONLY as a projector/proof column —
never written back to an Entity/Evidence that another pass reads, and never fed
into the kitems `status`.

The operator is conservative weakest-link:

    belief(node) = min(belief(parents)) * own_confidence
                 = own_confidence                       if it has no parents

`min` (not mean/Bayesian) matches the project's stance: a derivation is no more
believable than its least-believable input. The `derived_from` graph is already
guaranteed acyclic by `compiler.check_acyclic`, so the lazy recursion terminates
(a memo also guards against an accidental cycle). Reproducibility rests on
`Entity.best()` being deterministic (content-hash tiebreak), so belief is
identical regardless of the order documents were ingested.
"""
from __future__ import annotations

from .relation import RelationType


def belief_min(parent_beliefs: list[float], own_confidence: float) -> float:
    """Weakest-link: the min of the parents' beliefs scaled by own confidence,
    or own confidence alone when there are no parents."""
    if not parent_beliefs:
        return own_confidence
    return min(parent_beliefs) * own_confidence


def own_confidence(entity) -> float:
    """An entity's intrinsic confidence: the strongest confidence among its own
    evidence (order-independent — the set of evidence is the same regardless of
    ingestion order), defaulting to 1.0 for an entity with no evidence."""
    return max((ev.confidence for ev in entity.evidence), default=1.0)


def belief_of(graph, entity_id: str, _memo: dict | None = None) -> float:
    """Lazy weakest-link belief over `derived_from`. Pure read over the graph."""
    memo = _memo if _memo is not None else {}
    if entity_id in memo:
        return memo[entity_id]
    e = graph.get(entity_id)
    if e is None:
        return 1.0
    memo[entity_id] = 0.0                       # cycle guard (DAG is enforced elsewhere)
    parents = sorted({r.object_id for r in
                      graph.relations_of(entity_id, RelationType.DERIVED_FROM)})
    pbel = [belief_of(graph, p, memo) for p in parents if graph.get(p) is not None]
    b = belief_min(pbel, own_confidence(e))
    memo[entity_id] = b
    return b


def belief_column(graph) -> dict[str, float]:
    """The belief of every entity, as a {entity_id: belief} column for a
    projector / proof query. A pure read — it writes nothing back to the graph."""
    memo: dict[str, float] = {}
    return {eid: belief_of(graph, eid, memo) for eid in graph.entities}
