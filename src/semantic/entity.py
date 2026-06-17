"""
Entity — a stable, typed identity node in the semantic graph (the Entity Layer).

An entity is NOT a field value. It is a real-world thing (a Company, a Person, a
Paper, a Formula) whose properties are *derived from accumulated evidence*. The
same entity gathers evidence across many documents over time — that is what lets
the graph track identity (a company moving offices, gaining bank accounts, …)
which a flat chunk/field store cannot.

The type vocabulary unifies scientific and commercial domains deliberately:
`provenance`, `contains`, `derived_from` apply equally to a paper and an invoice.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .evidence import Evidence


def _evidence_order_key(ev: Evidence) -> str:
    """A stable, content-derived tiebreak key for evidence of equal confidence —
    so `best()` (and anything built on it, e.g. derived belief) is reproducible
    regardless of the order evidence was attached/ingested."""
    return hashlib.blake2b(
        f"{ev.prop}|{ev.value}|{ev.produced_by}|{ev.version}".encode("utf-8"),
        digest_size=8).hexdigest()


class EntityType(str, Enum):
    # people & organisations
    PERSON = "person"
    COMPANY = "company"
    ORGANIZATION = "organization"
    AUTHORITY = "authority"
    BANK = "bank"
    DEPARTMENT = "department"
    # documents (scientific + commercial)
    DOCUMENT = "document"
    PAPER = "paper"
    # scientific objects
    FORMULA = "formula"
    IMAGE = "image"
    TABLE = "table"
    CITATION = "citation"
    CONCEPT = "concept"
    # commercial objects
    BANK_ACCOUNT = "bank_account"
    # cross-cutting
    EVENT = "event"
    # knowledge items (the two-store plan): derived assertions whose existence
    # is justified ONLY by evidence chains down to spans. Subtypes: rule |
    # claim | definition | derivation | reuse_event | contradiction.
    KITEM = "kitem"


@dataclass
class Entity:
    id: str
    type: EntityType
    subtype: str = ""
    evidence: list[Evidence] = field(default_factory=list)

    # -- evidence accumulation ------------------------------------------------
    def attach(self, ev: Evidence) -> None:
        self.evidence.append(ev)

    def evidence_for(self, prop: str) -> list[Evidence]:
        return [e for e in self.evidence if e.prop == prop]

    def best(self, prop: str) -> Optional[Evidence]:
        """The most trustworthy evidence for a property: highest confidence,
        ties broken by DETERMINISTIC content-hash ordering (not recency) — so the
        derived value is reproducible regardless of ingestion/attachment order."""
        evs = self.evidence_for(prop)
        if not evs:
            return None
        return max(evs, key=lambda e: (e.confidence, _evidence_order_key(e)))

    def properties(self) -> dict[str, str]:
        """Derived view: the best value per observed property."""
        props: dict[str, str] = {}
        for e in self.evidence:
            if e.prop not in props:
                props[e.prop] = ""        # preserve first-seen order
        return {p: self.best(p).value for p in props}

    @property
    def value(self) -> str:
        """A display value: prefer name/title, else the first property."""
        for p in ("name", "title", "value"):
            b = self.best(p)
            if b:
                return b.value
        props = self.properties()
        return next(iter(props.values()), self.id)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "type": self.type.value, "subtype": self.subtype,
                "properties": self.properties(),
                "evidence": [e.to_dict() for e in self.evidence]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Entity":
        e = cls(id=d["id"], type=EntityType(d["type"]), subtype=d.get("subtype", ""))
        e.evidence = [Evidence.from_dict(x) for x in d.get("evidence", [])]
        return e
