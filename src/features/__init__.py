"""
`features` — an ADDITIVE, source-agnostic feature-extraction layer for pdfdrill.

Extractors take plain text (str) and emit flat `Feature` objects; relations are
flat `Relation` edges; `graph_builder.build_graph` turns relations into a
NetworkX graph. Nothing here reads PDF/PNG/MathPix/Markdown specifics or touches
the pdfdrill / docmodel / docops pipeline — it only reads text and adds features.

    from features import Feature, Relation, FeatureRegistry, build_graph, extract_all

Library-backed extractors (dates/phone/price/names/address) degrade gracefully
when their optional dependency is absent — install the extra:
    pip install 'pdfdrill[features]'
"""
from __future__ import annotations

from .features import Feature
from .relations import Relation
from .feature_registry import FeatureRegistry
from .graph_builder import build_graph

from . import (extract_email, extract_url, extract_doi, extract_dates,
               extract_phone, extract_price, extract_names, extract_address)

# Ordered registry of (name, module) — each module exposes extract(text, page_id).
EXTRACTORS = [
    ("email", extract_email),
    ("url", extract_url),
    ("doi", extract_doi),
    ("dates", extract_dates),
    ("phone", extract_phone),
    ("price", extract_price),
    ("names", extract_names),
    ("address", extract_address),
]

# The no-dependency extractors (always available).
_ALWAYS = {"email", "url", "doi"}


def extract_all(text: str, page_id: str = "", only: list[str] | None = None) -> list[Feature]:
    """Run every available extractor over `text`; return all Features (flat).

    Library-backed extractors that lack their dependency contribute nothing
    (they return []), so this is always safe to call. `only` restricts to a
    subset of extractor names.
    """
    out: list[Feature] = []
    for name, mod in EXTRACTORS:
        if only is not None and name not in only:
            continue
        out.extend(mod.extract(text, page_id))
    return out


def available_extractors() -> dict[str, bool]:
    """Map extractor name → whether it can run (no-dep ones are always True)."""
    status: dict[str, bool] = {}
    for name, mod in EXTRACTORS:
        status[name] = name in _ALWAYS or getattr(mod, "available", lambda: True)()
    return status


__all__ = ["Feature", "Relation", "FeatureRegistry", "build_graph",
           "extract_all", "available_extractors", "EXTRACTORS"]
