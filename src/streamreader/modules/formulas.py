# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Mathematics: inline formulas in text lines, displays as `math` lines.

A glyph is mathematics when its font only sets mathematics (mathtex). Two
things follow from that on one page:

- a line that is formula and no prose is a display. pdftotext makes a line
  of every limit, numerator and index row; the pieces that touch are one
  display, written as one `math` line, the others removed;
- in a line of prose, each run of mathematics becomes `\\( … \\)`. Only when
  the line's glyphs reproduce its warm-up text character for character:
  otherwise the line is left as it is.
"""
from __future__ import annotations

import difflib
import unicodedata

import re

from .. import mathpix, mathtex
from ..bboxlayout import PX_PER_PT
from ..ported import adapter, mathparse, mathrows

MATH_SHARE = 0.6        # of a line's glyphs, for the line to be a formula
ROW_SIZE = 0.8          # a row of a display has a glyph this x its size
TABLE_ROW = 3           # formulas side by side: cells, not displays
TABLE_ROWS = 2          # ... in at least this many rows near each other
ROW_REACH = 2.5         # x a row's height: how near the next row must be
PROSE_CHARS = 8         # a text line this long in the row: the row is prose
SCRIPT = 0.85           # a script is at most this x its base's size
WORD_GAP = 0.15         # x the font size: a gap this wide parts two words
PROSE_PAIRS = 2         # word after word this often: the line is prose
BAND_REACH = 3.0        # x a line height: how far apart a band's parts stand
BAND_INDENT = 1.5       # x a line height: a display is set in this far
INLINE_ROWS = 2.5       # x a line height: no inline formula is taller
BAND_WALL = 1.0         # x a line height: prose this near is the same row
BAND_GLYPHS = 3         # fewer glyphs than this are no display
BAND_GAP = 1.5          # x a line height: a gap this wide between parts ...
BAND_GAPS = 3           # ... this often makes a table row of the band
BAND_MATH = 2           # glyphs from a mathematics font, at least
BAND_SHARE = 0.3        # of a band's glyphs are mathematics
_OPERATORS = frozenset("=+-<>/*|")
_RELATIONS = frozenset("=+<>\u2212\u2264\u2265\u2192\u2208\u00d7\u2261\u2248\u223c\u2260")
_NUMBER = frozenset("0123456789.,%")       # set from a mathematics font or not
_TRAILING = frozenset(",.;:!")
_PREFIXES = ("\n\n", "\n", " ", "")


def _number(ids: list[int], g) -> bool:
    """The glyphs are a number and nothing else. Some families set the
    numbers of a table or a chart's axis from the mathematics italic."""
    return (all(g.text[k] in _NUMBER for k in ids)
            and any(g.text[k].isdigit() for k in ids))


def _box(ln: dict) -> tuple[int, int, int, int]:
    r = ln["region"]
    return (r["top_left_x"], r["top_left_y"], r["top_left_x"] + r["width"],
            r["top_left_y"] + r["height"])


def _gutters(prose: list[tuple], lines: list[tuple]) -> list[tuple]:
    """The gaps between the columns of a page: (left, right, top, bottom).
    `prose`: the boxes of the lines of prose; a gutter has GUTTER_ROWS of
    them on either side, row beside row. `lines`: the boxes of all lines;
    one that runs across the gap (a title, a wide display) ends the gutter
    there, and what is above and below it is tested by itself. A gutter
    reaches as far as the prose in the columns does."""
    if len(prose) < 2 * GUTTER_ROWS:
        return []
    edges = sorted({b[0] for b in prose} | {b[2] for b in prose})
    best: list[tuple] = []                  # runs of gaps: the emptiest of each
    run = None
    for a, b in zip(edges, edges[1:]):
        cover = sum(1 for p in prose if p[0] < b and p[2] > a)
        ok = (cover <= GUTTER_COVER * len(prose)
              and sum(1 for p in prose if p[2] <= a) >= GUTTER_ROWS
              and sum(1 for p in prose if p[0] >= b) >= GUTTER_ROWS)
        if not ok:
            if run:
                best.append(run)
            run = None
        elif run is None or (cover, a - b) < (run[0], run[1] - run[2]):
            run = (cover, a, b)
    if run:
        best.append(run)
    out = []
    for _, a, b in best:
        # (across: well into both columns. pdftotext joins two pieces that
        # face each other over the gap into one short line.)
        reach = b - a
        bars = sorted((l[1], l[3]) for l in lines
                      if l[0] < a - reach and l[2] > b + reach)
        tops = [-10 ** 9] + [bottom for _, bottom in bars]
        bottoms = [top for top, _ in bars] + [10 ** 9]
        side = sorted((p for p in prose if p[2] <= a or p[0] >= b),
                      key=lambda p: p[1])
        heights = sorted(p[3] - p[1] for p in side)
        far = GUTTER_BREAK * heights[len(heights) // 2]
        for top, bottom in zip(tops, bottoms):
            # ... and so does a stretch with no prose in either column: a
            # table or a figure set across both
            groups: list[list[tuple]] = []
            for p in side:
                if not top < (p[1] + p[3]) / 2 < bottom:
                    continue
                if groups and p[1] - max(q[3] for q in groups[-1]) <= far:
                    groups[-1].append(p)
                else:
                    groups.append([p])
            for group in groups:
                right = [p for p in group if p[0] >= b]
                rows = sum(1 for l in group if l[2] <= a
                           and any(r[1] < l[3] and r[3] > l[1] for r in right))
                if rows >= GUTTER_ROWS:
                    out.append((a, b,
                                max(top, group[0][1] - far / 2),
                                min(bottom, max(p[3] for p in group)
                                    + far / 2)))
    return out


def _parted(gutters: list[tuple], a: tuple, b: tuple) -> bool:
    """The boxes `a` and `b` stand in different columns."""
    for xa, xb, top, bottom in gutters:
        if not (top < (a[1] + a[3]) / 2 < bottom
                and top < (b[1] + b[3]) / 2 < bottom):
            continue
        mid, slack = (xa + xb) / 2, (xb - xa) / 4
        if ((a[2] <= mid + slack and b[0] >= mid - slack)
                or (b[2] <= mid + slack and a[0] >= mid - slack)):
            return True
    return False


def _clusters(lines: list[dict], formula: list[int],
              size_of: dict[int, float] | None = None,
              gutters: list[tuple] = ()) -> list[list[int]]:
    """Formula lines that touch: stacked within 0.8 of a line height and
    overlapping, or nearly, across, in one column of the page. `size_of`
    gives each line's largest glyph size, for the scripts met before their
    base."""
    out: list[list] = []                    # [members, box, largest size]
    for i in sorted(formula, key=lambda i: _box(lines[i])[1]):
        x0, y0, x1, y1 = _box(lines[i])
        slack = 0.8 * (y1 - y0)
        size = size_of[i] if size_of else 0.0
        for entry in out:
            members, box = entry[0], entry[1]
            if (y0 <= box[3] + slack and x0 <= box[2] + 2 * slack
                    and x1 >= box[0] - 2 * slack
                    and not _parted(gutters, box, (x0, y0, x1, y1))):
                members.append(i)
                box[:] = [min(box[0], x0), min(box[1], y0),
                          max(box[2], x1), max(box[3], y1)]
                entry[2] = max(entry[2], size)
                break
        else:
            out.append([[i], [x0, y0, x1, y1], size])
    # A piece can be met before the piece that links it to the rest: an
    # exponent lies above its base and is far from what was seen so far. So
    # a cluster set wholly in SCRIPT size is joined to a larger-size cluster
    # whose box it overlaps. Script size, not mere overlap: the cells of a
    # table overlap at their edges too, and joining those made the whole
    # table one display (1701.02095: 319 `math` lines against MathPix's 1).
    merged = bool(size_of)
    while merged:
        merged = False
        out.sort(key=lambda e: e[1][1])
        for a in range(len(out)):
            for b in range(a + 1, len(out)):
                (ma, ba, sa), (mb, bb, sb) = out[a], out[b]
                if bb[1] >= ba[3]:
                    break                   # sorted by top: none further
                if not (bb[0] < ba[2] and bb[2] > ba[0]):
                    continue
                if min(sa, sb) > SCRIPT * max(sa, sb):
                    continue                # peers: cells, or two displays
                ma += mb
                ba[:] = [min(ba[0], bb[0]), min(ba[1], bb[1]),
                         max(ba[2], bb[2]), max(ba[3], bb[3])]
                out[a][2] = max(sa, sb)
                del out[b]
                merged = True
                break
            if merged:
                break
    return [e[0] for e in out]


def _prose_words(ids: list[int], g) -> tuple[int, int]:
    """(prose words, letters in function names) among a line's glyphs. A
    word is a run of upright letters set against each other; `dim`, `sin`
    and their like belong to the formula."""
    words = named = 0
    run: list[int] = []

    def close() -> None:
        nonlocal words, named
        if len(run) >= 2:
            if "".join(g.text[k] for k in run) in mathtex.FUNCTIONS:
                named += len(run)
            else:
                words += 1
        run.clear()

    for k in sorted(ids, key=lambda k: g.x0[k]):
        upright = (not mathtex.is_math(g, k) and len(g.text[k]) == 1
                   and g.text[k].isalpha())
        if not upright or (run and g.x0[k] - g.x1[run[-1]]
                           > 0.25 * (g.y1[k] - g.y0[k])):
            close()
        if upright:
            run.append(k)
    close()
    return words, named


def _word_pairs(ids: list[int], g) -> int:
    """How often a word follows a word with nothing but a space between.
    Prose runs word after word; in a formula a name of several upright
    letters stands among symbols, indices and brackets."""
    pairs = 0
    run = 0             # upright letters of the word being read
    before = False      # a word stood just before, only a space since
    last = None
    for k in sorted(ids, key=lambda k: g.x0[k]):
        t = g.text[k]
        upright = (not mathtex.is_math(g, k) and len(t) == 1 and t.isalpha())
        # a word space is a third of an em and shrinks to a fifth; the
        # glyph's box is taller than its em, so the font size is the measure
        gap = (last is not None
               and g.x0[k] - g.x1[last] > WORD_GAP * g.size[k] * PX_PER_PT)
        if upright and not gap:
            run += 1
        else:
            word = run >= 2
            if word and before:
                pairs += 1
            if upright:                 # a space, then the next word
                before = word
                run = 1
            else:                       # a symbol ends the sequence
                before = False
                run = 0
        last = k
    if run >= 2 and before:
        pairs += 1
    return pairs


VETO = True
BANDS = True
BINDERS = True
GAPS = True
JOIN = True
ABSORB = True
CUT = True
CUT_WORDS = 1           # words in a line left outside a display: it cuts
STACK_JOIN = 0.5        # x the line pitch: rows of one display stand this near
OVERLAP = 0.25          # x the line pitch: boxes this deep in each other are one
ITALIC = True
COLUMNS = True
ADOPT = True
FRACTIONS = True
NAMES = True
CLOSERS = True          # a word before a closing bracket stays prose
TYPEWRITER = True       # a word of typewriter code is never in a formula
STRAYS = 2              # glyphs a line of text may hold that its text has not
ATTACH = 0.4            # x the line pitch: a piece this near belongs
GUTTER_ROWS = 3         # rows of prose on both sides: two columns of a page
GUTTER_COVER = 0.2      # of the prose lines may run across both columns
GUTTER_BREAK = 10       # x a line height with no prose: the columns end
ITALIC_WORD = 4         # italic letters set against each other: a word
FRACTION = 0.5          # of a band's width: a fraction bar is shorter
ROW_JOIN = 1.0          # x a line height: rows of one display stand this near
GAP = 1.2               # x the line pitch: a display stands off this far


def _italic(g, k: int) -> bool:
    """A letter of a text font that is italic by its name."""
    t = g.text[k]
    return (len(t) == 1 and t.isalpha() and not mathtex.is_math(g, k)
            and "italic" in mathtex.font_style(g.fonts[g.font[k]]))


def _italic_formula(ids: list[int], g) -> bool:
    """Italic letters with an operator among them and no word of them:
    `a f = x f_x + y f_y`, not `Proof.` and not a line of a theorem."""
    letters = operators = run = 0
    last = None
    for k in sorted(ids, key=lambda k: g.x0[k]):
        if _italic(g, k):
            near = (last is not None and g.size[k] == g.size[last]
                    and g.x0[k] - g.x1[last] < WORD_GAP * g.size[k] * PX_PER_PT)
            run = run + 1 if near else 1
            if run >= ITALIC_WORD:
                return False
            letters += 1
            last = k
        else:
            last = None
            run = 0
            operators += (g.text[k] in _RELATIONS
                          or (mathtex.is_math(g, k) and mathtex.font_class(
                              g.fonts[g.font[k]]) == "symbol"))
    return letters >= 2 and operators >= 1


_BIG = re.compile(r"(big|bigg|Big|Bigg|tp|bt|ex|display)\d*$")


def _binder(g, k: int) -> bool:
    """A glyph that spans rows: tall delimiters, big operators. Known by
    its extension font, or by its name in a font that sets more."""
    return bool(_BIG.search(g.name[k])) or bool(
        adapter._EXTENSION_FONT.search(
            mathtex.bare(g.fonts[g.font[k]].split("+")[-1])))


def _fraction_bar(rules, lines: list[dict], band: list[int], hull,
                  h: float) -> bool:
    """A rule inside the band, well shorter than it, with a line of the
    band right above and one right below: a fraction, where a table's
    rule runs from side to side."""
    if rules is None or not rules.n:
        return False
    boxes = [_box(lines[i]) for i in band]
    for j in range(rules.n):
        x0, x1, y = rules.x0[j], rules.x1[j], rules.y[j]
        if not (hull[0] <= x0 and x1 <= hull[2] and hull[1] < y < hull[3]
                and x1 - x0 < FRACTION * (hull[2] - hull[0])):
            continue
        over = [b for b in boxes if b[0] < x1 and b[2] > x0]
        if (any(b[1] < y and y - (b[1] + b[3]) / 2 < h for b in over
                if (b[1] + b[3]) / 2 < y)
                and any((b[1] + b[3]) / 2 - y < h for b in over
                        if (b[1] + b[3]) / 2 > y)):
            return True
    return False
TRACE: list | None = None     # for diagnosis: why a band was dropped


def _why(hull, reason: str) -> None:
    if TRACE is not None:
        TRACE.append((tuple(hull), reason))


def _bands(lines: list[dict], glyphs_of: dict[int, list[int]], g,
           barred: set[int], clusters: list[list[int]] = (), rules=None,
           gutters: list[tuple] = ()
           ) -> tuple[list[tuple[list[int], tuple, float]], set[int]]:
    """Displays found as stretches of the column: (line indices, box,
    line height) per display.

    pdftotext cuts a display into a line for every numerator, limit and
    text-font part, so no single line of it need look like a formula. A
    band starts from a line holding mathematics and takes in every line
    that is not prose and stands in its rows. It is a display when it is
    mostly mathematics, no prose shares its rows, and it is set in from
    the prose around it or has an equation number at its end.
    `barred`: lines that may not take part (the cells of a table).
    Also returns the indices of those `clusters` that have prose in their
    rows: pieces of a tall inline formula, not a display."""
    text = [i for i, ln in enumerate(lines)
            if ln["type"] == "text" and "parent_id" not in ln
            and "children_ids" not in ln and i in glyphs_of]
    pairs = {i: _word_pairs(glyphs_of[i], g) for i in text}
    prose = [i for i in text if pairs[i] >= PROSE_PAIRS]
    is_prose = set(prose)
    box = {i: _box(lines[i]) for i in text}
    heights = sorted(box[i][3] - box[i][1] for i in prose)
    sizes = sorted(max(g.size[k] for k in glyphs_of[i]) for i in prose)
    body = sizes[len(sizes) // 2] if sizes else 0.0
    free = [i for i in text if i not in is_prose]
    walls = prose
    has_math = {i for i in free if not _number(glyphs_of[i], g)
                and (any(mathtex.is_math(g, k) for k in glyphs_of[i])
                     or (ITALIC and _italic_formula(glyphs_of[i], g)))}
    numbers = [_box(ln) for ln in lines if ln["type"] == "equation_number"]
    taken: set[int] = set()
    out: list[list[int]] = []
    for seed in sorted(has_math, key=lambda i: (box[i][1], box[i][0])):
        if seed in taken:
            continue
        band = [seed]
        in_band = {seed}                # membership; `band` keeps the order
        hull = list(box[seed])
        h = (heights[len(heights) // 2] if heights
             else box[seed][3] - box[seed][1]) or 1
        grown = True
        while grown:
            grown = False
            for i in free:
                if i in taken or i in in_band:
                    continue
                x0, y0, x1, y1 = box[i]
                if (min(hull[3], y1) - max(hull[1], y0) > 0.3 * (y1 - y0)
                        and x0 <= hull[2] + BAND_REACH * h
                        and x1 >= hull[0] - BAND_REACH * h
                        and not _parted(gutters, hull, box[i])):
                    band.append(i)
                    in_band.add(i)
                    hull = [min(hull[0], x0), min(hull[1], y0),
                            max(hull[2], x1), max(hull[3], y1)]
                    grown = True
        taken.update(band)
        ids = [k for i in band for k in glyphs_of[i]]
        # Formulas in rows and columns are a table, unless a glyph that
        # spans rows holds them together: the bracket around a matrix, the
        # sum before a fraction.
        if (BINDERS and any(i in barred for i in band)
                and not any(_binder(g, k) for k in ids)
                and not _fraction_bar(rules, lines, band, hull, h)):
            _why(hull, 'table')
            continue
        math = sum(mathtex.is_math(g, k) for i in band
                   if not _number(glyphs_of[i], g) for k in glyphs_of[i])
        neutral = sum(mathtex.is_neutral(g, k) for k in ids)
        named = sum(_prose_words(glyphs_of[i], g)[1] for i in band)
        # Letters of a text italic are the variables where no mathematics
        # font is used (Times with Symbol). They count when the band is a
        # formula by them: an operator among them, no word of them.
        if ITALIC and _italic_formula(ids, g):
            math += sum(_italic(g, k) for k in ids)
        if (math + neutral + named < BAND_SHARE * len(ids)
                or math < BAND_MATH
                or sum(pairs[i] for i in band) >= PROSE_PAIRS):
            _why(hull, 'share')
            continue
        # all of it in script size: an index or exponent pdftotext cut off
        if body and max(g.size[k] for k in ids) <= SCRIPT * body:
            _why(hull, 'script')
            continue
        # Prose in the band's rows: the band is pieces of a tall inline
        # formula, or what is left of a display whose main line reads as
        # prose. A table cell in its rows: it is more of the table.
        if any(min(hull[3], box[j][3]) - max(hull[1], box[j][1])
               > 0.5 * (box[j][3] - box[j][1])
               and box[j][0] <= hull[2] + BAND_REACH * h
               and box[j][2] >= hull[0] - BAND_REACH * h
               and not _parted(gutters, hull, box[j]) for j in walls):
            _why(hull, 'wall')
            continue
        numbered = any(hull[1] <= (n[1] + n[3]) / 2 <= hull[3]
                       and n[0] >= hull[2]
                       and not _parted(gutters, hull, n) for n in numbers)
        if not numbered:
            if len(ids) < BAND_GLYPHS:
                _why(hull, 'few')
                continue                    # a stray limit, a QED square
            # parts far apart, again and again: the cells of a table row
            spans = sorted((box[i][0], box[i][2]) for i in band)
            gaps, right = 0, spans[0][1]
            for x0, x1 in spans[1:]:
                gaps += x0 - right > BAND_GAP * h
                right = max(right, x1)
            if gaps >= BAND_GAPS:
                _why(hull, 'gaps')
                continue
        # the prose of this column, nearest above and below
        over = [j for j in prose
                if box[j][0] < hull[2] and box[j][2] > hull[0]]
        above = sorted((j for j in over if box[j][3] <= hull[1] + h / 2),
                       key=lambda j: -box[j][3])[:2]
        below = sorted((j for j in over if box[j][1] >= hull[3] - h / 2),
                       key=lambda j: box[j][1])[:2]
        around = above + below
        if not numbered:
            if around:
                # (a band too tall for a line of text needs no indent: a
                # long display starts at the margin)
                if (hull[0] - min(box[j][0] for j in around) < BAND_INDENT * h
                        and hull[3] - hull[1] <= INLINE_ROWS * h):
                    _why(hull, 'indent')
                    continue
            elif len(band) < 2:
                _why(hull, 'lone')
                continue
        out.append((sorted(band), tuple(hull), h))
    walled: set[int] = set()
    for c, members in enumerate(clusters):
        bs = [_box(lines[i]) for i in members]
        if not bs:
            continue
        h = heights[len(heights) // 2] if heights else 1
        x0, y0 = min(b[0] for b in bs), min(b[1] for b in bs)
        x1, y1 = max(b[2] for b in bs), max(b[3] for b in bs)
        # pieces of an inline formula stand within their line of prose; a
        # display of several rows merely has prose close above and below
        if y1 - y0 <= INLINE_ROWS * h and any(
                y0 <= (box[j][1] + box[j][3]) / 2 <= y1
                and box[j][0] <= x1 + BAND_WALL * h
                and box[j][2] >= x0 - BAND_WALL * h
                and not _parted(gutters, (x0, y0, x1, y1), box[j])
                for j in prose):
            walled.add(c)
    return out, walled


def _set_off(lines: list[dict], members: list[int],
             size_of: dict[int, float], pitch: float) -> bool:
    """A display is set off from the text: it has more than one row, or
    the lines above and below it stand further away than a line of the
    paragraph would (GAP x the pitch). A formula that merely fills a line
    of its paragraph stands at the pitch."""
    full = SCRIPT * max(size_of[i] for i in members)
    levels: list[float] = []
    for i in members:
        if size_of[i] > full:
            _, y0, _, y1 = _box(lines[i])
            if all(abs((y0 + y1) / 2 - m) > 0.6 * (y1 - y0) for m in levels):
                levels.append((y0 + y1) / 2)
    if len(levels) != 1 or not pitch:
        return True
    row = levels[0]
    inside = set(members)
    x0 = min(_box(lines[i])[0] for i in members)
    x1 = max(_box(lines[i])[2] for i in members)
    above = below = None
    for i, ln in enumerate(lines):
        if i in inside or ln["type"] != "text" or "children_ids" in ln:
            continue
        if size_of.get(i, 0.0) <= full:
            continue                    # a limit or an index, cut off
        bx0, by0, bx1, by1 = _box(ln)
        if bx1 <= x0 or bx0 >= x1:
            continue
        mid = (by0 + by1) / 2
        if mid < row - 0.5 * pitch:
            above = mid if above is None else max(above, mid)
        elif mid > row + 0.5 * pitch:
            below = mid if below is None else min(below, mid)
    return ((above is None or row - above > GAP * pitch)
            and (below is None or below - row > GAP * pitch))


def _cut_at_prose(members: list[int], lines: list[dict],
                  prose: list[tuple]) -> list[list[int]]:
    """`members` cut wherever a line of prose runs through their box with
    no member in its row."""
    boxes = {i: _box(lines[i]) for i in members}
    x0, y0 = min(b[0] for b in boxes.values()), min(b[1] for b in boxes.values())
    x1, y1 = max(b[2] for b in boxes.values()), max(b[3] for b in boxes.values())
    for px0, py0, px1, py1 in prose:
        mid = (py0 + py1) / 2
        if not (y0 < mid < y1 and px0 < x1 and px1 > x0):
            continue
        if any(b[1] < mid < b[3] for b in boxes.values()):
            continue                    # beside the display, not through it
        above = [i for i in members if (boxes[i][1] + boxes[i][3]) / 2 < mid]
        below = [i for i in members if i not in above]
        if above and below:
            return (_cut_at_prose(above, lines, prose)
                    + _cut_at_prose(below, lines, prose))
    return [members]


def _joined(displays: list[list[int]], lines: list[dict],
            pitch: float) -> list[list[list[int]]]:
    """Displays that are one, as the parts each is made of. Two whose
    boxes lie in each other are one part. One right under the other,
    nearer than rows of text would stand (STACK_JOIN x the pitch), are the
    rows of an alignment found row by row: two parts, each read by itself."""
    def hull(parts):
        bs = [_box(lines[i]) for part in parts for i in part]
        return [min(b[0] for b in bs), min(b[1] for b in bs),
                max(b[2] for b in bs), max(b[3] for b in bs)]

    def joins(ba, bb):
        across = min(ba[2], bb[2]) - max(ba[0], bb[0])
        gap = max(ba[1], bb[1]) - min(ba[3], bb[3])
        return (across > 0 and gap < STACK_JOIN * pitch), gap

    out = sorted(([[list(m)], hull([m])] for m in displays),
                 key=lambda e: e[1][1])
    # the first pair that joins, top to bottom, is joined, and so on until
    # none does. After a join only the pairs with the grown display can
    # have changed, so the search goes on from the first display above
    # that now joins it (or from the grown one), not from the start.
    a = 0
    while a < len(out):
        for b in range(a + 1, len(out)):
            (pa, ba), (pb, bb) = out[a], out[b]
            yes, gap = joins(ba, bb)
            if not yes:
                continue
            if gap > -OVERLAP * pitch:
                pa += pb                    # rows
            else:
                pa[:] = [[i for part in pa + pb for i in part]]
            ba[:] = [min(ba[0], bb[0]), min(ba[1], bb[1]),
                     max(ba[2], bb[2]), max(ba[3], bb[3])]
            del out[b]
            a = next((c for c in range(a) if joins(out[c][1], ba)[0]), a)
            break
        else:
            a += 1
    return [parts for parts, _ in out]


def _side_by_side(lines: list[dict], clusters: list[list[int]],
                  gutters: list[tuple] = ()
                  ) -> tuple[set[int], list[list[int]]]:
    """(cells, lone rows). `cells`: indices into `clusters` of those standing
    TABLE_ROW or more in one row of the page, in a block of at least
    TABLE_ROWS such rows: the cells of a table. `lone rows`: the rows of
    TABLE_ROW or more that stand without such a neighbour row; with
    TABLE_ROWS = 2 that is a display whose parts are set apart by a quad."""
    boxes, hulls = [], []
    for members in clusters:
        bs = [_box(lines[i]) for i in members]
        boxes.append((min(b[1] for b in bs), max(b[3] for b in bs))
                     if bs else None)       # emptied by a merge
        hulls.append((min(b[0] for b in bs), min(b[1] for b in bs),
                      max(b[2] for b in bs), max(b[3] for b in bs))
                     if bs else None)
    rows: list[list[int]] = []
    seen: set[int] = set()
    for a, box in enumerate(boxes):
        if box is None or a in seen:
            continue
        top, bottom = box
        row = [b for b, other in enumerate(boxes) if other is not None
               for t, u in [other]
               if min(bottom, u) - max(top, t) > 0.5 * min(bottom - top,
                                                           u - t)
               and not _parted(gutters, hulls[a], hulls[b])]
        if len(row) >= TABLE_ROW:
            rows.append(row)
            seen.update(row)
    cells: set[int] = set()
    lone: list[list[int]] = []
    for row in rows:
        top = min(boxes[c][0] for c in row)
        bottom = max(boxes[c][1] for c in row)
        reach = ROW_REACH * (bottom - top)
        near = sum(1 for other in rows if other is not row
                   and min(boxes[c][0] for c in other) <= bottom + reach
                   and max(boxes[c][1] for c in other) >= top - reach)
        if near + 1 >= TABLE_ROWS:
            cells.update(row)
        else:
            lone.append(row)
    return cells, lone


# psred's token function writes an unknown glyph name as `\name{}`.
_UNMAPPED = re.compile(r"\\[A-Za-z][A-Za-z0-9.]*\{\}")


_SPELLING = (
    (re.compile(r"\\mathrm\{([A-Za-z]{2,})\}"), r"\\operatorname{\1}"),
    (re.compile(r"\\to(?![A-Za-z])"), r"\\rightarrow"),
    (re.compile(r"\\ast(?![A-Za-z])"), "*"),
    (re.compile(r"\\,\|\\,"), r"\\mid "),
    (re.compile(r"\\overline\{([A-Za-z])\}"), r"\\bar{\1}"),
    # three dots set one by one
    (re.compile(r"\.(?:\\[,:;!])?\.(?:\\[,:;!])?\.(?:\\[,:;!])?"
                r"(?=([A-Za-z])?)"),
     lambda m: "\\ldots " if m.group(1) else "\\ldots"),
    (re.compile(r"\\cdot\s*\\cdot\s*\\cdot(?![A-Za-z])"), r"\\cdots"),
)


def mathpix_spelling(tex: str) -> str:
    """The same formula in the commands MathPix writes: an upright word is
    an operator name, an arrow is `\rightarrow`, a bar over one letter is
    `\bar`. Measured as the most frequent token differences on the corpus."""
    for pattern, to in _SPELLING:
        tex = pattern.sub(to, tex)
    # a word set letter by letter in one alphabet: \mathbf{Set}
    before = None
    while before != tex:
        before, tex = tex, _ALIKE.sub(r"\\\1{\2", tex)
    return tex


_ALIKE = re.compile(r"\\(mathbf|mathrm|mathit|mathsf|mathtt)"
                    r"\{([^{}]*)\}\\\1\{")     # words; not \mathcal{A}\mathcal{B}


def _bars(rules, g, ids: list[int]) -> list[int]:
    """Rules lying inside the box of the glyphs `ids`."""
    if rules is None or not rules.n:
        return []
    size = max(g.size[k] for k in ids) * PX_PER_PT
    x0, x1 = min(g.x0[k] for k in ids), max(g.x1[k] for k in ids)
    y0, y1 = min(g.y0[k] for k in ids), max(g.y1[k] for k in ids)
    return [j for j in range(rules.n)
            if x0 - size <= (rules.x0[j] + rules.x1[j]) / 2 <= x1 + size
            and y0 - size <= rules.y[j] <= y1 + size]


def _stacked(ids: list[int], g, rules) -> set[int]:
    """The glyphs of `ids` that stand right over or right under a rule
    which has glyphs of `ids` on its other side too, and is no longer than
    they are wide: numerator and denominator of a fraction in a line of
    text. The bar is a rule, so `{1\\over2}` set in the text font is two
    digits to a reader of glyphs: `12`."""
    out: set[int] = set()
    if rules is None or not rules.n or not ids:
        return out
    for j in range(rules.n):
        x0, x1, y = rules.x0[j], rules.x1[j], rules.y[j]
        over, under = [], []
        for k in ids:
            if not x0 <= (g.x0[k] + g.x1[k]) / 2 <= x1:
                continue
            h = g.y1[k] - g.y0[k]
            if y - 1.5 * h <= g.y1[k] <= y + 0.15 * h:
                over.append(k)
            elif y - 0.15 * h <= g.y0[k] <= y + 1.5 * h:
                under.append(k)
        if not over or not under:
            continue
        both = over + under
        size = max(g.x1[k] - g.x0[k] for k in both)
        if (x0 >= min(g.x0[k] for k in both) - size
                and x1 <= max(g.x1[k] for k in both) + size):
            out.update(both)
    return out


def _parsed(g, rules, ids: list[int], style: str) -> str | None:
    """The glyphs as LaTeX by psred's parser (fractions, radicals, limits,
    scripts, accents, spacing), rows split where it is a multi-row display.
    None when it fails or leaves a glyph name unmapped: the caller then
    falls back rather than emit a guess."""
    try:
        atoms, bars = adapter.atoms(g, rules, ids)
        if not atoms:
            return None
        if rules is not None:
            keep = set(_bars(rules, g, ids))
            bars = [b for j, b in enumerate(bars) if j in keep]
        if style == "D":
            size = max(a["size"] for a in atoms)
            rows = mathrows.split_rows(atoms, bars, size)
            text = " \\\\\n".join(
                mathparse.parse(adapter.join_stacks(a), b, "D")
                for a, b in rows)
        else:
            text = mathparse.parse(adapter.join_stacks(atoms), bars, style)
    except Exception:                                    # noqa: BLE001
        return None
    if not text or _UNMAPPED.search(text):
        return None
    return mathpix_spelling(text)


def _adopted(parts: list[list[int]], lines: list[dict], free: list[int],
             g) -> list[list[int]]:
    """For each part of a display the glyphs of `free` (those no warm-up
    line holds) that lie in its box: pdftotext gives a tall bracket, a sum
    or an accent no line, or one beside where the glyph is drawn."""
    out: list[list[int]] = [[] for _ in parts]
    hulls = []
    for part in parts:
        bs = [_box(lines[i]) for i in part]
        hulls.append((min(b[0] for b in bs), min(b[1] for b in bs),
                      max(b[2] for b in bs), max(b[3] for b in bs)))
    for k in free:
        cx, cy = (g.x0[k] + g.x1[k]) / 2, (g.y0[k] + g.y1[k]) / 2
        reach = g.x1[k] - g.x0[k]           # a bracket before the first line
        best, best_d = None, None
        for p, (x0, y0, x1, y1) in enumerate(hulls):
            if not x0 - reach <= cx <= x1 + reach:
                continue
            if not (y0 <= cy <= y1 or min(y1, g.y1[k]) - max(y0, g.y0[k])
                    > 0.5 * (y1 - y0)):
                continue                    # ... or taller than the part
            d = abs((y0 + y1) / 2 - cy)
            if best_d is None or d < best_d:
                best, best_d = p, d
        if best is not None:
            out[best].append(k)
    return out


def _display(members: list[int], glyphs_of: dict[int, list[int]],
             g, rules=None, more: list[int] = ()) -> str:
    """The display as rows of LaTeX. Rows come from where the glyphs sit,
    not from the warm-up's lines, which cut a row wherever pdftotext saw a
    gap and make a row of every limit and index. `more`: glyphs of the
    display that no line holds."""
    ids = [k for i in members for k in glyphs_of[i]] + list(more)
    parsed = _parsed(g, rules, sorted(ids), "D")
    if parsed is not None:
        return parsed
    size = max(g.size[k] for k in ids)
    full = [k for k in ids if g.size[k] > ROW_SIZE * size]
    heights = sorted(g.y1[k] - g.y0[k] for k in full)
    height = heights[len(heights) // 2]
    # tall delimiters and big operators span rows: they do not define one
    base = sorted((k for k in full if g.y1[k] - g.y0[k] <= 1.6 * height),
                  key=lambda k: g.y0[k] + g.y1[k]) or full
    rows: list[list[int]] = []
    centres: list[float] = []
    for k in base:
        c = (g.y0[k] + g.y1[k]) / 2
        if rows and c - centres[-1] <= 0.6 * height:
            rows[-1].append(k)
            centres[-1] += (c - centres[-1]) / len(rows[-1])
        else:
            rows.append([k])
            centres.append(c)
    in_row = {k for row in rows for k in row}
    for k in ids:
        if k not in in_row:
            c = (g.y0[k] + g.y1[k]) / 2
            nearest = min(range(len(rows)), key=lambda r: abs(centres[r] - c))
            rows[nearest].append(k)
    return " \\\\\n".join(t for t in (mathtex.to_latex(g, row)
                                       for row in rows) if t)


def _align(plain: str, ids: list[int], g) -> list[tuple[bool, str]] | None:
    """Walk the line's text and its glyphs together. For every glyph:
    (a space precedes it, the characters of the text it stands for), or
    None when they do not tell the same line."""
    out = []
    p = 0
    for k in ids:
        space = False
        while p < len(plain) and plain[p] == " ":
            space, p = True, p + 1
        if p >= len(plain):
            return None
        if mathtex.is_math(g, k):
            out.append((space, plain[p]))       # replaced by LaTeX anyway
            p += 1
            continue
        want = unicodedata.normalize("NFKC", mathpix.seen(g.text[k]))
        if not want:
            out.append((False, ""))             # the text leaves it out
            continue
        end = p + 1
        while (end < len(plain) and end - p < len(want)
               and unicodedata.normalize("NFKC", plain[p:end]) != want):
            end += 1
        if unicodedata.normalize("NFKC", plain[p:end]) != want:
            return None
        out.append((space, plain[p:end]))
        p = end
    return out if not plain[p:].strip() else None


def _without_strays(plain: str, ids: list[int], g) -> list[int] | None:
    """`ids` without the glyphs the line's text does not have, when these
    are at most STRAYS and the text has no character without a glyph: a
    script of the line above or under whose centre lies in this line's
    box. None when the line differs in any other way."""
    nfkc = unicodedata.normalize
    told = [(c, k) for k in ids
            for c in nfkc("NFKC", g.text[k]).replace(" ", "")]
    have = "".join(c for c, _ in told)
    want = nfkc("NFKC", plain).replace(" ", "")
    kept: set[int] = set()
    extra: set[int] = set()
    for op, a, b, c, d in difflib.SequenceMatcher(
            None, have, want, autojunk=False).get_opcodes():
        if op == "insert" or (op == "replace" and d - c > b - a):
            return None                     # text no glyph tells
        n = b - a if op == "equal" else d - c if op == "replace" else 0
        kept.update(k for _, k in told[a:a + n])
        extra.update(k for _, k in told[a + n:b])
    extra -= kept
    if not 0 < len(extra) <= STRAYS:
        return None
    return [k for k in ids if k not in extra]


_CLOSING = frozenset(")]")
_CLOSERS = frozenset({"angbracketright", "parenright", "bracketright",
                      "braceright", "angbracketrightbig", "parenrightbig"})
_OPENING = frozenset("([")


def _runs(ids: list[int], spaced: list[bool], g,
          stacked: set[int] = frozenset()) -> list[tuple[int, int]]:
    """Index ranges [a, b) of `ids` that are formulas.

    The line is cut into tokens at its spaces. A token with a mathematics
    glyph is formula; so is a token of digits, brackets and relations when
    it carries an operator, touches one, lies between two formula tokens,
    sits inside an open bracket, or is set as a script. Upright letters
    before the mathematics of a token are an operator name (`Hom`), after
    it they are prose (`G-invariant`).
    """
    n = len(ids)
    kinds = ["M" if mathtex.is_math(g, k) or k in stacked else
             "N" if mathtex.is_neutral(g, k) else "P" for k in ids]
    text = [g.text[k] for k in ids]
    tokens, start = [], 0
    for k in range(1, n + 1):
        if k == n or spaced[k]:
            tokens.append([start, k])
            start = k
    has_math = [any(kinds[k] == "M" for k in range(s, e)) for s, e in tokens]
    neutral = [all(kinds[k] == "N" for k in range(s, e)) for s, e in tokens]
    for t, (s, e) in enumerate(tokens):         # cut prose glued behind
        if has_math[t]:
            last = max(k for k in range(s, e) if kinds[k] == "M")
            end = last + 1
            while end < e and kinds[end] == "N":
                end += 1
            # letters follow. A word of them is prose glued on
            # (`G-invariant`); one letter is a variable set in the text
            # font, and the formula goes on to the end of the word: `g(x)`
            if end < e and any(kinds[k] == "P" and kinds[k + 1] == "P"
                               for k in range(end, e - 1)):
                while end > last + 1 and (text[end - 1] in _OPERATORS
                                          or text[end - 1] in _OPENING):
                    end -= 1
                tokens[t][1] = end
            # a word right before a closing bracket from a mathematics
            # font is prose: Knuth's <desired size>, not \operatorname{size}
            first = min(k for k in range(s, e) if kinds[k] == "M")
            if (CLOSERS and first - s >= 2
                    and g.name[ids[first]] in _CLOSERS
                    and all(kinds[k] == "P" and text[k].isalpha()
                            for k in range(s, first))):
                tokens[t][0] = first

    def operator(k: int) -> bool:
        return text[k] in _OPERATORS or (
            kinds[k] == "M"
            and mathtex.font_class(g.fonts[g.font[ids[k]]]) == "symbol")

    joined = list(has_math)
    changed = True
    while changed:
        changed = False
        depth = 0
        for t, (s, e) in enumerate(tokens):
            if joined[t]:
                depth += sum(text[k] in _OPENING for k in range(s, e))
                depth -= sum(text[k] in _CLOSING for k in range(s, e))
                depth = max(depth, 0)
                continue
            before = t > 0 and joined[t - 1]
            after = t + 1 < len(tokens) and joined[t + 1]
            # a name set in text italic (`{\it SS}`): between two relation
            # signs of the formula, or with a prime on it. Not any italic
            # word beside a formula: the text of a theorem is italic.
            if NAMES and after and all(_italic(g, ids[k])
                                       for k in range(s, e)):
                nxt = tokens[t + 1][0]
                short = e - s == 1 or all(text[k].isupper()
                                          for k in range(s, e))
                if ((before and text[tokens[t - 1][1] - 1] in _RELATIONS
                     and text[nxt] in _RELATIONS)
                        or (short and g.name[ids[nxt]] == "prime")):
                    joined[t] = changed = True
                    continue
            if not neutral[t] or not (before or after):
                depth = 0
                continue
            small = before and (g.size[ids[s]]
                                <= mathtex.SCRIPT_SIZE
                                * g.size[ids[tokens[t - 1][1] - 1]])
            if ((before and after)
                    or any(operator(k) for k in range(s, e))
                    or (before and operator(tokens[t - 1][1] - 1))
                    or (after and operator(tokens[t + 1][0]))
                    or (before and depth > 0) or small):
                joined[t] = changed = True
                depth += sum(text[k] in _OPENING for k in range(s, e))
                depth = max(depth - sum(text[k] in _CLOSING
                                        for k in range(s, e)), 0)
            else:
                depth = 0

    runs = []
    t = 0
    while t < len(tokens):
        if not joined[t]:
            t += 1
            continue
        u = t
        while (u + 1 < len(tokens) and joined[u + 1]
               and tokens[u][1] == tokens[u + 1][0]):
            u += 1
        s, e = tokens[t][0], tokens[u][1]
        while e > s and kinds[e - 1] == "N" and text[e - 1] in _TRAILING:
            e -= 1                              # ends the sentence
        inside = "".join(text[s:e])
        if inside.count("(") < inside.count(")") and text[e - 1] == ")":
            e -= 1
        if inside.count("(") > inside.count(")") and text[s] == "(":
            s += 1
        if any(kinds[k] == "M" for k in range(s, e)):
            for a, b in _quantities(s, e, ids, kinds, text, g):
                runs += _without_code(a, b, ids, kinds, g)
        t = u + 1
    return runs


def _quantities(s: int, e: int, ids: list[int], kinds: list[str],
                text: list[str], g) -> list[tuple[int, int]]:
    """The run [s, e) without the words that stand alone between angle
    brackets: the syntax notation <register>, set in text italic, is a
    word, not the product r e g i s t e r."""
    if not CLOSERS:
        return [(s, e)]
    out, a, k = [], s, s
    while k < e:
        if g.name[ids[k]] == "angbracketleft":
            m = k + 1
            while m < e and kinds[m] == "P" and text[m].isalpha():
                m += 1
            if (m - k > 2 and m < e
                    and g.name[ids[m]] in _CLOSERS):
                out.append((a, k + 1))
                a = k = m
                continue
        k += 1
    out.append((a, e))
    return [(x, y) for x, y in out if any(kinds[i] == "M"
                                          for i in range(x, y))]


_TYPEWRITER = re.compile(r"^(CM(TT|SLTT|ITT|TCSC|VTT)|SFTT|LMMONO|"
                         r"COURIER|NIMBUSMONO|DEJAVUSANSMONO|INCONSOLATA)|"
                         r"MONO|TYPEWRITER")


def _without_code(s: int, e: int, ids: list[int], kinds: list[str],
                  g) -> list[tuple[int, int]]:
    """The run [s, e) cut where a word of code stands in it: typewriter
    letters, digits and backslashes (`\\vbox`). Typewriter brackets and
    commas stay: Xy-pic's `@(d_1,d_2)` is one formula."""
    if not TYPEWRITER:
        return [(s, e)]
    out, a = [], s
    for k in range(s, e + 1):
        if k == e or (_typewriter(g, ids[k])
                      and (g.text[ids[k]].isalnum()
                           or g.text[ids[k]] == "\\")):
            if any(kinds[i] == "M" for i in range(a, k)):
                out.append((a, k))
            a = k + 1
    return out


def _typewriter(g, i: int) -> bool:
    """A glyph of a typewriter font: code and verbatim, never a formula."""
    return bool(_TYPEWRITER.search(
        mathtex.bare(g.fonts[g.font[i]]).upper().replace("-", "")))


def process(page: dict, record, own: list[int]) -> list[tuple[str, dict | None]]:
    return _decide(page, record, own)[0]


def labels(page: dict, record, own: list[int]) -> list[str]:
    """What each glyph of the page was taken for: 'display', 'inline' or
    'text'. The same decisions as `process`, glyph by glyph, so they can be
    held against a colour twin's truth."""
    return _decide(page, record, own)[1]


def _decide(page: dict, record, own: list[int]):
    g, rules = getattr(record, "glyphs", record), getattr(record, "rules", None)
    glyph_labels = ["text"] * g.n
    lines = page["lines"]
    glyphs_of: dict[int, list[int]] = {}
    for k in range(g.n):
        if own[k] >= 0 and g.text[k].strip():
            glyphs_of.setdefault(own[k], []).append(k)
    # The warm-up takes a tall line for a heading, and a part of a formula
    # with stacked scripts is tall. A heading has words; a line with a
    # mathematics glyph and none is read here as the text it was.
    lines = [dict(ln, type="text")
             if ln["type"] == "section_header" and "parent_id" not in ln
             and (any(mathtex.is_math(g, k) for k in glyphs_of.get(i, ()))
                  or (ITALIC and _italic_formula(glyphs_of.get(i, ()), g)))
             and not _prose_words(glyphs_of.get(i, ()), g)[0] else ln
             for i, ln in enumerate(lines)]

    formula, mixed, plain = [], [], []
    for i, ln in enumerate(lines):
        ids = glyphs_of.get(i)
        if not ids or ln["type"] != "text" or "parent_id" in ln:
            continue
        math = sum(mathtex.is_math(g, k) for k in ids)
        if _number(ids, g):
            math = 0                    # a table's number, an axis's
        if not math:
            if all(mathtex.is_neutral(g, k) or g.text[k] in _NUMBER
                   for k in ids):
                plain.append(i)         # digits, brackets: maybe a part
            elif FRACTIONS and _stacked(ids, g, rules):
                mixed.append(i)         # text with a fraction of digits
            continue
        neutral = sum(mathtex.is_neutral(g, k) for k in ids)
        words, named = _prose_words(ids, g)
        if math + neutral + named >= MATH_SHARE * len(ids) and words < 2:
            formula.append(i)
        else:
            mixed.append(i)

    patches: list[tuple[str, dict | None]] = []
    line_size = {i: max(g.size[k] for k in glyphs_of[i])
                 for i in glyphs_of}
    gutters: list[tuple] = []
    if COLUMNS:
        gutters = _gutters(
            [_box(ln) for i, ln in enumerate(lines)
             if i in glyphs_of and ln["type"] == "text"
             and "children_ids" not in ln
             and _word_pairs(glyphs_of[i], g) >= PROSE_PAIRS],
            [_box(ln) for ln in lines if "children_ids" not in ln])
    clusters = _clusters(lines, formula, line_size, gutters)
    # A numerator or denominator of digits is its own warm-up line and has
    # no mathematics font; inside a display's box it is part of the display.
    boxes = []
    for members in clusters:
        bs = [_box(lines[i]) for i in members]
        boxes.append((min(b[0] for b in bs), min(b[1] for b in bs),
                      max(b[2] for b in bs), max(b[3] for b in bs)))
    for i in plain:
        x0, y0, x1, y1 = _box(lines[i])
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        for members, (bx0, by0, bx1, by1) in zip(clusters, boxes):
            slack = 0.5 * (y1 - y0)
            if bx0 <= cx <= bx1 and by0 - slack <= cy <= by1 + slack:
                members.append(i)
                break
    # An equation number at the margin makes everything in its row one
    # display. Without it a display whose parts are set apart by \qquad is
    # indistinguishable from the cells of a table row.
    numbered: set[int] = set()
    for ln in lines:
        if ln["type"] != "equation_number":
            continue
        nx0, ny0, nx1, ny1 = _box(ln)
        centre = (ny0 + ny1) / 2
        # The number ends its row. A bracketed number in a table cell is
        # typed the same way by the warm-up but has cells to its right.
        if any(o is not ln and _box(o)[1] <= centre <= _box(o)[3]
               and _box(o)[0] >= nx1 for o in lines):
            continue
        row = [c for c, members in enumerate(clusters) if members
               and min(_box(lines[i])[1] for i in members) <= centre
               <= max(_box(lines[i])[3] for i in members)
               and max(_box(lines[i])[2] for i in members) <= nx0
               and not _parted(gutters, _box(lines[members[0]]), _box(ln))]
        if not row:
            continue
        keep = row[0]
        for c in row[1:]:
            clusters[keep] += clusters[c]
            clusters[c] = []
        numbered.add(keep)
        # ... and a piece that reads as prose, `S_i \text{ simple}.`, when it
        # stands between the display's first piece and the number
        left = min(_box(lines[i])[0] for i in clusters[keep])
        slack = ny1 - ny0
        for i in list(mixed):
            x0, y0, x1, y1 = _box(lines[i])
            if (y0 <= centre <= y1 and x0 >= left - slack and x1 <= nx0
                    and not _parted(gutters, (x0, y0, x1, y1), _box(ln))):
                clusters[keep].append(i)
                mixed.remove(i)
    cells, lone = _side_by_side(lines, clusters, gutters)
    for row in lone:                        # one display in several parts?
        bs = [_box(lines[i]) for c in row for i in clusters[c]]
        # A display has its row to itself. Pieces of a tall inline formula
        # stand in a row too, but among the words of their line.
        top, bottom = min(b[1] for b in bs), max(b[3] for b in bs)
        inside = {i for c in row for i in clusters[c]}
        if any(i not in inside
               and ((ln["type"] == "text" and len(ln["text"]) >= PROSE_CHARS)
                    or ln["type"] == "equation_number")
               and top <= (_box(ln)[1] + _box(ln)[3]) / 2 <= bottom
               and not _parted(gutters, bs[0], _box(ln))
               for i, ln in enumerate(lines)):
            _why((0, top, 10 ** 6, bottom), "row-prose")
            cells.update(row)               # (a number that ended the row
            continue                        #  has joined it already)
        # The columns of a table, each a stack of cells, also stand in one
        # row. Parts of a display are one line high.
        # high: one full-size line, with its limits and indices around it.
        full = SCRIPT * max(line_size[i] for i in inside)
        stacked = False
        for c in row:
            levels: list[float] = []
            for i in clusters[c]:
                if line_size[i] <= full:
                    continue
                _, y0, _, y1 = _box(lines[i])
                mid = (y0 + y1) / 2
                if all(abs(mid - m) > 0.6 * (y1 - y0) for m in levels):
                    levels.append(mid)
            stacked = stacked or len(levels) >= 2
        if stacked:
            _why((0, top, 10 ** 6, bottom), "row-stacked")
            cells.update(row)
            continue
        keep = min(row)
        for c in row:
            if c != keep:
                clusters[keep] += clusters[c]
                clusters[c] = []
    # Displays found as bands take in what the line-by-line reading left:
    # text-font parts, lines it took for prose, a lone line set in.
    cluster_of = {i: c for c, members in enumerate(clusters)
                  for i in members}
    barred = {i for c in cells if c not in numbered for i in clusters[c]}
    bands, walled = _bands(lines, glyphs_of, g, barred, clusters, rules,
                           gutters)
    if VETO:
        for c in walled:
            if c not in numbered:
                if TRACE is not None and c not in cells and clusters[c]:
                    _why(_box(lines[min(clusters[c])]), "walled")
                cells.add(c)
    rows_of: dict[int, list] = {}           # column of cells -> its rows
    joined: dict[int, int] = {}
    for band, hull, h in (bands if BANDS else ()):
        # A display the line-by-line reading has built reaches far beyond
        # the band: several rows, set tight. The band is one of its rows,
        # and joining through it would chain display to display.
        touched = {cluster_of[i] for i in band if i in cluster_of}
        far = {c for c in touched
               if min(_box(lines[i])[1] for i in clusters[c]) < hull[1] - h
               or max(_box(lines[i])[3] for i in clusters[c]) > hull[3] + h}
        if any(c not in cells or c in numbered for c in far):
            _why(hull, "reach")
            continue
        # ... but a column of cells that reaches beyond is no display: the
        # band takes its own lines out of it and leaves the rest
        for c in far:
            clusters[c] = [i for i in clusters[c] if i not in band]
            for i in band:
                if cluster_of.get(i) == c:
                    del cluster_of[i]
        keep = next((cluster_of[i] for i in band if i in cluster_of), None)
        if keep is None:
            keep = len(clusters)
            clusters.append([])
        for c in touched:
            if c in far or c in rows_of:    # what is left of it, too
                rows_of.setdefault(c, []).append((hull, h, keep))
        for i in band:
            c = cluster_of.get(i)
            if c is None:
                clusters[keep].append(i)
            elif c != keep and clusters[c]:
                for j in clusters[c]:
                    cluster_of[j] = keep
                clusters[keep] += clusters[c]
                clusters[c] = []
                if c in numbered:
                    numbered.add(keep)
            cluster_of[i] = keep
        clusters[keep] = sorted(set(clusters[keep]))
        mixed[:] = [i for i in mixed if i not in clusters[keep]]
        numbered.add(keep)
    # Rows taken out of one column and set tight are the rows of one
    # display: an alignment whose columns were taken for a table's.
    for rows in rows_of.values():
        rows.sort(key=lambda r: r[0][1])
        for (above, h, a), (below, _, b) in zip(rows, rows[1:]):
            while a != b and not clusters[a] and a in joined:
                a = joined[a]
            if a != b and clusters[a] and clusters[b] and (
                    below[1] - above[3] < ROW_JOIN * h):
                clusters[b] = sorted(set(clusters[a] + clusters[b]))
                clusters[a] = []
                joined[a] = b
    displays: list[list[int]] = []
    pitches: list[float] = []

    def pitch() -> float:
        """From one line of prose to the next, on this page."""
        if not pitches:
            prose = sorted(
                (_box(lines[i]) for i, ln in enumerate(lines)
                 if i in glyphs_of and ln["type"] == "text"
                 and _word_pairs(glyphs_of[i], g) >= PROSE_PAIRS),
                key=lambda b: (b[1], b[0]))
            steps = sorted(
                (b[1] + b[3] - a[1] - a[3]) / 2 for a, b in zip(prose, prose[1:])
                if b[0] < a[2] and b[2] > a[0]
                and 0 < (b[1] + b[3] - a[1] - a[3]) / 2 < 2 * (a[3] - a[1]))
            heights = sorted(b[3] - b[1] for b in prose)
            pitches.append(steps[len(steps) // 2] if steps else
                           1.2 * heights[len(heights) // 2] if heights
                           else 0.0)
        return pitches[0]

    for c, members in enumerate(clusters):
        if not members:
            continue
        first = min(members)
        if c in cells and c not in numbered:
            _why(_box(lines[first]), "cells")
            mixed += members                # a table row: formulas in cells
            continue
        if (c not in numbered and sum(len(glyphs_of[i]) for i in members)
                < BAND_GLYPHS):
            _why(_box(lines[first]), "few")
            mixed += members                # a label in a figure, a QED square
            continue
        if (GAPS and c not in numbered
                and not _set_off(lines, members, line_size, pitch())):
            _why(_box(lines[first]), "no-gap")
            mixed += members                # a formula that fills its line
            continue
        if (len(members) == 1 and c not in numbered
                and lines[first]["text_display"].startswith(" ")):
            _why(_box(lines[first]), "inline")
            mixed.append(first)             # ends a sentence: inline
            continue
        displays.append(members)
    if CUT:
        # A line of prose through a display's box: two displays, which the
        # line-by-line reading or a band has joined across it.
        taken = {i for members in displays for i in members}
        prose = [_box(ln) for i, ln in enumerate(lines)
                 if i in glyphs_of and i not in taken and ln["type"] == "text"
                 and "children_ids" not in ln
                 and (_word_pairs(glyphs_of[i], g) >= PROSE_PAIRS
                      or (CUT_WORDS and _prose_words(glyphs_of[i], g)[0]
                          >= CUT_WORDS))]
        parts = [p for members in displays
                 for p in _cut_at_prose(members, lines, prose)]
        displays = []
        for members in parts:
            if sum(len(glyphs_of[i]) for i in members) < BAND_GLYPHS:
                mixed += members
            else:
                displays.append(members)
    # A fragment inside a display's box is part of it: `p, q` under a sum,
    # a `#` in the text font. Left as a line it would open a paragraph.
    shown = {i for members in displays for i in members}
    loose = [i for i, ln in enumerate(lines)
             if i in glyphs_of and i not in shown and ln["type"] == "text"
             and "parent_id" not in ln and "children_ids" not in ln
             and _word_pairs(glyphs_of[i], g) < PROSE_PAIRS]
    # ... and so is a piece right above or under it that has no word: a
    # limit, a numerator, an index, which pdftotext made lines of and
    # which are too little to be displays.
    wordless = {i for i in loose if ATTACH
                and not _prose_words(glyphs_of[i], g)[0]}
    near = ATTACH * pitch() if wordless else 0.0
    reach = pitch() if wordless else 0.0    # ... or right beside its end
    # (a piece that stands in a row of text is part of that row: the
    # radical, the exponent, the full stop of the line under the display)
    worded = [_box(lines[i]) for i in glyphs_of
              if i not in shown and i not in wordless
              and lines[i]["type"] == "text"
              and "children_ids" not in lines[i]] if wordless else []
    wordless = {i for i in wordless
                for x0, y0, x1, y1 in [_box(lines[i])]
                if not any(b[1] < y1 and b[3] > y0
                           and b[0] - reach <= (x0 + x1) / 2 <= b[2] + reach
                           for b in worded)}
    for members in displays:
        bs = [_box(lines[i]) for i in members]
        bx0, by0 = min(b[0] for b in bs), min(b[1] for b in bs)
        bx1, by1 = max(b[2] for b in bs), max(b[3] for b in bs)
        grown = True
        while grown:
            grown = False
            for i in (loose if ABSORB else ()):
                if i in shown:
                    continue
                x0, y0, x1, y1 = _box(lines[i])
                if not bx0 <= (x0 + x1) / 2 <= bx1:
                    continue
                if by0 <= (y0 + y1) / 2 <= by1:
                    members.append(i)
                    shown.add(i)
                elif (i in wordless and y1 > by0 - near and y0 < by1 + near):
                    members.append(i)
                    shown.add(i)
                    by0, by1 = min(by0, y0), max(by1, y1)
                    grown = True
    mixed[:] = [i for i in mixed if i not in shown]
    joined = (_joined(displays, lines, pitch()) if JOIN
              else [[m] for m in displays])
    free = [k for k in range(g.n) if own[k] < 0 and g.text[k].strip()]
    for parts in joined:
        parts.sort(key=lambda part: min(_box(lines[i])[1] for i in part))
        members = [i for part in parts for i in part]
        first = min(members)
        more = (_adopted(parts, lines, free, g) if ADOPT and free
                else [[] for _ in parts])
        taken = {k for ks in more for k in ks}
        free = [k for k in free if k not in taken]
        latex = " \\\\\n".join(_display(part, glyphs_of, g, rules, ks)
                                for part, ks in zip(parts, more))
        text = "\\[\n" + latex + "\n\\]"
        boxes = [_box(lines[i]) for i in members] + [
            (int(g.x0[k]), int(g.y0[k]), round(g.x1[k]), round(g.y1[k]))
            for k in taken]
        for k in taken:
            glyph_labels[k] = "display"
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
        patches.append((lines[first]["id"], {
            "type": "math", "text": text, "text_display": "\n" + text,
            "cnt": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
            "region": {"top_left_x": x0, "top_left_y": y0,
                       "width": x1 - x0, "height": y1 - y0}}))
        patches += [(lines[i]["id"], None) for i in members if i != first]
        for i in members:
            for k in glyphs_of[i]:
                glyph_labels[k] = "display"

    for i in sorted(mixed):
        ln = lines[i]
        prefix = next((p for p in _PREFIXES
                       if ln["text_display"] == p + ln["text"]), None)
        if prefix is None:
            continue
        ids = sorted(glyphs_of[i], key=lambda k: g.x0[k])
        aligned = _align(mathpix.plain(ln["text"]), ids, g)
        if aligned is None and STRAYS:
            ids = _without_strays(mathpix.plain(ln["text"]), ids, g)
            aligned = ids and _align(mathpix.plain(ln["text"]), ids, g)
        if not aligned:
            continue
        spaced = [s for s, _ in aligned]
        runs = dict(_runs(ids, spaced, g,
                          _stacked(ids, g, rules) if FRACTIONS else ()))
        if not runs:
            continue
        out, k = "", 0
        while k < len(ids):
            if spaced[k]:
                out += " "
            if k in runs:
                run = ids[k:runs[k]]
                for r in run:
                    glyph_labels[r] = "inline"
                out += "\\(" + (_parsed(g, rules, run, "T")
                                or mathtex.to_latex(g, run)) + "\\)"
                k = runs[k]
            else:
                out += mathpix.escape(aligned[k][1])
                k += 1
        patches.append((ln["id"], {"text": out, "text_display": prefix + out}))
    return patches, glyph_labels
