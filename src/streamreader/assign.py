# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Which warm-up line does each glyph belong to?"""
from __future__ import annotations

import unicodedata
from bisect import bisect_right
from collections import Counter
from difflib import SequenceMatcher

from . import mathpix
from .glyphs import Glyphs, band

SLACK = 2          # page pixels around a line region


def owners(lines: list[dict], glyphs: Glyphs) -> list[int]:
    """For every glyph the index into `lines` of the line whose region
    contains its centre (of its `band`: a cmsy10 box hangs below its line),
    or -1. Where regions overlap, the line whose
    vertical centre is nearer wins."""
    boxes = []
    for i, ln in enumerate(lines):
        r = ln["region"]
        boxes.append((r["top_left_y"] - SLACK, r["top_left_x"] - SLACK,
                      r["top_left_x"] + r["width"] + SLACK,
                      r["top_left_y"] + r["height"] + SLACK, i))
    boxes.sort()
    tops = [b[0] for b in boxes]
    tallest = max((b[3] - b[0] for b in boxes), default=0)
    out: list[int] = []
    x0, x1 = glyphs.x0, glyphs.x1
    for g in range(glyphs.n):
        top, bottom = band(glyphs, g)
        cx, cy = (x0[g] + x1[g]) / 2, (top + bottom) / 2
        best, best_d = -1, None
        j = bisect_right(tops, cy) - 1
        while j >= 0 and tops[j] >= cy - tallest:
            top, left, right, bottom, i = boxes[j]
            if cy <= bottom and left <= cx <= right:
                d = abs((top + bottom) / 2 - cy)
                if best_d is None or d < best_d:
                    best, best_d = i, d
            j -= 1
        out.append(best)
    return out


TOLD = 0.8         # of a line's characters its glyphs must tell, to trust it


def _nfkc(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace(" ", "")


def by_text(lines: list[dict], glyphs: Glyphs, own: list[int]) -> list[int]:
    """`own`, with the glyphs moved that the lines' text places elsewhere.

    Line boxes lie in each other where scripts are set, so a superscript's
    centre can fall into the line above. The warm-up text says which line
    has the character: a line whose glyphs tell its text but for a
    character at one place takes that character's glyph from a line that
    has it too many (or from no line), if it stands at that place.
    """
    x0, y0, x1, y1 = glyphs.x0, glyphs.y0, glyphs.x1, glyphs.y1
    of: dict[int, list[int]] = {}
    for k, i in enumerate(own):
        if i >= 0 and glyphs.text[k].strip():
            of.setdefault(i, []).append(k)
    spare: dict[str, list[int]] = {}        # character -> glyphs too many
    gaps = []                               # (line, character, left, right)
    for i, ids in of.items():
        ids.sort(key=lambda k: x0[k])
        told = [(c, k) for k in ids for c in _nfkc(glyphs.text[k])]
        have = "".join(c for c, _ in told)
        want = _nfkc(mathpix.plain(lines[i]["text"]))
        if have == want or not want:
            continue
        ops = SequenceMatcher(None, have, want, autojunk=False).get_opcodes()
        same = sum(b - a for op, a, b, _, _ in ops if op == "equal")
        if same < TOLD * max(len(have), len(want)):
            continue                        # a display, a table: no witness
        r = lines[i]["region"]
        for op, a, b, c, d in ops:
            if op == "equal":
                continue
            if op == "replace":             # the glyph's text is another's
                n = min(b - a, d - c)
                a, c = a + n, c + n
            for _, k in told[a:b]:
                spare.setdefault(glyphs.text[k], []).append(k)
            left = x1[told[a - 1][1]] if a else r["top_left_x"]
            right = (x0[told[b][1]] if b < len(told)
                     else r["top_left_x"] + r["width"])
            gaps += [(i, ch, left, right) for ch in want[c:d]]
    if not gaps:
        return own
    for k, i in enumerate(own):
        if i < 0 and glyphs.text[k].strip():
            spare.setdefault(glyphs.text[k], []).append(k)
    out = list(own)
    for i, ch, left, right in gaps:
        r = lines[i]["region"]
        top, height = r["top_left_y"], r["height"]
        mid = top + height / 2
        best = None
        for k in spare.get(ch, ()):
            if out[k] == i:
                continue
            w = x1[k] - x0[k]
            cx, cy = (x0[k] + x1[k]) / 2, (y0[k] + y1[k]) / 2
            if (left - w <= cx <= right + w
                    and top - height / 2 <= cy <= top + 1.5 * height
                    and (best is None or abs(cy - mid) < best[0])):
                best = (abs(cy - mid), k)
        if best is not None:
            out[best[1]] = i
            spare[ch].remove(best[1])
    return out


def line_text(glyphs: Glyphs, own: list[int], line: int) -> str:
    """The glyphs of one line, left to right."""
    mine = sorted((glyphs.x0[g], g) for g in range(glyphs.n)
                  if own[g] == line)
    return "".join(glyphs.text[g] for _, g in mine)


def agreement(lines: list[dict], glyphs: Glyphs, own: list[int]) -> float:
    """Share of non-space characters on which a line's warm-up text and its
    glyphs agree, summed over the page (1.0 for a page without text)."""
    per_line: dict[int, Counter] = {}
    for g in range(glyphs.n):
        if own[g] >= 0:
            per_line.setdefault(own[g], Counter()).update(
                glyphs.text[g].replace(" ", ""))
    same = most = 0
    for i, ln in enumerate(lines):
        a = Counter(mathpix.plain(ln["text"]).replace(" ", ""))
        b = per_line.get(i, Counter())
        same += sum((a & b).values())
        most += max(sum(a.values()), sum(b.values()))
    return same / most if most else 1.0
