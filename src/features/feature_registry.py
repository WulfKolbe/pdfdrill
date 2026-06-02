"""
FeatureRegistry — a lightweight in-memory store of extracted Features.

Flat by design: a single list, queried by type. No nesting, no coupling to the
existing pipeline.
"""
from __future__ import annotations

from .features import Feature


class FeatureRegistry:
    def __init__(self) -> None:
        self._features: list[Feature] = []

    def register_feature(self, feature: Feature) -> None:
        self._features.append(feature)

    def register_many(self, features: list[Feature]) -> None:
        self._features.extend(features)

    def find_features(self, type: str) -> list[Feature]:
        return [f for f in self._features if f.type == type]

    def all(self) -> list[Feature]:
        return list(self._features)

    def types(self) -> list[str]:
        return sorted({f.type for f in self._features})
