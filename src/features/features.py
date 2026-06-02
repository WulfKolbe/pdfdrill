"""
Feature dataclass — a flat, source-agnostic extracted item.

This package is an ADDITIVE layer: extractors receive plain text (str) and emit
`Feature` objects. They never read PDF/PNG/MathPix/Markdown specifics and never
modify the pdfdrill / docmodel / docops pipeline — they only *read* text and
*add* features (and `relations.Relation` edges between them).
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class Feature:
    id: str
    page_id: str
    type: str
    value: str
    confidence: float
    start: Optional[int] = None
    end: Optional[int] = None

    @classmethod
    def create(cls, page_id: str, type: str, value: str, confidence: float,
               start: Optional[int] = None, end: Optional[int] = None) -> "Feature":
        """Build a Feature with a deterministic id from (type, page_id, span, value)."""
        h = hashlib.sha1(
            f"{type}|{page_id}|{start}|{value}".encode("utf-8")).hexdigest()[:12]
        return cls(id=f"{type.lower()}-{h}", page_id=page_id, type=type,
                   value=value, confidence=round(float(confidence), 4),
                   start=start, end=end)

    def to_dict(self) -> dict:
        return asdict(self)
