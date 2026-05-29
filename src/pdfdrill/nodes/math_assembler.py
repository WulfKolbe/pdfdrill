"""Node: Assemble char-level math zones into LaTeX expressions.

Takes math_inline/math_display spans from the math_detector and:
1. Walks CharMeta for each zone to get font info
2. Maps chars to LaTeX via latex_map
3. Detects subscripts/superscripts from size + baseline shifts
4. Produces a 'latex' field in props on each math span
"""

from __future__ import annotations

from dataclasses import dataclass

from ..context import (
    CharMeta,
    DocumentContext,
    Span,
    MATH_INLINE,
    MATH_DISPLAY,
)
from ..engine import Node
from ..latex_map import FONT_CHAR_TO_LATEX, UNICODE_TO_LATEX, char_to_latex


@dataclass
class MathExpression:
    start: int
    end: int
    expr_type: str  # "inline" or "display"
    raw_text: str
    latex: str
    confidence: float


class MathAssemblerNode(Node):
    name = "math_assembler"

    def should_run(self, ctx: DocumentContext) -> bool:
        return any(s.kind in (MATH_INLINE, MATH_DISPLAY) for s in ctx.L4)

    def run(self, ctx: DocumentContext) -> DocumentContext:
        text = ctx.graphemes
        char_meta = ctx.char_meta
        has_meta = char_meta is not None and len(char_meta) == len(text)

        new_L4: list[Span] = []

        for s in ctx.L4:
            if s.kind not in (MATH_INLINE, MATH_DISPLAY):
                new_L4.append(s)
                continue

            raw = text[s.start:s.end]

            if has_meta:
                latex = _assemble_latex(text, char_meta, s.start, s.end)
            else:
                latex = _simple_latex(raw)

            # Preserve existing props and add latex + original
            props = dict(s.props) if s.props else {}
            props["latex"] = latex
            props["original"] = raw

            new_L4.append(Span(
                start=s.start,
                end=s.end,
                kind=s.kind,
                props=props,
            ))

        ctx.L4 = new_L4
        return ctx


def _assemble_latex(
    text: str,
    char_meta: list[CharMeta],
    start: int,
    end: int,
) -> str:
    """Assemble LaTeX from char-level metadata within a math zone."""
    parts: list[str] = []

    # Determine "normal" size = the LARGEST size in the span (body text, not sub/superscripts)
    sizes = [char_meta[i].size for i in range(start, end) if char_meta[i].size > 0]
    if not sizes:
        return _simple_latex(text[start:end])
    normal_size = max(sizes)

    # Determine normal baseline from chars at normal size
    baselines = [char_meta[i].baseline for i in range(start, end)
                 if char_meta[i].baseline > 0 and abs(char_meta[i].size - normal_size) < 1.0]
    if not baselines:
        normal_baseline = 0
    else:
        baselines.sort()
        normal_baseline = baselines[len(baselines) // 2]

    in_sub = False
    in_sup = False
    i = start

    while i < end:
        ch = text[i]
        cm = char_meta[i]

        # Skip whitespace/newlines (but emit space if between math tokens)
        if ch in "\n\f":
            i += 1
            continue
        if ch == " ":
            if parts and not parts[-1].endswith(" "):
                parts.append(" ")
            i += 1
            continue

        # Detect sub/superscript from size and baseline
        is_small = cm.size > 0 and cm.size < normal_size * 0.85
        baseline_shift = cm.baseline - normal_baseline if normal_baseline > 0 and cm.baseline > 0 else 0

        if is_small and baseline_shift < -1.5 and not in_sup:
            # Superscript (baseline moves up = smaller y value in PDF coords)
            if in_sub:
                parts.append("}")
                in_sub = False
            parts.append("^{")
            in_sup = True
        elif is_small and baseline_shift > 1.5 and not in_sub:
            # Subscript (baseline moves down)
            if in_sup:
                parts.append("}")
                in_sup = False
            parts.append("_{")
            in_sub = True
        elif not is_small:
            if in_sub:
                parts.append("}")
                in_sub = False
            if in_sup:
                parts.append("}")
                in_sup = False

        # Check for multi-char operator names (log, sin, cos, etc.)
        op_match = _match_operator_name(text, i, end)
        if op_match:
            op_name, op_len = op_match
            parts.append(f"\\{op_name}")
            i += op_len
            continue

        # Map character to LaTeX
        if ch == '#':
            latex_ch = r'\#'
        else:
            latex_ch = char_to_latex(ch, cm.font_name)
        parts.append(latex_ch)
        i += 1

    # Close any open sub/sup
    if in_sub or in_sup:
        parts.append("}")

    result = "".join(parts)
    return _clean_latex(result)


_OPERATOR_NAMES = {
    "log": "log", "sin": "sin", "cos": "cos", "tan": "tan",
    "exp": "exp", "lim": "lim", "sup": "sup", "inf": "inf",
    "max": "max", "min": "min", "det": "det", "dim": "dim",
    "ker": "ker", "mod": "mod", "gcd": "gcd", "deg": "deg",
    "arg": "arg", "hom": "hom", "ord": "ord",
    "Gal": "Gal", "Aut": "Aut", "End": "End", "Hom": "Hom",
    "rank": "rank", "disc": "disc", "sgn": "sgn", "vol": "vol",
    "arcsin": "arcsin", "arccos": "arccos", "arctan": "arctan",
}


def _match_operator_name(text: str, pos: int, end: int) -> tuple[str, int] | None:
    """Check if text at pos starts with a known math operator name."""
    for name in sorted(_OPERATOR_NAMES, key=len, reverse=True):
        if pos + len(name) <= end and text[pos:pos + len(name)] == name:
            after = pos + len(name)
            if after >= end or not text[after].isalpha():
                return (_OPERATOR_NAMES[name], len(name))
    return None


def _simple_latex(raw: str) -> str:
    """Simple character-by-character LaTeX conversion without metadata."""
    parts = []
    for ch in raw:
        if ch == '#':
            parts.append(r'\#')
        elif ch in UNICODE_TO_LATEX:
            parts.append(UNICODE_TO_LATEX[ch])
        elif ch == "\n":
            parts.append(" ")
        elif ch == "\f":
            continue
        else:
            parts.append(ch)
    return _clean_latex("".join(parts))


def _clean_latex(s: str) -> str:
    """Clean up assembled LaTeX string."""
    import re
    # Collapse multiple spaces
    s = re.sub(r"  +", " ", s)
    # Remove spaces around operators where LaTeX handles spacing
    s = s.strip()
    # Remove empty groups
    s = s.replace("^{}", "").replace("_{}", "")
    return s
