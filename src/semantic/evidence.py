"""
Evidence — the atomic observation a SENSOR (extractor/process) emits.

This is the Proof-Layer primitive: every property of every entity, and every
relation, is backed by Evidence that records *what was observed*, *where*
(grounding), *which process produced it*, and *which version*. Extractors never
create final entities; they emit Evidence that an IdentityResolver attaches to
the right entity. The address/IBAN/VAT are evidence pointing at an entity, not
the entity itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Evidence:
    source: str                 # document / region / page id the observation came from
    prop: str                   # property name: name/address/iban/title/year/…
    value: str                  # the observed (normalised) value
    produced_by: str            # the Process/sensor that emitted it (libpostal/iban/ner/mathpix…)
    version: str = ""           # process version (proof layer)
    confidence: float = 1.0     # 0..1
    grounding: Optional[dict[str, Any]] = None  # {block_id, start, end, bbox, …}

    def to_dict(self) -> dict[str, Any]:
        d = {"source": self.source, "prop": self.prop, "value": self.value,
             "produced_by": self.produced_by, "confidence": self.confidence}
        if self.version:
            d["version"] = self.version
        if self.grounding:
            d["grounding"] = self.grounding
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Evidence":
        return cls(source=d["source"], prop=d["prop"], value=d["value"],
                   produced_by=d.get("produced_by", ""), version=d.get("version", ""),
                   confidence=d.get("confidence", 1.0), grounding=d.get("grounding"))
