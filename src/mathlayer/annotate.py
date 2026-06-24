"""Attach the canonical math record to FO/EQ objects.

Duck-typed over anything exposing `.type` (a DocObject / GraphNode) and a
`.props` dict carrying `latex` — so it works on both the full Document and the
fast docgraph view without importing either. The first integration point of the
canonical math layer into pdfdrill's document model.
"""
from __future__ import annotations

from typing import Any, Optional

from .canonical import CanonicalMath, from_latex

# the object types that carry a typed LaTeX expression
MATH_TYPES = {"Formula", "Equation"}


def annotate_object(obj: Any) -> Optional[CanonicalMath]:
    """Parse obj's `latex` into the canonical tree and store it under
    `props["math"]`. Returns the record, or None for a non-math / latex-less
    object (left untouched)."""
    if getattr(obj, "type", None) not in MATH_TYPES:
        return None
    props = getattr(obj, "props", None)
    if not isinstance(props, dict):
        return None
    latex = props.get("latex")
    if not latex or not str(latex).strip():
        return None
    cm = from_latex(str(latex))
    props["math"] = cm.to_dict()
    return cm


def annotate_document(doc: Any) -> dict[str, int]:
    """Annotate every FO/EQ in a document-like (iterable of objects via
    `.objects`). Returns counts {seen, parsed, relations, unparsed}."""
    counts = {"seen": 0, "parsed": 0, "relations": 0, "unparsed": 0}
    objects = getattr(doc, "objects", None)
    if objects is None:
        return counts
    for obj in objects:
        cm = annotate_object(obj)
        if cm is None:
            continue
        counts["seen"] += 1
        if cm.role == "unparsed":
            counts["unparsed"] += 1
        else:
            counts["parsed"] += 1
            if cm.role == "relation":
                counts["relations"] += 1
    return counts
