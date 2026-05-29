"""Markdown projector — renders DocumentContext to Markdown with transclusions.

Follows Mathpix conventions:
- Headings from font size / bold detection get # markers
- Math zones become $latex$ or $$latex$$
- Bold → **text**, Italic → *text*
- Citations → {{cite:...}}, References → {{ref:...}}
- Equation numbers after display math are suppressed
- Ligatures expanded, hyphens resolved
"""

from __future__ import annotations

import re

from ..context import (
    CITATION, EMPHASIS_BOLD, EMPHASIS_ITALIC, EQUATION_NUMBER,
    EQUATION_REF, HEADING, MATH_DISPLAY, MATH_INLINE, PARAGRAPH,
    STRUCTURAL_REF, DocumentContext, Span,
)
from .base import Projector

_LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}


class MarkdownProjector(Projector):
    name = "markdown"

    def project(self, ctx: DocumentContext) -> str:
        text = ctx.graphemes

        # Build annotation list: (start, end, type, content, priority)
        annotations: list[tuple[int, int, str, str, int]] = []

        # Pre-scan display equation ends
        display_ends: set[int] = set()
        for s in ctx.L4:
            if s.kind == MATH_DISPLAY:
                display_ends.add(s.end)

        # L4: math, emphasis
        for s in ctx.L4:
            if s.kind == MATH_INLINE:
                latex = (s.props or {}).get("latex", "") or text[s.start:s.end]
                annotations.append((s.start, s.end, "math_inline", latex, 1))
            elif s.kind == MATH_DISPLAY:
                latex = (s.props or {}).get("latex", "") or text[s.start:s.end]
                annotations.append((s.start, s.end, "math_display", latex, 1))
            elif s.kind == EMPHASIS_BOLD:
                annotations.append((s.start, s.end, "bold", text[s.start:s.end], 2))
            elif s.kind == EMPHASIS_ITALIC:
                annotations.append((s.start, s.end, "italic", text[s.start:s.end], 2))

        # L2: headings
        for s in ctx.L2:
            if s.kind == HEADING:
                annotations.append((s.start, s.end, "heading", text[s.start:s.end], 0))

        # L3: references as transclusions
        for s in ctx.L3:
            p = s.props or {}
            detail = p.get("detail", text[s.start:s.end])
            if s.kind == CITATION:
                annotations.append((s.start, s.end, "citation", detail, 3))
            elif s.kind == EQUATION_NUMBER:
                near_display = any(abs(s.start - de) < 10 for de in display_ends)
                if near_display:
                    annotations.append((s.start, s.end, "eq_num_suppress", detail, 1))
                else:
                    annotations.append((s.start, s.end, "eq_num", detail, 3))
            elif s.kind == EQUATION_REF:
                annotations.append((s.start, s.end, "eq_ref", detail, 3))
            elif s.kind == STRUCTURAL_REF:
                annotations.append((s.start, s.end, "struct_ref", detail, 3))

        # Sort and resolve overlaps
        annotations.sort(key=lambda a: (a[0], a[4], -(a[1] - a[0])))
        covered: set[int] = set()
        active: list[tuple[int, int, str, str]] = []
        for start, end, atype, content, _ in annotations:
            if start in covered:
                continue
            active.append((start, end, atype, content))
            for j in range(start, end):
                covered.add(j)

        ann_at: dict[int, tuple[int, int, str, str]] = {}
        for a in active:
            ann_at[a[0]] = a

        # Paragraph ends and hyphen skips
        para_ends: set[int] = set()
        for s in ctx.L2:
            para_ends.add(s.end)

        hyphen_skip: set[int] = set()
        for s in ctx.L3:
            if s.kind == "hyphen" and (s.props or {}).get("resolution") == "soft_removed":
                hyphen_skip.add(s.start)

        # Walk and render
        output: list[str] = []
        i = 0
        while i < len(text):
            if i in hyphen_skip:
                i += 1
                if i < len(text) and text[i] == "\n":
                    i += 1
                continue

            if i in ann_at:
                start, end, atype, content = ann_at[i]

                if atype == "math_inline":
                    output.append(f"${content}$")
                elif atype == "math_display":
                    output.append(f"\n\n$${content}$$\n\n")
                elif atype == "heading":
                    level = _guess_heading_level(content, ctx)
                    output.append(f"\n\n{'#' * level} {_clean(content)}\n\n")
                elif atype == "bold":
                    output.append(f"**{_clean(content)}**")
                elif atype == "italic":
                    output.append(f"*{_clean(content)}*")
                elif atype == "citation":
                    output.append(f"{{{{cite:{content}}}}}")
                elif atype == "eq_num_suppress":
                    pass
                elif atype == "eq_num":
                    output.append(f"{{{{eq:{content}}}}}")
                elif atype == "eq_ref":
                    output.append(f"{{{{eqref:{content}}}}}")
                elif atype == "struct_ref":
                    output.append(f"{{{{ref:{content}}}}}")

                i = end
                if i < len(text) and text[i] == " " and i + 1 < len(text) and text[i + 1] in ".,;:!?)]}":
                    i += 1
                continue

            ch = text[i]
            if ch == "\f":
                i += 1
                continue
            if ch == "\n":
                if i in para_ends or (i > 0 and i - 1 in para_ends):
                    output.append("\n\n")
                    i += 1
                    while i < len(text) and text[i] in "\n\f ":
                        i += 1
                    continue
                else:
                    output.append(" ")
                    i += 1
                    continue

            output.append(_LIGATURES.get(ch, ch))
            i += 1

        result = "".join(output)
        result = re.sub(r"\n{3,}", "\n\n", result)
        result = re.sub(r"  +", " ", result)
        return result.strip() + "\n"


def _clean(s: str) -> str:
    for lig, exp in _LIGATURES.items():
        s = s.replace(lig, exp)
    s = s.replace("\n", " ").replace("\f", "")
    return re.sub(r"  +", " ", s).strip()


def _guess_heading_level(content: str, ctx: DocumentContext) -> int:
    clean = content.strip()
    for s in ctx.L2:
        if s.kind == HEADING:
            para_text = ctx.graphemes[s.start:s.end].strip()
            if para_text == clean:
                fs = (s.props or {}).get("font_size", 0)
                if fs > 14:
                    return 1
                if fs > 12:
                    return 2
                break
    if re.match(r"^\d+\s", clean):
        return 2
    if re.match(r"^\d+\.\d+", clean):
        return 3
    if clean.lower() in ("abstract", "introduction", "conclusion", "references"):
        return 4
    return 2
