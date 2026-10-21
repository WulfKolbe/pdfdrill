# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Characters the warm-up could not read.

pdftotext writes U+FFFD for a glyph whose font maps it to no character:
the pieces of cmex10's large delimiters, Knuth's manfnt (the dangerous
bend, the METAFONT logo), cmr10's dotless j. The glyph's name still says
what it is. Where a line holds as many such glyphs as U+FFFD characters,
they are put in, in order: as LaTeX inside a formula, as the character
outside. A line of nothing but U+FFFD takes the characters of all the
glyphs it holds, top to bottom (the pieces of a large brace); if it holds
none, another line holds them, and it goes.
"""
from __future__ import annotations

import re

from .. import assign, mathpix, mathtex
from ..glyphs import Glyphs

UNREAD = True           # switch
_MISSING = "�"
_MATH = re.compile(r"\\\(.*?\\\)|\\\[.*?\\\]", re.S)


def _unread(text: str) -> bool:
    return (text == _MISSING or text.startswith("(cid:")
            or any(0xE000 <= ord(c) <= 0xF8FF for c in text))


def _fill(text: str, chars: list[str], latex: list[str]) -> str:
    """`text` with its U+FFFD characters replaced in order, inside a
    formula by `latex[k]`, outside by `chars[k]`."""
    inside = [False] * len(text)
    for m in _MATH.finditer(text):
        for k in range(m.start(), m.end()):
            inside[k] = True
    out, k = [], 0
    for pos, c in enumerate(text):
        if c == _MISSING:
            out.append((latex[k] if inside[pos] else chars[k]) or _MISSING)
            k += 1
        else:
            out.append(c)
    return "".join(out)


def process(page: dict, record, own: list[int]):
    from . import unpack
    g, _ = unpack(record)
    lines = page["lines"]
    if not UNREAD or not any(_MISSING in ln["text"] for ln in lines):
        return []
    # the earlier modules joined and removed lines: own them anew
    own = assign.by_text(lines, g, assign.owners(lines, g))
    held: dict[int, list[int]] = {}
    for i in range(g.n):
        if own[i] >= 0 and _unread(g.text[i]):
            held.setdefault(own[i], []).append(i)
    patches = []
    for li, ln in enumerate(lines):
        n = ln["text"].count(_MISSING)
        if not n or "children_ids" in ln:
            continue
        ids = sorted(held.get(li, []), key=lambda i: (g.x0[i], g.y0[i]))
        if not ids:
            if not ln["text"].replace(_MISSING, "").strip():
                patches.append((ln["id"], None))
            continue
        chars = [mathtex.char_of(g.fonts[g.font[i]], g.name[i]) for i in ids]
        if not ln["text"].replace(_MISSING, "").strip():
            if not all(chars):
                continue
            # nothing but pieces, as of a large brace beside a list: the
            # pieces from top to bottom
            text = "".join(c for _, c in sorted(
                zip(ids, chars), key=lambda ic: (g.y0[ic[0]], g.x0[ic[0]])))
        elif len(ids) == n:
            text = _fill(ln["text"], chars, [_latex(g, i) for i in ids])
            if _MISSING in text:
                continue
        else:
            continue
        display = ln["text_display"]
        lead = display[:len(display) - len(display.lstrip(" \n"))]
        patches.append((ln["id"], {"text": text, "text_display": lead + text}))
    return patches


def _latex(g: Glyphs, i: int) -> str:
    got = mathtex.token(mathtex.font_class(g.fonts[g.font[i]]), g.name[i],
                        g.text[i])
    if got == mathtex.UNKNOWN:
        got = mathtex.char_of(g.fonts[g.font[i]], g.name[i])
    return got
