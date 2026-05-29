"""Node: Stub NLP -- sentence splitting via punctuation rules.

Placeholder for future integration with spaCy/Stanza.
Currently uses regex-based sentence boundary detection.
"""

from __future__ import annotations

import re

from ..context import (
    DocumentContext,
    Span,
    PARAGRAPH,
    SENTENCE,
)
from ..engine import Node

# Sentence-ending punctuation followed by space+uppercase or end of text.
# Handles: . ? ! and their Unicode variants
# Avoids splitting on abbreviations like "e.g.", "Dr.", single-letter initials "A."
_SENT_END = re.compile(
    r"(?<=[.!?…¿¡])"  # lookbehind: sentence-ending punctuation
    r"(?:"
    r'[\s“”"‘’\'\)»\]]+'  # whitespace or closing quotes/brackets
    r"(?=[A-ZÀ-ÖØ-Þ0-9(\"«\[])"  # lookahead: uppercase, digit, opening bracket
    r"|"
    r"\s*$"                 # or end of string
    r")",
    re.UNICODE,
)


class StubNlpNode(Node):
    name = "stub_nlp"

    def should_run(self, ctx: DocumentContext) -> bool:
        return any(s.kind == PARAGRAPH for s in ctx.L2)

    def run(self, ctx: DocumentContext) -> DocumentContext:
        text = ctx.graphemes
        paragraphs = [s for s in ctx.L2 if s.kind == PARAGRAPH]

        for para in paragraphs:
            para_text = text[para.start:para.end]
            boundaries = _split_sentences(para_text)

            for rel_start, rel_end in boundaries:
                abs_start = para.start + rel_start
                abs_end = para.start + rel_end
                snippet = text[abs_start:abs_end].strip()
                if not snippet:
                    continue

                stype = _classify_sentence(snippet)
                props = {"type": stype} if stype != "declarative" else None

                ctx.L4.append(Span(
                    start=abs_start,
                    end=abs_end,
                    kind=SENTENCE,
                    props=props,
                ))

        return ctx


def _split_sentences(text: str) -> list[tuple[int, int]]:
    """Return (start, end) pairs for sentences within a paragraph."""
    if not text.strip():
        return []

    boundaries: list[int] = [0]
    for m in _SENT_END.finditer(text):
        pos = m.start()
        if pos > boundaries[-1] + 2:  # avoid empty splits
            boundaries.append(pos)

    # Produce (start, end) pairs
    result = []
    for i in range(len(boundaries)):
        start = boundaries[i]
        end = boundaries[i + 1] if i + 1 < len(boundaries) else len(text)
        if text[start:end].strip():
            result.append((start, end))

    return result


def _classify_sentence(text: str) -> str:
    """Simple sentence type classification by trailing punctuation."""
    stripped = text.rstrip()
    if not stripped:
        return "declarative"
    last = stripped[-1]
    if last == "?":
        return "interrogative"
    if last == "!":
        return "exclamatory"
    if stripped.startswith("¿"):
        return "interrogative"
    if stripped.startswith("¡"):
        return "exclamatory"
    return "declarative"
