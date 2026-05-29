"""Node: Heuristic OCR error flagging.

Detects common OCR errors and suspicious patterns:
- Beta/eszett confusion (beta vs eszett)
- Math symbols in running text
- Ligature artifacts
- Italic spacing (spaces between capitals)
- Special character issues
"""

from __future__ import annotations

import re

from ..context import (
    DocumentContext,
    Span,
    FLAG,
)
from ..engine import Node


class FlaggerNode(Node):
    name = "flagger"

    def should_run(self, ctx: DocumentContext) -> bool:
        return bool(ctx.graphemes)

    def run(self, ctx: DocumentContext) -> DocumentContext:
        text = ctx.graphemes
        spans: list[Span] = []

        spans.extend(_detect_beta_eszett(text))
        spans.extend(_detect_math_symbols(text))
        spans.extend(_detect_ligatures(text))
        spans.extend(_detect_italic_spacing(text))

        ctx.L4.extend(spans)
        return ctx


def _detect_beta_eszett(text: str) -> list[Span]:
    """Detect beta that might be OCR-misread eszett, especially near German words."""
    spans = []
    for m in re.finditer(r"β", text):
        pos = m.start()
        context = text[max(0, pos-10):pos+10]
        # If surrounded by Latin letters, likely an eszett error
        before = text[pos-1] if pos > 0 else ""
        after = text[pos+1] if pos+1 < len(text) else ""
        if before.isalpha() and before.isascii() and after.isalpha() and after.isascii():
            spans.append(Span(
                start=pos, end=pos+1,
                kind=FLAG,
                props={
                    "flag_type": "beta_eszett_confusion",
                    "detail": f"β in Latin context: ...{context}...",
                    "correction": "ß",
                    "original": "β",
                    "confidence": 0.8,
                },
            ))
        elif before.isalpha() or after.isalpha():
            spans.append(Span(
                start=pos, end=pos+1,
                kind=FLAG,
                props={
                    "flag_type": "possible_beta_eszett",
                    "detail": f"β near text: ...{context}...",
                    "confidence": 0.4,
                },
            ))
    return spans


_MATH_SYMBOLS = re.compile(
    r"[∑∏∫∂∇Δ"
    r"∈∉⊂⊃⊆⊇"
    r"∀∃∅∞≈≡"
    r"≤≥≪≫±×"
    r"÷√∝∠∧∨"
    r"¬⊕⊗⊥∥⟨"
    r"⟩⟪⟫←→↔"
    r"⇐⇒⇔↦↗↘"
    r"↙↖∘⋅⊙⊚]"
)


def _detect_math_symbols(text: str) -> list[Span]:
    """Flag math symbols that appear in running text (potential equation zones)."""
    spans = []
    for m in _MATH_SYMBOLS.finditer(text):
        pos = m.start()
        spans.append(Span(
            start=pos, end=pos+1,
            kind=FLAG,
            props={
                "flag_type": "math_symbol_in_text",
                "detail": f"symbol: {m.group()}",
                "confidence": 0.5,
            },
        ))
    return spans


_LIGATURES = {
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬀ": "ff",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "ft",
    "ﬆ": "st",
}


def _detect_ligatures(text: str) -> list[Span]:
    """Flag Unicode ligature characters that may cause text processing issues."""
    spans = []
    for lig, expansion in _LIGATURES.items():
        for m in re.finditer(re.escape(lig), text):
            spans.append(Span(
                start=m.start(), end=m.end(),
                kind=FLAG,
                props={
                    "flag_type": "ligature",
                    "detail": f"{lig} -> {expansion}",
                    "correction": expansion,
                    "original": lig,
                    "confidence": 0.95,
                },
            ))
    return spans


_SPACED_CAPS = re.compile(r"[A-Z]\s[A-Z]\s[A-Z](?:\s[A-Z])*")


def _detect_italic_spacing(text: str) -> list[Span]:
    """Detect spaced-out capital letters typical of OCR on italic/decorative text."""
    spans = []
    for m in _SPACED_CAPS.finditer(text):
        span = m.group()
        if len(span) >= 5:  # at least 3 spaced capitals
            spans.append(Span(
                start=m.start(), end=m.end(),
                kind=FLAG,
                props={
                    "flag_type": "italic_spacing",
                    "detail": f"spaced capitals: '{span}'",
                    "correction": span.replace(" ", ""),
                    "confidence": 0.6,
                },
            ))
    return spans
