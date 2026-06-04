"""
IdentityResolver — the heart of the design.

Three responsibilities, exactly as specified:
  * find_existing_entity()  — is this real-world thing already in the graph?
  * create_entity()         — if not, mint a stable node
  * attach_evidence()       — every sensor's observation lands on the entity

`resolve()` composes them: find-or-create by identity key, then attach evidence.
Identity keys come in two strengths:
  * STRONG (iban/vat/bic/email/tax_id): an exact normalised match ⇒ same entity.
  * SOFT (name): exact normalised match for now; fuzzy (rapidfuzz) is a later
    refinement (kept separate — entities are merged only on strong evidence).
Strong-key evidence is indexed when attached, so a later document that mentions
only the IBAN still resolves to the company first seen by name.
"""
from __future__ import annotations

from typing import Iterable, Optional

from .entity import Entity, EntityType
from .evidence import Evidence
from .graph import SemanticGraph

# Properties whose value is a strong identity key (globally ~unique per entity).
STRONG_KEYS = {"iban", "vat", "vatid", "tax_id", "taxid", "bic", "email",
               "customer_number", "contract_number"}
# Properties usable as a soft identity key.
SOFT_KEYS = {"name", "title"}


def _norm(kind: str, value: str) -> str:
    v = " ".join(str(value).split()).lower()
    if kind in STRONG_KEYS:
        v = v.replace(" ", "")
    return v


class IdentityResolver:
    def __init__(self, graph: SemanticGraph) -> None:
        self.graph = graph
        self._index: dict[tuple, str] = {}      # (kind, norm_value) -> entity id

    def reindex(self) -> "IdentityResolver":
        """Rebuild the identity index from the graph's existing entities — call
        after loading a persisted graph so cross-run accumulation resolves to the
        already-known entities."""
        self._index.clear()
        for e in self.graph.entities.values():
            for ev in e.evidence:
                if ev.prop in STRONG_KEYS or ev.prop in SOFT_KEYS:
                    self._register(ev.prop, ev.value, e.id)
        return self

    def find_existing_entity(self, type: EntityType,
                             keys: Iterable[tuple]) -> Optional[Entity]:
        for kind, value in keys:
            eid = self._index.get((kind, _norm(kind, value)))
            e = self.graph.get(eid) if eid else None
            if e is not None and e.type == type:
                return e
        return None

    def create_entity(self, type: EntityType, subtype: str = "") -> Entity:
        return self.graph.add_entity(
            Entity(id=self.graph.new_id(type), type=type, subtype=subtype))

    def _register(self, kind: str, value: str, entity_id: str) -> None:
        self._index[(kind, _norm(kind, value))] = entity_id

    def attach_evidence(self, entity: Entity, evidence: Iterable[Evidence]) -> None:
        for ev in evidence:
            entity.attach(ev)
            # Index strong/soft-key observations so future docs resolve to here.
            if ev.prop in STRONG_KEYS or ev.prop in SOFT_KEYS:
                self._register(ev.prop, ev.value, entity.id)

    def resolve(self, type: EntityType, keys: Iterable[tuple] = (),
                evidence: Iterable[Evidence] = (), subtype: str = "") -> Entity:
        keys = list(keys)
        e = self.find_existing_entity(type, keys)
        if e is None:
            e = self.create_entity(type, subtype)
        for kind, value in keys:
            self._register(kind, value, e.id)
        self.attach_evidence(e, list(evidence))
        return e
