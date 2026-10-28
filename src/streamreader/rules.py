# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""What a thin horizontal rule belongs to: the glyphs right above and below.

A fraction bar has glyphs on both sides, an overline only below it, an
underline only above. Long rules (tables, footnotes) are left alone here.
"""
from __future__ import annotations

from .bboxlayout import PX_PER_PT
from .glyphs import Glyphs, Rules

REACH = 1.6         # x the glyph's size: how far a baseline may be off
SHORT = 20.0        # x the neighbours' size: a longer rule is not a bar
EDGE = 1.0          # page pixels of slack at the rule's ends


def neighbours(g: Glyphs, r: Rules, i: int) -> tuple[list[int], list[int]]:
    """(above, below): glyphs whose centre lies within the rule's width and
    whose baseline is within REACH of it, upward and downward."""
    x0, x1, y = r.x0[i] - EDGE, r.x1[i] + EDGE, r.y[i]
    above, below = [], []
    for k in range(g.n):
        if not g.text[k].strip():
            continue
        centre = (g.x0[k] + g.x1[k]) / 2
        if not x0 <= centre <= x1:
            continue
        reach = REACH * g.size[k] * PX_PER_PT
        if g.base[k] <= y and y - g.base[k] <= reach:
            above.append(k)
        elif g.base[k] > y and g.base[k] - y <= reach:
            below.append(k)
    return above, below


def role(g: Glyphs, r: Rules, i: int) -> str:
    """'fraction', 'over', 'under', or 'free' for a rule with no glyphs of
    its own or one too long to be a bar."""
    above, below = neighbours(g, r, i)
    if not above and not below:
        return "free"
    size = max(g.size[k] for k in above + below) * PX_PER_PT
    if r.x1[i] - r.x0[i] > SHORT * size:
        return "free"
    if above and below:
        return "fraction"
    return "under" if above else "over"
