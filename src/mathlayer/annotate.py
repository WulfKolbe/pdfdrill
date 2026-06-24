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


def annotate_object(obj: Any, ops: Optional[dict] = None) -> Optional[CanonicalMath]:
    """Parse obj's LaTeX into the canonical tree and store it under
    `props["math"]`. Feeds the macro-EXPANDED `latex` (best parse rate) and
    records which field was used (`source`). Returns the record, or None for a
    non-math / latex-less object (left untouched)."""
    if getattr(obj, "type", None) not in MATH_TYPES:
        return None
    props = getattr(obj, "props", None)
    if not isinstance(props, dict):
        return None
    # prefer the macro-EXPANDED latex; fall back to the macro source only if the
    # expanded field is absent (it parses far worse, but better than nothing).
    source = "latex"
    latex = props.get("latex")
    if not (latex and str(latex).strip()):
        latex = props.get("latex_original")
        source = "latex_original"
    if not (latex and str(latex).strip()):
        return None
    cm = from_latex(str(latex), ops=ops)
    d = cm.to_dict()
    d["source"] = source
    props["math"] = d
    return cm


def annotate_document(doc: Any, ops: Optional[dict] = None) -> dict[str, int]:
    """Annotate every FO/EQ in a document-like (iterable of objects via
    `.objects`). Returns counts {seen, parsed, relations, unparsed}."""
    counts = {"seen": 0, "parsed": 0, "relations": 0, "unparsed": 0}
    objects = getattr(doc, "objects", None)
    if objects is None:
        return counts
    if isinstance(objects, dict):      # Document.objects is a dict; iterate values
        objects = objects.values()
    for obj in objects:
        cm = annotate_object(obj, ops=ops)
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
