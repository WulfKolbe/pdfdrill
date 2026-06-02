"""
Relation dataclass — a flat directed edge between two feature ids.

Kept flat (source/target/type/weight): no nested arrays of objects. A list of
`Relation` feeds `graph_builder.build_graph` for grouping / citation graphs / etc.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Relation:
    source: str
    target: str
    type: str
    weight: float

    def to_dict(self) -> dict:
        return asdict(self)
