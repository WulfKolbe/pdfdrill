"""
SemanticGraph — the primary artifact.

A persistent container of typed Entities and typed Relations. Extractors feed
evidence into it via the IdentityResolver; the graph is what accumulates and
survives across documents (and, persisted to the sidecar, across runs). This is
the inversion the design demands: the graph is primary, extractors are sensors.
"""
from __future__ import annotations

from typing import Any, Optional

from .entity import Entity, EntityType


class SemanticGraph:
    def __init__(self) -> None:
        self.entities: dict[str, Entity] = {}
        self.relations: list = []          # list[Relation]; typed in relation.py
        self._counters: dict[str, int] = {}

    # -- entities -------------------------------------------------------------
    def new_id(self, type: EntityType) -> str:
        slug = type.value if isinstance(type, EntityType) else str(type)
        self._counters[slug] = self._counters.get(slug, 0) + 1
        return f"{slug}:{self._counters[slug]}"

    def add_entity(self, e: Entity) -> Entity:
        self.entities[e.id] = e
        return e

    def get(self, entity_id: str) -> Optional[Entity]:
        return self.entities.get(entity_id)

    def entities_of(self, type: EntityType) -> list[Entity]:
        return [e for e in self.entities.values() if e.type == type]

    def entity_count(self, type: Optional[EntityType] = None) -> int:
        return len(self.entities) if type is None else len(self.entities_of(type))

    # -- relations ------------------------------------------------------------
    def relate(self, subject_id: str, predicate, object_id: str,
               confidence: float = 1.0, produced_by: str = "", version: str = "",
               grounding: Optional[dict] = None):
        from .relation import Relation
        r = Relation(subject_id=subject_id, predicate=predicate, object_id=object_id,
                     confidence=confidence, produced_by=produced_by, version=version,
                     grounding=grounding)
        self.relations.append(r)
        return r

    def relations_of(self, entity_id: str, predicate=None) -> list:
        return [r for r in self.relations if r.subject_id == entity_id
                and (predicate is None or r.predicate == predicate)]

    def relations_to(self, entity_id: str, predicate=None) -> list:
        return [r for r in self.relations if r.object_id == entity_id
                and (predicate is None or r.predicate == predicate)]

    def has_relation(self, subject_id: str, predicate, object_id: str) -> bool:
        return any(r.subject_id == subject_id and r.predicate == predicate
                   and r.object_id == object_id for r in self.relations)

    def relate_once(self, subject_id: str, predicate, object_id: str, **kw):
        """relate(), but skip if an identical (subject,predicate,object) edge
        already exists — so re-ingesting a document doesn't duplicate edges."""
        if self.has_relation(subject_id, predicate, object_id):
            return None
        return self.relate(subject_id, predicate, object_id, **kw)

    # -- serialization --------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {"entities": [e.to_dict() for e in self.entities.values()],
                "relations": [r.to_dict() for r in self.relations]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SemanticGraph":
        from .relation import Relation
        g = cls()
        for ed in d.get("entities", []):
            g.add_entity(Entity.from_dict(ed))
        g.relations = [Relation.from_dict(rd) for rd in d.get("relations", [])]
        # restore id counters so new_id keeps incrementing past loaded ids
        for e in g.entities.values():
            slug = e.type.value
            try:
                n = int(e.id.rsplit(":", 1)[1])
                g._counters[slug] = max(g._counters.get(slug, 0), n)
            except (ValueError, IndexError):
                pass
        return g
