# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Warm-up pass without pdftotext: blocks, lines and words from the glyphs.

The same `bboxlayout.Page` that `pdftotext -tsv` gives, built from the
patched pdfminer's glyphs in the order the content stream set them. A
glyph continues a line when it sits in the line's band (a sub- or
superscript does, the next line of prose does not) and follows on to the
right; otherwise it goes on with the most recent line that takes it (the
formula after a fraction or a sum's limits), or starts a new one. Words
are cut at gaps wider than a letter's kern; a TeX accent set as a glyph of
its own goes onto its letter. Blocks are runs of lines set one under the
other in the same type. A run of glyphs that steps along y at one x (the
arXiv stamp in the margin) is a line set up the page.
"""
from __future__ import annotations

import re
import unicodedata

from . import bboxlayout, mathtex
from .bboxlayout import PX_PER_PT, Line, Page
from .glyphs import Glyphs, PageGlyphs, band

ABOVE = 0.7             # em: a baseline this far above the line's
BELOW = 0.8             # ... or this far below it is in the line's band
                        # (TeX's scripts and inline fractions; the next
                        # line is 1.2 em down)
HANG = 2.5              # em: a hung glyph's top this far above the baseline
SMALLER = 0.4           # x the line's size: type this much smaller or
LARGER = 2.5            # larger is not on the line (scripts are 0.5-0.7)
SCRIPT = 0.9            # x the hung glyph's size: smaller type is a limit
BACK = 0.5              # em: a glyph may start this far left of the line's end
GAP = 3.0               # em: a wider gap on the baseline starts a new line
OPEN = 6                # lines back a glyph may go on with
WORD = 0.12             # em: a wider gap between glyphs is a space
BLOCK = 1.75            # em: a baseline further down ends a block (TeX
                        # sets lines 1.2 em apart)
SIZE = 0.15             # a type size differing by more ends a block

# a spacing accent and the combining mark it stands for
_ACCENTS = {"´": "́", "`": "̀", "^": "̂", "ˆ": "̂",
            "¨": "̈", "~": "̃", "˜": "̃", "¯": "̄",
            "˘": "̆", "˙": "̇", "˚": "̊", "¸": "̧",
            "˝": "̋", "˛": "̨", "ˇ": "̌"}


_LIGATURE = re.compile("[\ufb00-\ufb06]")


class _Line:
    """`hung`: the line holds only glyphs hung from their top (a display's
    integral or big brace) and has no baseline of its own yet."""
    __slots__ = ("ids", "base", "em", "x1", "vertical", "hung", "last")

    def __init__(self, g: Glyphs, i: int, vertical: bool = False) -> None:
        self.ids = [i]
        self.base = g.base[i]
        self.em = _em(g, i)
        self.x1 = g.x1[i]
        self.vertical = vertical
        self.hung = _hung(g, i)
        self.last = g.x0[i]

    def takes(self, g: Glyphs, i: int) -> bool:
        base, em = g.base[i], self.em
        if not SMALLER * em <= _em(g, i) <= LARGER * em:
            return False                # a drop cap, a chapter's numeral
        if self.hung:
            low, high = self.base - ABOVE * em, self.base + HANG * em
        elif _hung(g, i):
            low, high = self.base - HANG * em, self.base + BELOW * em
        else:
            low, high = self.base - ABOVE * em, self.base + BELOW * em
        # an accent sits over the glyph after it: back to where that starts
        return (low <= base <= high
                and g.x0[i] >= min(self.x1 - BACK * em, self.last - 1)
                and g.x0[i] - self.x1 <= GAP * em)

    def add(self, g: Glyphs, i: int) -> None:
        self.ids.append(i)
        self.x1 = max(self.x1, g.x1[i])
        self.last = g.x0[i]
        # the baseline is a glyph's of the type around: not a limit's
        if (self.hung and not _hung(g, i)
                and _em(g, i) >= SCRIPT * self.em):
            self.base, self.em, self.hung = g.base[i], _em(g, i), False


# fonts whose glyphs hang from their reference point: TeX's extension fonts
_EXTENSION = re.compile(r"^(CMEX|LMMATHEXTENSION|TXEX|PXEX|NTXEXX?|MTEX|"
                        r"MT2EX|EUEX|ESINT|STIXSIZE|BLEX)", re.I)
_hung_cache: dict[str, bool] = {}


def _hung(g: Glyphs, i: int) -> bool:
    name = g.fonts[g.font[i]]
    hung = _hung_cache.get(name)
    if hung is None:
        hung = _hung_cache[name] = bool(_EXTENSION.match(
            mathtex.bare(name).replace("-", "")))
    return hung


def _em(g: Glyphs, i: int) -> float:
    return (g.size[i] or 10.0) * PX_PER_PT


def _visible(g: Glyphs, i: int) -> bool:
    return (bool(g.text[i].strip()) and g.x1[i] > g.x0[i] - 1
            and not mathtex.is_picture(g.fonts[g.font[i]]))


def _vertical_runs(g: Glyphs) -> list[list[int]]:
    """Runs of two or more glyphs set up (or down) the page: no advance
    along x, one x, each next to the one before along y."""
    runs, run = [], []
    for i in range(g.n):
        if (run and abs(g.adv[i]) < 0.01 and abs(g.x0[i] - g.x0[run[-1]]) < 1
                and min(abs(g.y1[i] - g.y0[run[-1]]),
                        abs(g.y0[i] - g.y1[run[-1]])) <= 0.5 * _em(g, i)):
            run.append(i)
            continue
        if len(run) > 1:
            runs.append(run)
        run = [i] if abs(g.adv[i]) < 0.01 and g.y1[i] > g.y0[i] else []
    if len(run) > 1:
        runs.append(run)
    return runs


def _diagonal(g: Glyphs) -> set[int]:
    """Glyphs of strings set at a slant (a watermark across the page): one
    show operator whose glyphs climb or fall along x. MathPix leaves them."""
    out: set[int] = set()
    for i in range(1, g.n):
        if (g.op[i] == g.op[i - 1] and abs(g.adv[i - 1]) >= 0.01
                and abs(g.move[i]) < 0.05 * _em(g, i)
                and abs(g.base[i] - g.base[i - 1]) > 0.02 * _em(g, i)):
            out.update((i - 1, i))
    return out


def lines_of(g: Glyphs) -> list[_Line]:
    """The page's lines, in the order their first glyphs were set."""
    upright = _diagonal(g)
    lines: list[_Line] = []
    for run in _vertical_runs(g):
        ln = _Line(g, run[0], vertical=True)
        ln.ids = list(run)
        lines.append(ln)
        upright.update(run)
    current: _Line | None = None
    for i in range(g.n):
        if i in upright or not _visible(g, i):
            continue
        if current is not None and current.takes(g, i):
            current.add(g, i)
            continue
        back = next((ln for ln in reversed(lines[-OPEN:])
                     if not ln.vertical and ln.takes(g, i)), None)
        if back is not None:
            back.add(g, i)
            current = back
            continue
        current = _Line(g, i)
        lines.append(current)
    lines.sort(key=lambda ln: ln.ids[0])
    return lines


def _accent_onto(g: Glyphs, ids: list[int]) -> list[tuple[int, str]]:
    """(glyph, text) along the line, a text accent folded onto the letter
    under it."""
    out: list[tuple[int, str]] = []
    skip = set()
    for k, i in enumerate(ids):
        if i in skip:
            continue
        mark = _ACCENTS.get(g.text[i])
        if mark and not mathtex.font_class(g.fonts[g.font[i]]):
            # the letter it sits on: the neighbour its box overlaps most
            best, overlap = None, 0.0
            for j in (ids[k - 1] if k else None,
                      ids[k + 1] if k + 1 < len(ids) else None):
                if j is None or j in skip or not g.text[j].isalpha():
                    continue
                o = min(g.x1[i], g.x1[j]) - max(g.x0[i], g.x0[j])
                if o > overlap:
                    best, overlap = j, o
            if best is not None and overlap >= 0.3 * (g.x1[i] - g.x0[i]):
                text = unicodedata.normalize("NFC", g.text[best] + mark)
                if best == ids[k - 1] and out and out[-1][0] == best:
                    out[-1] = (best, text)
                else:
                    out.append((best, text))
                    skip.add(best)
                continue
        out.append((i, _text(g, i)))
    return out


def _text(g: Glyphs, i: int) -> str:
    """The glyph's character; read by its name where the font maps it to
    none (cmex10's pieces, manfnt), U+FFFD where the name says nothing."""
    text = g.text[i]
    if text and all(ord(c) < 0x20 for c in text):
        # the font's map says U+0000: nothing to read, as pdftotext has it
        return mathtex.char_of(g.fonts[g.font[i]], g.name[i])
    if text.startswith("(cid:") or "\ufffd" in text or any(
            0xE000 <= ord(c) <= 0xF8FF for c in text):
        return mathtex.char_of(g.fonts[g.font[i]], g.name[i]) or "\ufffd"
    return text


def _space(g: Glyphs, a: int, b: int, right: float, usual: float) -> bool:
    """A word space between glyph `a` and glyph `b` right of it: a space
    glyph between them in the stream, or a gap wider by WORD em than the
    line's usual gap between letters (letter spacing widens them all; a
    producer that puts its spaces in the character spacing and takes them
    back inside words leaves no move at the space)."""
    if a < b - 1 and all(not g.text[k].strip() for k in range(a + 1, b)):
        return True
    return g.x0[b] - right - usual > WORD * _em(g, b)


def _words(g: Glyphs, ln: _Line) -> list[bboxlayout.Word]:
    k = PX_PER_PT
    if ln.vertical:
        ids = ln.ids
        cut = [0] + [n for n in range(1, len(ids)) if min(
            abs(g.y1[ids[n]] - g.y0[ids[n - 1]]),
            abs(g.y0[ids[n]] - g.y1[ids[n - 1]])) > WORD * _em(g, ids[n])
        ] + [len(ids)]
        pieces = [[(i, _text(g, i)) for i in ids[a:b]]
                  for a, b in zip(cut, cut[1:])]
    else:
        ids = sorted(ln.ids, key=lambda i: (g.x0[i], i))
        glyphs = _accent_onto(g, ids)
        # letter spacing: only a line that sets its spaces as glyphs has
        # any to allow for (the glyphs say where its words end)
        usual = 0.0
        left, right_ = g.x0[ids[0]], max(g.x1[i] for i in ids)
        if any(not g.text[k].strip() and g.text[k]
               and abs(g.base[k] - ln.base) <= 0.3 * ln.em
               and left <= g.x0[k] <= right_
               for k in range(min(ln.ids), max(ln.ids) + 1)):
            gaps = sorted(max(0.0, g.x0[b] - g.x1[a])
                          for (a, _), (b, _) in zip(glyphs, glyphs[1:]))
            usual = gaps[len(gaps) // 2] if gaps else 0.0
        pieces, piece, right = [], [], None
        last = None
        for i, text in glyphs:
            if piece and _space(g, last, i, right, usual):
                pieces.append(piece)
                piece, right = [], None
            piece.append((i, text))
            right = g.x1[i] if right is None else max(right, g.x1[i])
            last = i
        if piece:
            pieces.append(piece)
    words = []
    for piece in pieces:
        ids_ = [i for i, _ in piece]
        ys = [(g.y0[i], g.y1[i]) if ln.vertical else band(g, i)
              for i in ids_]
        letters = [i for i in ids_ if g.text[i].isalpha()]
        words.append((min(g.x0[i] for i in ids_) / k,
                       min(y for y, _ in ys) / k,
                       max(g.x1[i] for i in ids_) / k,
                       max(y for _, y in ys) / k,
                       unicodedata.normalize("NFKC", "".join(
                           t for _, t in piece)) if _LIGATURE.search(
                           "".join(t for _, t in piece)) else
                       "".join(t for _, t in piece),
                       None if not letters else all(
                           "bold" in mathtex.font_style(g.fonts[g.font[i]])
                           for i in letters)))
    return words


def _cuts(pg: PageGlyphs) -> list[tuple[float, float, list[float]]]:
    """(top, bottom, xs): where a line is cut into cells, as pdftotext
    cuts it: at a vertical stroke, and at the edges and column edges of
    the tables the table module will find. A formula would take a table's
    rows, and a line across two tables side by side lies in neither."""
    from .modules import tables
    out = []
    posts = pg.posts
    if posts is not None:
        out += [(posts.y0[k], posts.y1[k], [posts.x[k]])
                for k in range(posts.n)]
    found = [(rows, columns) for rows, columns, _ in tables.grids(
        pg.rules, posts)] if tables.GRID else []
    every = tables.words(pg.glyphs)
    if tables.GRID and tables.OPEN:
        found += [(rows, columns) for rows, columns, *_ in tables.open_tables(
            pg.glyphs, every, pg.rules, posts, pg.width)]
    if tables.GRID and tables.POSTS:
        found += [(rows, columns) for rows, columns, *_ in tables.apart(
            found, tables.post_tables(pg.glyphs, every, pg.rules, posts))]
    if tables.UNRULED:
        found += [(rows, columns) for rows, columns, *_ in
                  tables.unruled_tables(pg.glyphs, [], pg.rules)]

    # a table's edges too: tables side by side share their baselines
    out += [(rows[0], rows[-1], list(columns)) for rows, columns in found]
    return out


def _cut(g: Glyphs, lines: list[_Line], cuts) -> list[_Line]:
    out = []
    for ln in lines:
        xs = sorted({x for y0, y1, xs_ in cuts if y0 <= ln.base <= y1
                     for x in xs_} if not ln.vertical else ())
        if not xs:
            out.append(ln)
            continue
        parts: dict[int, list[int]] = {}
        for i in ln.ids:
            centre = (g.x0[i] + g.x1[i]) / 2
            parts.setdefault(sum(x < centre for x in xs), []).append(i)
        for ids in parts.values():
            piece = _Line(g, ids[0])
            piece.ids = ids
            out.append(piece)
    out.sort(key=lambda ln: ln.ids[0])
    return out


def page_of(pg: PageGlyphs) -> Page:
    """The page as `pdftotext -tsv` would give it, in points."""
    g = pg.glyphs
    width, height = pg.points if pg.points[0] else (pg.width / PX_PER_PT,
                                                     pg.height / PX_PER_PT)
    blocks: list[list[Line]] = []
    last = None
    for ln in _cut(g, lines_of(g), _cuts(pg)):
        words = _words(g, ln)
        if not words:
            continue
        box = (min(w[0] for w in words), min(w[1] for w in words),
               max(w[2] for w in words), max(w[3] for w in words))
        here = (box, _type(g, ln))
        if last is None or not _same_block(last, here):
            blocks.append([])
        blocks[-1].append(Line(box, words))
        last = here
    return Page(width, height, blocks)


def _type(g: Glyphs, ln: _Line) -> tuple[float, float] | None:
    """(baseline, em) of the line's main type: the size most of its glyphs
    have, and their middle baseline; None set up the page."""
    if ln.vertical:
        return None
    sizes: dict[float, list[int]] = {}
    for i in ln.ids:
        sizes.setdefault(round(g.size[i], 1), []).append(i)
    main = max(sizes.values(), key=len)
    bases = sorted(g.base[i] for i in main)
    return bases[len(bases) // 2], _em(g, main[0])


def _same_block(a, b) -> bool:
    """The line `b` goes on with the block of the line `a` above it: the
    next baseline down in the same type, the two overlapping across."""
    (abox, at), (bbox, bt) = a, b
    if at is None or bt is None:
        return False
    (abase, aem), (bbase, bem) = at, bt
    small, large = sorted((aem, bem))
    return (0.5 * aem <= bbase - abase <= BLOCK * aem
            and large <= (1 + SIZE) * small
            and bbox[0] < abox[2] and abox[0] < bbox[2])


def page_from_glyphs(doc_id: str, pg: PageGlyphs) -> dict:
    return bboxlayout.page_from_boxes(doc_id, pg.page, page_of(pg))
