"""
Shared caption parsing for image-bearing lines (figures, diagrams, pictures).

MathPix encodes an image two equivalent ways in a line's text fields:

  - LaTeX form:     `\\begin{figure} \\includegraphics{<cdn>} \\caption{<text>} \\end{figure}`
  - Markdown form:  `![](<cdn>)`

The caption (when present) lives inside `\\caption{...}` of the LaTeX form, and
its braces can be unbalanced by a naive regex because captions routinely embed
inline math (`\\(2^{\\text{nd}}\\)`, `\\(\\mathrm{R}_{6}\\)`). So we extract it
with a balanced-brace walk, then parse the leading `Kind N: body` label.

Mirrors the TS `PictureProcessor` (`FIG_RE` caption group + the
`/^\\s*(Abbildung|Figure)\\s+([0-9.]+)\\s*:\\s*(.*)$/i` parser), widened to the
kinds real documents use (Picture / Sketch / Table / Diagram …) and a refnum
that allows a trailing letter (`5b`) and dotted numbers (`1.2`).
"""
from __future__ import annotations

import re
from typing import Optional

# `\caption`, optional `*`, optional `[short]`, then the `{` whose matching
# `}` we walk to (so nested braces from inline math don't end it early).
_CAPTION_START = re.compile(r"\\caption\*?\s*(?:\[[^\]]*\])?\s*\{")

# `Picture 5b: ...`, `Sketch 2: ...`, `Table 1: ...`, `Figure 1.2: ...`,
# `Abbildung 3: ...`. Kind set widened well beyond the TS Figure|Abbildung.
_LABEL = re.compile(
    r"^\s*(Abbildung|Abb\.?|Figure|Fig\.?|Picture|Sketch|Diagram|Diagramm"
    r"|Table|Tabelle|Image|Photo|Chart)\s*"
    r"([0-9]+(?:\.[0-9]+)*[A-Za-z]?)\s*[:.]\s*(.*)$",
    re.I | re.S,
)


def extract_figure_caption(text: str) -> str:
    """Return the balanced-brace body of the first `\\caption{...}`, or ''."""
    if not text:
        return ""
    m = _CAPTION_START.search(text)
    if not m:
        return ""
    start = m.end()
    depth = 1
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start:i].strip()
    return ""  # unbalanced — give up rather than capture past the figure


def parse_caption(caption: str) -> tuple[Optional[str], Optional[str], str]:
    """Parse 'Picture 5b: body' → (kind, refnum, body).

    Returns (None, None, caption.strip()) when there is no recognizable label.
    """
    if not caption:
        return None, None, ""
    m = _LABEL.match(caption)
    if not m:
        return None, None, caption.strip()
    kind = m.group(1).strip().rstrip(".").capitalize()
    return kind, m.group(2), m.group(3).strip()
