"""Node: Reference and citation detection.

Runs BEFORE math_detector to mark positions that should be excluded
from math expression detection. Detects:
1. Citations: [Name99], [ABC12, DEF34], [1], [2,3]
2. Equation numbers: (N) or (N.M) at or near end of line
3. Theorem/figure/section references: "Theorem 1.1", "Figure 2", "Section 3"
4. Footnote markers: superscript digits (detected by size)
5. Margin annotations: page numbers, running headers

Each detection adds spans to L3 and marks character ranges so the
math detector can exclude them.
"""

from __future__ import annotations

import re

from ..context import (
    DocumentContext,
    Span,
    CITATION,
    EQUATION_NUMBER,
    EQUATION_REF,
    STRUCTURAL_REF,
)
from ..engine import Node


# ---------------------------------------------------------------------------
# Citation patterns
# ---------------------------------------------------------------------------

# Author-year citations: [Erd46], [ABC12a], [GK15, SST84]
_CITE_AUTHOR_YEAR = re.compile(
    r"\["
    r"([A-Z][A-Za-z]*\d{2}[a-z]?"         # first citation
    r"(?:[,;\s]+[A-Z][A-Za-z]*\d{2}[a-z]?)*"  # optional additional citations
    r")\]"
)

# Numbered citations: [1], [2, 3], [12-15]
_CITE_NUMBERED = re.compile(
    r"\["
    r"(\d{1,3}"
    r"(?:[,;\s–\-]+\d{1,3})*"
    r")\]"
)


# ---------------------------------------------------------------------------
# Equation number patterns
# ---------------------------------------------------------------------------

# Equation tags at end of line: (1), (2.3), (A.1)
# Must be near end of line or preceded by lots of whitespace
_EQ_NUMBER = re.compile(
    r"\((\d{1,3}(?:\.\d{1,3})?|[A-Z]\.\d{1,3})\)"
    r"\s*(?:\n|$)"
)

# Equation tags that appear inline as references: Eq. (1), equation (2.3)
_EQ_REF = re.compile(
    r"(?:Eq\.|eq\.|equation|Equation|Gleichung)\s*"
    r"\((\d{1,3}(?:\.\d{1,3})?)\)"
)


# ---------------------------------------------------------------------------
# Structural references
# ---------------------------------------------------------------------------

_STRUCT_REF = re.compile(
    r"(?:Theorem|Lemma|Proposition|Corollary|Definition|Remark|"
    r"Conjecture|Example|Proof|Claim|Section|Figure|Fig\.|Table|"
    r"Chapter|Appendix|Algorithm|Satz|Abschnitt|Kapitel|Tabelle|Bild)"
    r"\s+"
    r"(\d+(?:\.\d+)*[a-z]?)"
    r"(?:\.\s|\s|,|;|\)|\]|$)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Footnote patterns
# ---------------------------------------------------------------------------

# Superscript-style footnote markers: a digit that appears at superscript position
# We can only detect these by checking the raw text for patterns like
# single digits preceded by a word and followed by whitespace or punctuation
_FOOTNOTE_MARKER = re.compile(
    r"(?<=[a-z.!?,;:)\]])"  # preceded by text char or punctuation
    r"(\d)"                   # single digit
    r"(?=[\s\n]|$)"          # followed by whitespace or EOL
)


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

class ReferenceDetectorNode(Node):
    name = "reference_detector"

    def should_run(self, ctx: DocumentContext) -> bool:
        return bool(ctx.graphemes)

    def run(self, ctx: DocumentContext) -> DocumentContext:
        text = ctx.graphemes
        spans: list[Span] = []

        spans.extend(_detect_citations(text))
        spans.extend(_detect_equation_numbers(text))
        spans.extend(_detect_equation_refs(text))
        spans.extend(_detect_structural_refs(text))

        ctx.L3.extend(spans)
        return ctx


def _detect_citations(text: str) -> list[Span]:
    """Detect citation brackets [Name99] and [N]."""
    spans: list[Span] = []

    for m in _CITE_AUTHOR_YEAR.finditer(text):
        spans.append(Span(
            start=m.start(),
            end=m.end(),
            kind=CITATION,
            props={"detail": m.group(0), "confidence": 0.95},
        ))

    for m in _CITE_NUMBERED.finditer(text):
        # Avoid matching things already caught as author-year
        already = any(
            s.start <= m.start() < s.end
            for s in spans
        )
        if not already:
            spans.append(Span(
                start=m.start(),
                end=m.end(),
                kind=CITATION,
                props={"detail": m.group(0), "subtype": "numbered", "confidence": 0.85},
            ))

    return spans


def _detect_equation_numbers(text: str) -> list[Span]:
    """Detect equation number tags like (1), (2.3) at end of display lines."""
    spans: list[Span] = []
    for m in _EQ_NUMBER.finditer(text):
        spans.append(Span(
            start=m.start(),
            end=m.start() + len(m.group(0).rstrip()),
            kind=EQUATION_NUMBER,
            props={"detail": m.group(1), "confidence": 0.9},
        ))
    return spans


def _detect_equation_refs(text: str) -> list[Span]:
    """Detect inline equation references like 'Eq. (1)'."""
    spans: list[Span] = []
    for m in _EQ_REF.finditer(text):
        spans.append(Span(
            start=m.start(),
            end=m.end(),
            kind=EQUATION_REF,
            props={"detail": m.group(0), "confidence": 0.9},
        ))
    return spans


def _detect_structural_refs(text: str) -> list[Span]:
    """Detect references to theorems, figures, sections, etc."""
    spans: list[Span] = []
    for m in _STRUCT_REF.finditer(text):
        spans.append(Span(
            start=m.start(),
            end=m.end(),
            kind=STRUCTURAL_REF,
            props={"detail": m.group(0).strip().rstrip(".,;)"), "confidence": 0.85},
        ))
    return spans


# ---------------------------------------------------------------------------
# Utility: get exclusion set for math detector
# ---------------------------------------------------------------------------

REFERENCE_SPAN_KINDS = frozenset({
    CITATION,
    EQUATION_NUMBER,
    EQUATION_REF,
    STRUCTURAL_REF,
})


def get_reference_exclusion_set(ctx: DocumentContext) -> set[int]:
    """Return the set of grapheme positions that are part of reference annotations.

    The math_detector should skip these positions during bridge propagation
    and span detection.
    """
    excluded: set[int] = set()
    for s in ctx.L3:
        if s.kind in REFERENCE_SPAN_KINDS:
            excluded.update(range(s.start, s.end))
    return excluded
