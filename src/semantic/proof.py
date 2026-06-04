"""
Proof layer — answer the provenance questions about any node:

  * why was this node created?   → created_by()  (the originating sensor)
  * which evidence supports it?  → evidence_supporting() / evidence_for_prop()
  * which agent produced it?     → processes()
  * which version produced it?   → versions()
  * from which documents?        → sources()

Pure functions over an Entity's accumulated Evidence — the audit trail that makes
the graph defensible rather than a "trust me" extraction.
"""
from __future__ import annotations

from typing import Optional

from .entity import Entity
from .evidence import Evidence


def evidence_supporting(entity: Entity) -> list[Evidence]:
    return list(entity.evidence)


def evidence_for_prop(entity: Entity, prop: str) -> list[Evidence]:
    return entity.evidence_for(prop)


def processes(entity: Entity) -> set[str]:
    return {e.produced_by for e in entity.evidence}


def sources(entity: Entity) -> set[str]:
    return {e.source for e in entity.evidence}


def created_by(entity: Entity) -> Optional[str]:
    """The sensor whose observation first created this node."""
    return entity.evidence[0].produced_by if entity.evidence else None


def versions(entity: Entity) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for e in entity.evidence:
        out.setdefault(e.produced_by, set()).add(e.version)
    return out


def explain(entity: Entity) -> dict[str, object]:
    """A compact provenance summary for one node."""
    return {"id": entity.id, "type": entity.type.value,
            "created_by": created_by(entity),
            "processes": sorted(processes(entity)),
            "sources": sorted(sources(entity)),
            "evidence_count": len(entity.evidence)}
