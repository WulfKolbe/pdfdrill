"""Node: Detect font emphasis (bold, italic) and map to LaTeX commands.

Scans CharMeta for runs of bold or italic text fonts (NOT math italic),
creates L4 spans with LaTeX command mappings.
"""

from __future__ import annotations

from ..context import (
    CharMeta,
    DocumentContext,
    HEADING,
    Span,
    EMPHASIS_BOLD,
    EMPHASIS_ITALIC,
)
from ..engine import Node


class EmphasisDetectorNode(Node):
    name = "emphasis_detector"

    def should_run(self, ctx: DocumentContext) -> bool:
        return bool(ctx.graphemes)

    def run(self, ctx: DocumentContext) -> DocumentContext:
        char_meta = ctx.char_meta
        if not char_meta:
            return ctx

        text = ctx.graphemes
        if len(char_meta) != len(text):
            return ctx

        bold_spans = _detect_bold_runs(text, char_meta)
        italic_spans = _detect_italic_runs(text, char_meta)

        for s in bold_spans:
            if (s.props or {}).get("interpretation") == "heading":
                ctx.L2.append(Span(
                    start=s.start, end=s.end,
                    kind=HEADING,
                    props={"font_size": 10.0},
                ))
            else:
                ctx.L4.append(s)
        ctx.L4.extend(italic_spans)
        return ctx


def _detect_bold_runs(
    text: str,
    char_meta: list[CharMeta],
) -> list[Span]:
    """Find runs of bold text and classify them."""
    runs = _find_font_class_runs(text, char_meta, "bold")
    results = []

    for start, end in runs:
        span_text = text[start:end].strip()
        if not span_text or len(span_text) < 2:
            continue

        # Classify: heading-like bold (starts line, capitalized) vs inline emphasis
        if _is_line_start(start, text) and len(span_text) < 80:
            interpretation = "heading"
        else:
            interpretation = "strong"

        results.append(Span(
            start=start, end=end,
            kind=EMPHASIS_BOLD,
            props={"interpretation": interpretation},
        ))

    return results


def _detect_italic_runs(
    text: str,
    char_meta: list[CharMeta],
) -> list[Span]:
    """Find runs of italic text (NOT math italic) and classify them."""
    runs = _find_font_class_runs(text, char_meta, "italic")
    results = []

    for start, end in runs:
        span_text = text[start:end].strip()
        if not span_text or len(span_text) < 2:
            continue

        results.append(Span(
            start=start, end=end,
            kind=EMPHASIS_ITALIC,
            props={"interpretation": "emphasis"},
        ))

    return results


def _find_font_class_runs(
    text: str,
    char_meta: list[CharMeta],
    target_class: str,
) -> list[tuple[int, int]]:
    """Find contiguous runs of a given font_class in text (non-whitespace chars)."""
    runs = []
    in_run = False
    run_start = 0

    for i in range(len(text)):
        cm = char_meta[i]
        is_target = cm.font_class == target_class and not text[i].isspace() and text[i] not in "\n\f"

        if is_target and not in_run:
            in_run = True
            run_start = i
        elif not is_target and in_run:
            # Allow small gaps (1-2 spaces between bold words)
            gap = 0
            j = i
            while j < len(text) and j < i + 3 and text[j] == " ":
                j += 1
                gap += 1
            if j < len(text) and j < len(char_meta) and char_meta[j].font_class == target_class:
                continue  # bridge the gap
            in_run = False
            if i - run_start >= 2:
                runs.append((run_start, i))

    if in_run and len(text) - run_start >= 2:
        runs.append((run_start, len(text)))

    return runs


def _is_line_start(pos: int, text: str) -> bool:
    """Check if position is at the start of a line."""
    if pos == 0:
        return True
    for i in range(pos - 1, max(0, pos - 3), -1):
        if text[i] == "\n" or text[i] == "\f":
            return True
        if not text[i].isspace():
            return False
    return False
