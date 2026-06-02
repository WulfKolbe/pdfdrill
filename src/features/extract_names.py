"""extract_names — PERSON_NAME features via `probablepeople` (graceful if absent).

probablepeople tags a single name-ish string (primarily English). It is not a
free-text finder, so we run it per line/segment and emit a feature only when it
classifies the segment as a Person. Modest confidence — study/extend later.
"""
from __future__ import annotations

import re

from .features import Feature

# Candidate name segments: short-ish lines / comma-or-semicolon-separated chunks
# that look like a name (have at least two capitalized tokens).
_NAMEISH = re.compile(r"\b([A-Z][\w.'-]+(?:\s+[A-Z][\w.'-]+){1,3})")


def _pp():
    try:
        import probablepeople
        return probablepeople
    except Exception:
        return None


def available() -> bool:
    return _pp() is not None


def extract(text: str, page_id: str = "") -> list[Feature]:
    pp = _pp()
    if not pp or not (text or "").strip():
        return []
    out: list[Feature] = []
    seen: set[tuple] = set()
    for m in _NAMEISH.finditer(text):
        cand = m.group(1).strip()
        try:
            _parsed, kind = pp.tag(cand)
        except Exception:
            continue
        if kind != "Person":
            continue
        span = (m.start(1), m.end(1))
        if (cand, span) in seen:
            continue
        seen.add((cand, span))
        out.append(Feature.create(page_id, "PERSON_NAME", cand, 0.6, *span))
    return out
