"""match_entities — fuzzy-match Features into `Relation` edges via `rapidfuzz`.

For deduping/linking invoice numbers, company names, OCR-typo variants, etc.
Emits flat `Relation(source, target, type, weight)` where weight = score/100.
Within one list: links near-duplicate pairs. Across two lists: links A→B matches.
"""
from __future__ import annotations

from itertools import combinations

from .features import Feature
from .relations import Relation


def _scorer():
    from rapidfuzz import fuzz       # required dependency for this module
    return fuzz.token_sort_ratio


def match(features_a: list[Feature], features_b: list[Feature] | None = None,
          threshold: float = 85.0, type: str = "SAME_AS") -> list[Relation]:
    """Fuzzy-match feature values into Relations (weight = score/100, ≥threshold).

    `features_b=None` → match within `features_a` (each unordered pair once).
    Otherwise → match every A against every B. Identical ids are never linked.
    """
    score = _scorer()
    out: list[Relation] = []
    if features_b is None:
        pairs = combinations(features_a, 2)
    else:
        pairs = ((a, b) for a in features_a for b in features_b)
    for a, b in pairs:
        if a.id == b.id:
            continue
        s = score(a.value or "", b.value or "")
        if s >= threshold:
            out.append(Relation(source=a.id, target=b.id, type=type,
                                 weight=round(s / 100.0, 4)))
    return out
