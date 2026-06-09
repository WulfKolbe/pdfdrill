"""
LAYER 2 — content identity.  (Gap 2: formulas/images/tables don't dedup.)

Your IdentityResolver merges on strong keys (iban/email) and soft keys
(name/title). A FORMULA has none, so re-OCR mints a duplicate. This layer adds
ONE strong key — "content_hash" — computed from a canonicalised form, and routes
keyless scientific objects through your existing resolver unchanged. Strong keys
for commercial entities, content hash for scientific ones; both coexist.

Composable: it only `.add()`s "content_hash" to the resolver's STRONG_KEYS set
at import time (idempotent) — no edit to identity.py. Canonicalisation lives
here (domain logic), NOT in the resolver's `_norm`.

    resolve_formula(resolver, latex, source, ...)  -> Entity  (dedups by content)
    content_hash(latex) / canonicalize_latex(latex)
"""
from __future__ import annotations

import hashlib
import re

# In-repo this is `from semantic import identity, entity, evidence`.
from .. import identity
from ..entity import EntityType
from ..evidence import Evidence

identity.STRONG_KEYS.add("content_hash")   # idempotent; makes the resolver merge on it

_SPACING = re.compile(r"\\[,!:;> ]|\\quad|\\qquad|\\!|\\,")
_WS = re.compile(r"\s+")


def canonicalize_latex(latex: str) -> str:
    """Collapse renderings that differ only cosmetically so re-OCR of the same
    equation hashes identically. Conservative: spacing macros + whitespace +
    \\left/\\right delimiters. Extend per corpus."""
    s = latex.strip()
    s = s.replace(r"\left", "").replace(r"\right", "")
    s = _SPACING.sub(" ", s)
    s = _WS.sub(" ", s).strip()
    return s


def content_hash(latex: str) -> str:
    return hashlib.blake2b(canonicalize_latex(latex).encode("utf-8"),
                           digest_size=16).hexdigest()


def resolve_formula(resolver, latex: str, source: str,
                    produced_by: str = "mathpix", confidence: float = 1.0,
                    entity_type: EntityType = EntityType.FORMULA, **grounding):
    h = content_hash(latex)
    ev = [
        Evidence(source, "latex", latex, produced_by, confidence=confidence,
                 grounding=grounding or None),
        Evidence(source, "content_hash", h, produced_by, confidence=1.0,
                 grounding=grounding or None),
    ]
    return resolver.resolve(entity_type, keys=[("content_hash", h)], evidence=ev)
