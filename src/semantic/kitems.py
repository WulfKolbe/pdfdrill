"""
Kitems — knowledge items as graph entities (the two-store plan, store half).

Documents are the axioms (ground truth of "this was written, here"); kitems
are theorems; the evidence chain is the proof object. The decision record:
kitems live CANONICALLY in the semantic graph — `statement_md`/`status`/
`stratum` are properties, the evidence chain is `Evidence` rows whose
`grounding` carries the span (bibkey + node + fractional-index range + role),
and kitem_derivation is `DERIVED_FROM` edges. The `kitem`/`kitem_evidence`
SQL tables are G4 **projections** (sqlite_view), never a second writable
store.

The honesty invariant (TOWER's support-chain rule, applied here): **every
kitem must be reachable down to at least one span, transitively** — and its
`status` says how far that proof goes:

    proposed    a pass emitted it; no grounded span yet
    supported   every evidence row carries a span, or (a derivation) every
                parent is supported
    accepted    >= 2 INDEPENDENT spans (distinct bibkey+node) in the
                transitive closure — the corroboration rule
    disputed    a CONTRADICTS edge touches it (human or contradiction kitem;
                no LLM ever promotes, only this demotes)

Content-hash identity makes re-emitting the same statement a fixpoint no-op:
the entity is found, new evidence accumulates, no duplicate is minted.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from .entity import EntityType
from .evidence import Evidence
from .relation import RelationType
from .layers import content_identity

_WS = re.compile(r"\s+")


def kitem_hash(statement_md: str) -> str:
    """blake2b of the whitespace-normalized statement, namespaced so a kitem
    never collides with a formula's content hash."""
    return content_identity.content_hash("kitem|" + _WS.sub(" ", statement_md).strip())


def emit_kitem(graph, resolver, statement_md: str, *, kind: str, stratum: int,
               spans: Optional[list[dict[str, Any]]] = None,
               derived_from: Optional[list[str]] = None,
               produced_by: str = "", valid_at: str = ""):
    """Emit (or re-find) a kitem. spans: [{bibkey, node, range|ord, role,
    page?, excerpt?}] — each becomes an Evidence row with span grounding.
    Idempotent: same normalized statement -> same entity, evidence accumulates
    (duplicate spans are skipped)."""
    h = kitem_hash(statement_md)
    ev = [Evidence("kitem", "statement_md", _WS.sub(" ", statement_md).strip(),
                   produced_by, confidence=1.0),
          Evidence("kitem", "kind", kind, produced_by, confidence=1.0),
          Evidence("kitem", "stratum", stratum, produced_by, confidence=1.0)]
    if valid_at:
        ev.append(Evidence("kitem", "valid_at", valid_at, produced_by, confidence=1.0))
    e = resolver.resolve(EntityType.KITEM, keys=[("content_hash", h)], evidence=ev)
    if not e.subtype:
        e.subtype = kind
    # ensure the hash itself is a queryable property
    if not any(x.prop == "content_hash" for x in e.evidence):
        e.attach(Evidence("kitem", "content_hash", h, produced_by, confidence=1.0))

    existing = {(x.grounding or {}).get("node"): (x.grounding or {}).get("range")
                for x in e.evidence if x.prop == "span"}
    for sp in spans or []:
        node, rng = sp.get("node"), sp.get("range") or sp.get("ord") or ""
        if node in existing and existing[node] == rng:
            continue                                    # fixpoint no-op
        g = {"bibkey": sp.get("bibkey", ""), "node": node, "range": rng,
             "role": sp.get("role", "asserts")}
        if sp.get("page") is not None:
            g["page"] = sp["page"]
        e.attach(Evidence(sp.get("bibkey", ""), "span",
                          sp.get("excerpt", "") or rng, produced_by,
                          confidence=1.0, grounding=g))
        existing[node] = rng

    for pid in derived_from or []:
        if not graph.has_relation(e.id, RelationType.DERIVED_FROM, pid):
            graph.relate(e.id, RelationType.DERIVED_FROM, pid,
                         produced_by=produced_by,
                         grounding={"layer": "kitem_derivation"})
    return e


def _own_spans(entity) -> list[dict]:
    return [x.grounding or {} for x in entity.evidence
            if x.prop == "span" and (x.grounding or {}).get("node")]


def _transitive_spans(graph, kitem_id: str, _seen: Optional[set] = None) -> list[dict]:
    """Own spans plus every parent's, following DERIVED_FROM (cycle-safe;
    the compiler separately enforces the DAG)."""
    seen = _seen if _seen is not None else set()
    if kitem_id in seen:
        return []
    seen.add(kitem_id)
    e = graph.get(kitem_id)
    if e is None:
        return []
    spans = _own_spans(e)
    for rel in graph.relations_of(kitem_id, RelationType.DERIVED_FROM):
        spans += _transitive_spans(graph, rel.object_id, seen)
    return spans


def status_of(graph, kitem_id: str) -> str:
    """Compiler-automatic status (see module docstring). Disputed wins."""
    e = graph.get(kitem_id)
    if e is None:
        return "unknown"
    contradicted = any(r.predicate == RelationType.CONTRADICTS
                       for r in graph.relations_to(kitem_id))
    if contradicted:
        return "disputed"
    spans = _transitive_spans(graph, kitem_id)
    independent = {(s.get("bibkey"), s.get("node")) for s in spans}
    if len(independent) >= 2:
        return "accepted"
    if independent:
        return "supported"
    # a derivation with no spans anywhere below is unproven
    return "proposed"


def all_kitems(graph) -> list:
    return [e for e in graph.entities.values() if e.type == EntityType.KITEM]


def kitem_tiddlers(graph, bibkey: str) -> list[dict[str, Any]]:
    """$Bibkey_KI<serial> tiddlers — statement + status + the drill-down hash.

    The text leads with the ONE shallow statement line; provenance follows as
    a list of bibkey/page pointers (the wiki-side drill-down handles)."""
    out = []
    for i, e in enumerate(sorted(all_kitems(graph), key=lambda e: e.id), start=1):
        p = e.properties()
        spans = _own_spans(e)
        prov = " ".join(
            f"[{s.get('bibkey', '?')}" + (f" p{s['page']}" if s.get("page") is not None
                                          else "") + "]"
            for s in spans)
        out.append({
            "title": f"{bibkey}_KI{i:04d}",
            "text": (p.get("statement_md", "") +
                     (f"\n\n''evidence:'' {prov}" if prov else "")),
            "kind": e.subtype or p.get("kind", ""),
            "status": status_of(graph, e.id),
            "stratum": str(p.get("stratum", "")),
            "khash": p.get("content_hash", "") or kitem_hash(p.get("statement_md", "")),
            "tags": "kitem " + (e.subtype or ""),
            "type": "text/vnd.tiddlywiki",
        })
    return out
