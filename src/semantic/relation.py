"""
Relation — a typed, provenance-bearing edge between two entities (Relation Layer).

Relations are primary: objects are stable patterns of relations. The predicate
vocabulary is deliberately domain-spanning — `cites`/`derived_from`/`contains`
serve a paper and an invoice alike — plus the commercial edges the invoice model
needs. Every relation records which process produced it and what grounds it.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class RelationType(str, Enum):
    # CSP relation layer (domain-agnostic)
    CITES = "cites"
    DERIVED_FROM = "derived_from"
    EXPLAINS = "explains"
    CONTAINS = "contains"
    CONTRADICTS = "contradicts"
    IMPLEMENTS = "implements"
    # commercial / organisational
    OWNS = "owns"
    SENDER = "sender"
    RECEIVER = "receiver"
    REPRESENTED_BY = "represented_by"
    ACTS_FOR = "acts_for"
    PUBLISHES = "publishes"
    BELONGS_TO = "belongs_to"
    ISSUED_BY = "issued_by"
    SENT_TO = "sent_to"
    HAS_ATTACHMENT = "has_attachment"
    REFERENCES = "references"


@dataclass
class Relation:
    subject_id: str
    predicate: RelationType
    object_id: str
    confidence: float = 1.0
    produced_by: str = ""
    version: str = ""
    grounding: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        d = {"subject_id": self.subject_id, "predicate": self.predicate.value,
             "object_id": self.object_id, "confidence": self.confidence,
             "produced_by": self.produced_by}
        if self.version:
            d["version"] = self.version
        if self.grounding:
            d["grounding"] = self.grounding
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Relation":
        return cls(subject_id=d["subject_id"], predicate=RelationType(d["predicate"]),
                   object_id=d["object_id"], confidence=d.get("confidence", 1.0),
                   produced_by=d.get("produced_by", ""), version=d.get("version", ""),
                   grounding=d.get("grounding"))
