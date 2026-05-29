"""Node: Detect lines and paragraphs from grapheme string + char positions.

Uses newline/form-feed positions and char-level x-coordinates to detect:
- Body text left margin per page
- First-line indentation (LaTeX \\parindent style)
- Centered lines (display equations, titles)
- Paragraph breaks from blank lines, page breaks, and indentation
"""

from __future__ import annotations

from collections import Counter

from ..context import (
    CharMeta,
    DocumentContext,
    Span,
    PARAGRAPH,
    HEADING,
)
from ..engine import Node


class LinesParagraphsNode(Node):
    name = "lines_paragraphs"

    def should_run(self, ctx: DocumentContext) -> bool:
        return bool(ctx.graphemes)

    def run(self, ctx: DocumentContext) -> DocumentContext:
        text = ctx.graphemes
        char_meta = ctx.char_meta if ctx.char_meta else None

        if char_meta and len(char_meta) == len(text):
            spans = _detect_paragraphs_with_positions(text, char_meta)
        else:
            spans = _detect_paragraphs_simple(text)

        ctx.L2.extend(spans)
        return ctx


# ---------------------------------------------------------------------------
# Position-aware paragraph detection
# ---------------------------------------------------------------------------

def _detect_paragraphs_with_positions(
    text: str,
    char_meta: list[CharMeta],
) -> list[Span]:
    """Detect paragraphs using char-level x-coordinates.

    Computes body margin per page, detects first-line indentation,
    and avoids splitting at centered display lines.
    """
    # Step 1: split into lines by \n and \f positions
    lines: list[tuple[int, int, int]] = []  # (start, end, page)
    line_start = 0
    current_page = 0

    for i, ch in enumerate(text):
        if ch == "\n" or ch == "\f":
            if i > line_start:
                lines.append((line_start, i, current_page))
            if ch == "\f":
                current_page += 1
            line_start = i + 1

    if line_start < len(text):
        content = text[line_start:].strip()
        if content:
            lines.append((line_start, len(text), current_page))

    if not lines:
        return []

    # Step 2: compute body margin per page
    page_margins: dict[int, float] = {}
    page_line_x0s: dict[int, list[float]] = {}

    for ls, le, page in lines:
        line_text = text[ls:le].strip()
        if len(line_text) < 20:
            continue  # skip short lines (headings, eq numbers)
        # Find x0 of first non-whitespace char with metadata
        for idx in range(ls, le):
            if idx < len(char_meta) and not text[idx].isspace():
                cm = char_meta[idx]
                if cm.x0 > 0 and cm.font_class == "text":
                    page_line_x0s.setdefault(page, []).append(round(cm.x0, 0))
                    break

    for page, x0s in page_line_x0s.items():
        if x0s:
            counts = Counter(x0s)
            page_margins[page] = counts.most_common(1)[0][0]

    default_margin = 78.0  # fallback
    if page_margins:
        all_margins = list(page_margins.values())
        all_margins.sort()
        default_margin = all_margins[len(all_margins) // 2]

    # Step 2b: compute body text size (most common font size)
    all_text_sizes: list[float] = []
    for ls, le, page in lines:
        for idx in range(ls, le):
            if idx < len(char_meta) and not text[idx].isspace() and char_meta[idx].size > 0:
                if char_meta[idx].font_class in ("text", "bold", "italic"):
                    all_text_sizes.append(round(char_meta[idx].size, 0))
    body_size = 10.0
    if all_text_sizes:
        size_counts = Counter(all_text_sizes)
        body_size = size_counts.most_common(1)[0][0]

    # Step 3: classify each line
    LINE_TEXT = "text"
    LINE_INDENT = "indent"       # first-line indentation
    LINE_CENTERED = "centered"   # display equation or title
    LINE_HEADING = "heading"     # bold/larger font
    LINE_SHORT = "short"         # very short line (last line of paragraph)
    LINE_BLANK = "blank"

    classified: list[tuple[int, int, int, str, float]] = []  # (start, end, page, class, font_size)

    for ls, le, page in lines:
        line_text = text[ls:le]
        stripped = line_text.strip()

        if not stripped:
            classified.append((ls, le, page, LINE_BLANK, 0.0))
            continue

        # Find first non-space char's properties
        margin = page_margins.get(page, default_margin)
        first_x0 = 0.0
        first_class = "text"
        first_size = body_size
        for idx in range(ls, le):
            if idx < len(char_meta) and not text[idx].isspace():
                first_x0 = char_meta[idx].x0
                first_class = char_meta[idx].font_class
                first_size = char_meta[idx].size
                break

        # Compute dominant font size for this line
        line_sizes = [char_meta[idx].size for idx in range(ls, min(le, len(char_meta)))
                      if not text[idx].isspace() and char_meta[idx].size > 0]
        line_size = max(line_sizes) if line_sizes else body_size

        indent = first_x0 - margin if first_x0 > 0 else 0
        is_large_font = line_size > body_size * 1.15

        if is_large_font and len(stripped) < 80:
            classified.append((ls, le, page, LINE_HEADING, line_size))
        elif len(stripped) < 10 and indent > 50:
            classified.append((ls, le, page, LINE_CENTERED, line_size))
        elif first_class == "bold" and len(stripped) < 60:
            classified.append((ls, le, page, LINE_HEADING, line_size))
        elif indent > 15 and indent < 40:
            classified.append((ls, le, page, LINE_INDENT, line_size))
        elif indent > 40:
            classified.append((ls, le, page, LINE_CENTERED, line_size))
        elif len(stripped) < 30:
            classified.append((ls, le, page, LINE_SHORT, line_size))
        else:
            classified.append((ls, le, page, LINE_TEXT, line_size))

    # Step 4: group lines into paragraphs
    spans: list[Span] = []
    para_start = -1
    prev_page = -1

    for i, (ls, le, page, lclass, lsize) in enumerate(classified):
        # Page break always starts new paragraph
        if page != prev_page and para_start >= 0:
            spans.append(Span(
                start=para_start, end=classified[i-1][1],
                kind=PARAGRAPH,
            ))
            para_start = -1

        prev_page = page

        if lclass == LINE_BLANK:
            if para_start >= 0:
                spans.append(Span(
                    start=para_start, end=classified[i-1][1],
                    kind=PARAGRAPH,
                ))
                para_start = -1
            continue

        if lclass == LINE_HEADING:
            if para_start >= 0:
                spans.append(Span(
                    start=para_start, end=classified[i-1][1],
                    kind=PARAGRAPH,
                ))
            spans.append(Span(
                start=ls, end=le,
                kind=HEADING,
                props={"font_size": lsize},
            ))
            para_start = -1
            continue

        if lclass == LINE_INDENT:
            if para_start >= 0:
                spans.append(Span(
                    start=para_start, end=classified[i-1][1],
                    kind=PARAGRAPH,
                ))
            para_start = ls
            continue

        if para_start < 0:
            para_start = ls

    # Final paragraph
    if para_start >= 0 and classified:
        spans.append(Span(
            start=para_start, end=classified[-1][1],
            kind=PARAGRAPH,
        ))

    # Filter empty
    return [s for s in spans if text[s.start:s.end].strip()]


# ---------------------------------------------------------------------------
# Fallback: simple paragraph detection (no char positions)
# ---------------------------------------------------------------------------

def _detect_paragraphs_simple(text: str) -> list[Span]:
    """Split text into paragraphs using only newlines and form feeds."""
    spans: list[Span] = []
    i = 0
    para_start = 0

    while i < len(text) and text[i] in ("\n", "\f", " "):
        i += 1
    para_start = i

    while i < len(text):
        ch = text[i]
        if ch == "\f":
            if i > para_start and text[para_start:i].strip():
                spans.append(Span(start=para_start, end=i, kind=PARAGRAPH))
            i += 1
            while i < len(text) and text[i] in ("\n", "\f", " "):
                i += 1
            para_start = i
        elif ch == "\n" and i + 1 < len(text) and text[i + 1] in ("\n", "\f"):
            if i > para_start and text[para_start:i].strip():
                spans.append(Span(start=para_start, end=i, kind=PARAGRAPH))
            i += 1
            while i < len(text) and text[i] in ("\n", "\f", " "):
                i += 1
            para_start = i
        else:
            i += 1

    if para_start < len(text) and text[para_start:].strip():
        spans.append(Span(start=para_start, end=len(text), kind=PARAGRAPH))

    return spans
