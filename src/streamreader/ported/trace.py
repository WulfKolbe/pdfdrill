# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""psred featjudge's `trace` interface, served from pdf2mmd2's glyph arrays.

The trace itself is ported into `pdf2mmd2.glyphs` (columns adv, move, cause,
op). This module only hands it out in the shape `space.py` and psred's own
tests expect: one dict per glyph, lengths in PDF points.
"""
from __future__ import annotations

import re
from pathlib import Path

from .. import glyphs
from ..bboxlayout import PX_PER_PT

tj_to_page = glyphs.tj_to_page
_CAUSE = {glyphs.CAUSE_NONE: "none", glyphs.CAUSE_TJ: "TJ",
          glyphs.CAUSE_POSITION: "position"}


# pdfTeX's cmex10 has no Unicode map, so a big operator arrives as `(cid:80)`
# or a stray letter. `space.atom_class` goes by the character; the glyph
# name knows which operator it is.
_OPERATOR = {"summation": "∑", "product": "∏", "integral": "∫",
             "contintegral": "∮", "union": "⋃", "intersection": "⋂",
             "circleplus": "⨁", "circlemultiply": "⨂"}
_SIZED = re.compile(r"^(.*?)(text|display)$")


def _text(g, i: int) -> str:
    m = _SIZED.match(g.name[i])
    return _OPERATOR.get(m.group(1), g.text[i]) if m else g.text[i]


def trace(pdf, page: int) -> list[dict]:
    """[event] in stream order for one page; see psred trace.py CONTRACT.
    y is measured downward from the top of the page here."""
    g = list(glyphs.read_pages(Path(pdf), page, page))[0].glyphs
    k = PX_PER_PT
    return [dict(kind="glyph", text=_text(g, i), font=g.fonts[g.font[i]],
                 size=g.size[i], x=g.x0[i] / k, y=g.base[i] / k,
                 adv=g.adv[i] / k, move_before=g.move[i] / k,
                 cause=_CAUSE[g.cause[i]], op_no=g.op[i])
            for i in range(g.n)]
