# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Ruled tables: a grid of thin horizontal and vertical strokes.

Inside such a grid the warm-up reads every cell as a line of its own, and
the formula module may join cells set in a mathematics font into one
display. This module replaces every line inside the grid by one MathPix
`table`: its text is a `tabular`, its children are the `table_column`s,
the `table_row`s and a `simple_cell` per filled cell (`cell_row`,
`cell_column`), as MathPix writes them. A cell is read from its glyphs.
"""
from __future__ import annotations

import re

from .. import mathpix, mathtex
from ..bboxlayout import PX_PER_PT
from ..glyphs import Glyphs, band
from .formulas import _typewriter

GRID = True             # switch: build tables from ruled grids
TOUCH = 3.0             # px: strokes this close meet
MIN_ROWS = 2            # a grid has at least this many rows ...
MIN_COLUMNS = 2         # ... and columns
INSIDE = 0.5            # share of a line's box in the grid that makes it a cell
OPEN = True             # switch: tables drawn with horizontal rules only
OPEN_WIDTH = 0.15       # x page width: a shorter rule is a fraction bar
OPEN_ROWS = 1           # lines of words between the rules, at least
OPEN_GUTTER = 0.6       # x glyph height: a white gap this wide ends a column
ROW_HEIGHT = 5.0        # x type height: a taller row is a frame, not a table
HEADS = 0.5             # share of cells a row of heads above the grid fills
FILLED = 0.6            # share of cells with a glyph: fewer, a frame or a chart
UNRULED = True          # switch: tables without rules, from the moves in a row
CELL = 0.8              # em: a move this wide between two glyphs ends a cell
STREAM = 4              # glyphs: a glyph this close after another follows it
BASE = 0.45             # em: a glyph this close under the one before is in its row
HEAD_ROWS = 2           # rows of heads over a table may span its columns
ALIGNED = 0.6           # share of a table's cuts that fall on its gutters
TALL = 1.5              # em: a taller glyph in a table makes it a display
BAR = 0.5               # x table width: a shorter stroke in it is a fraction
MATH = 0.5              # share of mathematical glyphs, or of display lines,
                        # that makes a display
LEADERS = 0.2           # share of dots that makes a table of contents
PROSE = 20.0            # em: a wider cell is a line of prose
CODE = 0.05             # x its width: a typewriter gap this near a multiple is code
LEADING = 2.0           # em: rows further apart are two tables
POSTS = True            # switch: tables of column rules and one cross rule
DOUBLE = 12.0           # px: column rules this close are one (||)
REMARKS = True          # formulas beside remarks in parentheses are a display
INDEX = True            # a last column of page numbers only is an index

_NUMBER = re.compile(r"\d+(?:\.\d+)*[.:]?")   # 7, 7., 13.4.1
_PAGES = re.compile(r"\d+(?:[,–-]\s*\d+)*")


def _clusters(values: list[float], tolerance: float) -> list[float]:
    """Sorted values, those within `tolerance` of each other as one."""
    out: list[float] = []
    for v in sorted(values):
        if out and v - out[-1] <= tolerance:
            continue
        out.append(v)
    return out


def grids(rules, posts) -> list[tuple[list[float], list[float], list]]:
    """(row edges, column edges, vertical strokes) of each ruled grid on
    the page: the strokes that meet, taken together, with at least
    MIN_ROWS rows and MIN_COLUMNS columns. A row is cut only where a
    stroke crosses it (`spans`)."""
    if rules is None or posts is None or not rules.n or not posts.n:
        return []
    h = [(rules.x0[i], rules.x1[i], rules.y[i]) for i in range(rules.n)]
    v = [(posts.x[i], posts.y0[i], posts.y1[i]) for i in range(posts.n)]
    parent = list(range(len(h) + len(v)))

    def root(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, (x0, x1, y) in enumerate(h):
        for j, (x, y0, y1) in enumerate(v):
            if (x0 - TOUCH <= x <= x1 + TOUCH
                    and y0 - TOUCH <= y <= y1 + TOUCH):
                parent[root(i)] = root(len(h) + j)
    groups: dict[int, tuple[list, list]] = {}
    for i in range(len(h)):
        groups.setdefault(root(i), ([], []))[0].append(h[i])
    for j in range(len(v)):
        groups.setdefault(root(len(h) + j), ([], []))[1].append(v[j])
    out = []
    for hs, vs in groups.values():
        if len(hs) < 2 or not vs:
            continue
        rows = _clusters([y for _, _, y in hs], TOUCH)
        left = min(x0 for x0, _, _ in hs)
        right = max(x1 for _, x1, _ in hs)
        columns = _clusters([left, right] + [x for x, _, _ in vs], TOUCH)
        if len(rows) - 1 >= MIN_ROWS and len(columns) - 1 >= MIN_COLUMNS:
            out.append((rows, columns, vs))
    return sorted(out, key=lambda rc: (rc[0][0], rc[1][0]))


def open_tables(g: Glyphs, every: list[list[int]], rules, posts,
                page_width: float) -> list:
    """Tables drawn with horizontal rules only (booktabs): two or more
    long rules of the same extent with OPEN_ROWS lines of words between
    them and no vertical stroke; the columns are the white gaps that run
    through every line. (row edges, column edges, [], rule ys, False)."""
    if rules is None or not rules.n:
        return []
    long_ = [(rules.x0[i], rules.x1[i], rules.y[i]) for i in range(rules.n)
             if rules.x1[i] - rules.x0[i] >= OPEN_WIDTH * page_width]
    groups: list[list[tuple[float, float, float]]] = []
    for r in sorted(long_, key=lambda r: (round(r[0]), r[2])):
        for grp in groups:
            if (abs(grp[0][0] - r[0]) <= TOUCH
                    and abs(grp[0][1] - r[1]) <= TOUCH):
                grp.append(r)
                break
        else:
            groups.append([r])
    out = []
    for grp in groups:
        if len(grp) < 2:
            continue
        x0, x1 = grp[0][0], grp[0][1]
        ys = sorted(y for _, _, y in grp)
        top, bottom = ys[0], ys[-1]
        if posts is not None and any(
                x0 - TOUCH <= posts.x[i] <= x1 + TOUCH
                and posts.y0[i] < bottom and posts.y1[i] > top
                for i in range(posts.n)):
            continue                    # a ruled grid, read as one
        inner = [w for w in every
                 if all(x0 <= (g.x0[i] + g.x1[i]) / 2 <= x1
                        and top < (g.y0[i] + g.y1[i]) / 2 < bottom
                        for i in w)]
        if not inner:
            continue
        # lines: words on one baseline
        bases: list[float] = []
        for b in sorted(g.base[w[0]] for w in inner):
            h = g.y1[inner[0][0]] - g.y0[inner[0][0]]
            if not bases or b - bases[-1] > 0.5 * h:
                bases.append(b)
        if len(bases) < OPEN_ROWS:
            continue
        # columns: x ranges no word of any line crosses. Heads over a
        # rule of their own often reach across the columns (booktabs'
        # \\midrule): the body under the first inner rule says.
        body = [w for w in inner if len(ys) < 3
                or g.y0[w[0]] > ys[1]] or inner
        spans_ = sorted((min(g.x0[i] for i in w), max(g.x1[i] for i in w))
                        for w in body)
        height = sorted(g.y1[i] - g.y0[i] for w in inner for i in w)
        gutter = OPEN_GUTTER * height[len(height) // 2]
        edges, reach = [x0], spans_[0][1]
        for a, b in spans_[1:]:
            if a - reach >= gutter:
                edges.append((a + reach) / 2)
            reach = max(reach, b)
        edges.append(x1)
        if len(edges) - 1 < MIN_COLUMNS or (
                len(bases) == 1 and len(edges) - 1 < 3):
            continue                    # one line in two parts: a caption
        # a row ends a little under its baseline: the centres of two
        # lines' glyphs lie a third of a line above their baselines
        # a rule between two lines (booktabs' \\midrule) is their edge
        rows = [top]
        for a, b in zip(bases, bases[1:]):
            inner_rules = [y for y in ys if a < y < b]
            rows.append(inner_rules[0] if inner_rules
                        else a + 0.25 * (b - a))
        rows.append(bottom)
        out.append((rows, edges, [], ys, False))
    return out


def apart(found: list, more: list) -> list:
    """The tables of `more` that overlap none of `found`."""
    boxes = [(c[0], r[0], c[-1], r[-1]) for r, c, *_ in found]
    return [t for t in more
            if not any(t[1][0] < b[2] and b[0] < t[1][-1]
                       and t[0][0] < b[3] and b[1] < t[0][-1]
                       for b in boxes)]


def post_tables(g: Glyphs, every: list[list[int]], rules, posts) -> list:
    """Tables of column rules without a frame (c||c|c, a truth table):
    vertical strokes of one height, the pieces a row's strut leaves
    joined, and a horizontal rule across all of them under the heads. The
    rule spans the table: its ends are the outer edges.
    (row edges, column edges, [], rule ys, False)."""
    if (rules is None or posts is None or not rules.n or not posts.n):
        return []
    pieces = sorted((posts.x[i], posts.y0[i], posts.y1[i])
                    for i in range(posts.n))
    long_: list[list[float]] = []
    for x, y0, y1 in sorted(pieces, key=lambda p: (round(p[0]), p[1])):
        for post in long_:
            if abs(post[0] - x) <= TOUCH and -TOUCH <= y0 - post[2] <= 2 * TOUCH:
                post[2] = max(post[2], y1)
                break
        else:
            long_.append([x, y0, y1])
    groups: list[list[list[float]]] = []
    for post in sorted(long_, key=lambda p: (round(p[1]), p[0])):
        for grp in groups:
            if (abs(grp[0][1] - post[1]) <= 2 * TOUCH
                    and abs(grp[0][2] - post[2]) <= 2 * TOUCH):
                grp.append(post)
                break
        else:
            groups.append([post])
    out = []
    for grp in groups:
        top, bottom = grp[0][1], grp[0][2]
        xs: list[float] = []
        for x in sorted(p[0] for p in grp):
            if xs and x - xs[-1] <= DOUBLE:
                xs[-1] = (xs[-1] + x) / 2
            else:
                xs.append(x)
        cross = [(rules.x0[i], rules.x1[i], rules.y[i])
                 for i in range(rules.n)
                 if top < rules.y[i] < bottom
                 and rules.x0[i] < xs[0] - TOUCH
                 and rules.x1[i] > xs[-1] + TOUCH]
        if not cross:
            continue
        x0 = min(c[0] for c in cross)
        x1 = max(c[1] for c in cross)
        inner = [w for w in every
                 if all(x0 <= (g.x0[i] + g.x1[i]) / 2 <= x1
                        and top - TOUCH <= band(g, i)[0]
                        and g.base[i] <= bottom + TOUCH for i in w)]
        if not inner:
            continue
        bases: list[float] = []
        for b in sorted(g.base[w[0]] for w in inner):
            h = g.y1[inner[0][0]] - g.y0[inner[0][0]]
            if not bases or b - bases[-1] > 0.5 * h:
                bases.append(b)
        if len(bases) < MIN_ROWS:
            continue
        if any(mathtex.is_picture(g.fonts[g.font[i]]) for i in range(g.n)
               if x0 <= g.x0[i] <= x1 and top <= g.base[i] <= bottom):
            continue                    # strokes of a figure (xy-pic)
        ys = sorted(c[2] for c in cross)
        # columns without a rule between them: white gaps through the
        # body (under the cross rule; heads may span)
        body = [w for w in inner if g.base[w[0]] > ys[0]] or inner
        height = sorted(g.y1[i] - g.y0[i] for w in body for i in w)
        gutter = OPEN_GUTTER * height[len(height) // 2]
        spans_ = sorted((min(g.x0[i] for i in w), max(g.x1[i] for i in w))
                        for w in body)
        reach = spans_[0][1]
        for a, b in spans_[1:]:
            mid = (a + reach) / 2
            if a - reach >= gutter and all(abs(mid - x) > gutter for x in xs):
                xs.append(mid)
            reach = max(reach, b)
        xs.sort()
        pitch = (bottom - top) / len(bases)
        if any(abs(rules.x0[i] - x0) <= TOUCH and abs(rules.x1[i] - x1) <= TOUCH
               and (top - 2 * pitch <= rules.y[i] <= top
                    or bottom <= rules.y[i] <= bottom + 2 * pitch)
               for i in range(rules.n)):
            continue                    # a band of a larger ruled table
        rows = [top]
        for a, b in zip(bases, bases[1:]):
            between = [y for y in ys if a < y < b]
            rows.append(between[0] if between else a + 0.25 * (b - a))
        rows.append(bottom)
        out.append((rows, [x0] + xs + [x1], [], ys, False))
    return out


def _em(g: Glyphs, i: int) -> float:
    return g.size[i] * PX_PER_PT


def _row_cells(g: Glyphs, row: list[int]) -> list[list[list[int]]]:
    """A row's glyphs, left to right, cut where the current point moved
    CELL em or more beyond the glyph before: its origin minus that glyph's
    origin and advance (the font's width, not its ink). When the glyph
    follows the other within STREAM glyphs of the content stream, the cut
    ends a cell; else it ends a segment: two columns of prose, or two
    tables side by side, are set one after the other. Spaces between
    typewriter glyphs that are whole multiples of its width are code; a
    comma ends no cell (an index: "\\quad, 154, 332").
    [segment: [cell: [glyph]]]."""
    row = sorted(row, key=lambda i: g.x0[i])
    segments = [[[row[0]]]]
    for a, b in zip(row, row[1:]):
        gap = g.x0[b] - (g.x0[a] + g.adv[a])
        if gap < CELL * max(_em(g, a), _em(g, b)) or g.text[a] == "," or (
                _typewriter(g, a) and _typewriter(g, b) and g.adv[a] > 0
                and abs(gap / g.adv[a] - round(gap / g.adv[a])) <= CODE):
            segments[-1][-1].append(b)
        elif 0 < b - a <= STREAM:
            segments[-1].append([b])
        else:
            segments.append([[b]])
    return segments


def _rows(g: Glyphs) -> list[tuple[float, float, list[list[list[int]]]]]:
    """The page's rows top to bottom: (baseline, em, segments). Glyphs
    raised or lowered less than BASE em from the one before (scripts,
    the E of the TeX logo) stay in its row."""
    ids = sorted((i for i in range(g.n)
                  if g.text[i].strip() or g.name[i] in mathtex.CHARS),
                 key=lambda i: g.base[i])
    rows: list[list[int]] = []
    for i in ids:
        if rows and g.base[i] - g.base[rows[-1][-1]] <= BASE * _em(g, i):
            rows[-1].append(i)
        else:
            rows.append([i])
    out = []
    for row in rows:
        sizes = sorted(row, key=lambda i: g.size[i])
        main = sizes[len(sizes) // 2]
        bases = sorted(g.base[i] for i in row if g.size[i] == g.size[main])
        out.append((bases[len(bases) // 2], _em(g, main), _row_cells(g, row)))
    return out


def _blocks(rows: list) -> list[list]:
    """Runs of MIN_ROWS or more rows of two cells or more, each at most
    LEADING em under the one before."""
    blocks: list[list] = []
    above = None
    for row in rows:
        if sum(len(s) for s in row[2]) < 2:
            above = None
            continue
        if above is None or row[0] - above[0] > LEADING * row[1]:
            blocks.append([])
        blocks[-1].append(row)
        above = row
    return [b for b in blocks if len(b) >= MIN_ROWS]


def _span(g: Glyphs, ids: list[int]) -> tuple[float, float]:
    return min(g.x0[i] for i in ids), max(g.x1[i] for i in ids)


def _merged(spans_: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[list[float]] = []
    for a, b in sorted(spans_):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


def unruled_tables(g: Glyphs, taken: list[tuple[float, float, float, float]],
                   rules=None) -> list:
    """Tables without rules: MIN_ROWS or more rows one under the other,
    each cut into cells by wide moves (`_row_cells`), whose cuts line up
    in white columns no cell crosses (gutters). A gutter needs a cut in
    MIN_ROWS rows. Segments side by side (lanes) are read apart. Blocks
    that meet `taken` boxes (ruled tables, page furniture) are left, and
    so are blocks a stroke shorter than BAR of their width runs through:
    the bars of fractions whose numerators and denominators form rows.
    (row edges, column edges, [], [], None) as `open_tables`."""
    out = []
    for block in _blocks(_rows(g)):
        lanes = _merged([_span(g, [i for c in s for i in c])
                         for _, _, segs in block for s in segs])
        for lo, hi in lanes:
            rows = [(base, em, [[c for s in segs for c in s
                                 if lo <= g.x0[c[0]] <= hi]])
                    for base, em, segs in block]
            for sub in _blocks(rows):
                found = _table(g, [cells for _, _, (cells,) in sub],
                               [base for base, _, _ in sub])
                bars = [] if rules is None or found is None else [
                    (rules.x0[k], rules.y[k], rules.x1[k], rules.y[k])
                    for k in range(rules.n) if rules.x1[k] - rules.x0[k]
                    < BAR * (found[1][-1] - found[1][0])]
                if found and _tall_glyph(g, found):
                    continue            # a display: integrals, delimiters
                if found and not any(
                        found[1][0] < b[2] and b[0] < found[1][-1]
                        and found[0][0] <= b[3] and b[1] <= found[0][-1]
                        for b in taken + bars):
                    out.append(found)
    return out


def _gutters(g: Glyphs, block: list[list[list[int]]]
             ) -> list[tuple[float, float]]:
    """White columns no cell of `block` crosses, with a cut in MIN_ROWS
    rows, when most cuts of the rows fall on them (ALIGNED): words set
    apart by quads in a line or two line up by chance once."""
    boxes = _merged([_span(g, c) for cells in block for c in cells])
    gaps = [(_span(g, c)[1], _span(g, d)[0])
            for cells in block for c, d in zip(cells, cells[1:])]
    gutters = [(a[1], b[0]) for a, b in zip(boxes, boxes[1:])]
    gutters = [(lo, hi) for lo, hi in gutters
               if sum(a <= lo and hi <= b for a, b in gaps) >= MIN_ROWS]
    on = sum(any(a <= lo and hi <= b for lo, hi in gutters) for a, b in gaps)
    return gutters if on >= ALIGNED * len(gaps) else []


def _tall_glyph(g: Glyphs, found) -> bool:
    """A glyph in the table's box taller than TALL em of the type around
    it, a display-size operator or a piece of a large delimiter: a
    display."""
    (rows, columns, *_) = found
    inside = [i for i in range(g.n)
              if columns[0] <= (g.x0[i] + g.x1[i]) / 2 <= columns[-1]
              and rows[0] <= (g.y0[i] + g.y1[i]) / 2 <= rows[-1]]
    if not inside:
        return False
    em = sorted(_em(g, i) for i in inside)[len(inside) // 2]
    return any(g.y1[i] - g.y0[i] > TALL * em
               or g.name[i].endswith("display")     # cmex's font box lies
               or g.name[i].endswith(("tp", "bt", "ex", "mid"))
               and g.name[i] in mathtex.CHARS for i in inside)


def _table(g: Glyphs, block: list[list[list[int]]], bases: list[float]):
    """(row edges, column edges, [], [], None) of rows of cells, or None
    without MIN_COLUMNS columns or with a cell wider than PROSE em (a line
    of prose and its margin note, a line of contents and its page), with
    MATH of its glyphs mathematical (a display) or LEADERS of them dots
    (contents), or of two columns whose first holds line numbers only. Heads
    may span columns (\\multicolumn): the columns are those of the rows
    under up to HEAD_ROWS rows, if that gives more of them."""
    cells_ = [c for cells in block for c in cells]
    if any(_span(g, c)[1] - _span(g, c)[0] > PROSE * _em(g, c[0])
           for c in cells_):
        return None
    every = [i for c in cells_ for i in c]
    if (sum(mathtex.is_math(g, i) for i in every) >= MATH * len(every)
            or sum(g.text[i] == "." for i in every) >= LEADERS * len(every)):
        return None                     # a display; contents with leaders
    gutters: list[tuple[float, float]] = []
    for k in range(HEAD_ROWS + 1):
        if k and len(block) - k < MIN_ROWS + 1:
            break
        found = _gutters(g, block[k:])
        if len(found) > len(gutters):
            gutters = found
    if len(gutters) + 1 < MIN_COLUMNS:
        return None
    if len(gutters) == 1 and all(
            _NUMBER.fullmatch("".join(g.text[i] for i in cells[0]))
            for cells in block if _span(g, cells[0])[1] <= gutters[0][0]):
        return None                     # numbered lines: an algorithm
    edge = gutters[-1][1]
    last = ["".join(g.text[i] for i in c).strip() for cells in block
            for c in cells if _span(g, c)[0] >= edge]
    rest = [i for cells in block for c in cells if _span(g, c)[0] < edge
            for i in c if not mathtex.is_neutral(g, i)]
    if REMARKS and last and rest and all(
            t.startswith("(") or t.endswith(")") for t in last) and sum(
            mathtex.is_math(g, i) for i in rest) >= MATH * len(rest):
        return None                     # = ... (by the Jacobi identity)
    terms = ["".join(g.text[i] for i in c).strip() for cells in block
             for c in cells if _span(g, c)[0] < edge]
    if INDEX and last and all(_PAGES.fullmatch(t) for t in last) and all(
            len(t) > 1 and not _PAGES.fullmatch(t) for t in terms):
        return None                     # an index: terms and their pages,
                                        # not glyphs and their slots
    y0 = min(g.y0[i] for i in every)
    y1 = max(g.y1[i] for i in every)
    x0 = min(g.x0[i] for i in every)
    x1 = max(g.x1[i] for i in every)
    edges = [y0] + [a + 0.25 * (b - a) for a, b in zip(bases, bases[1:])]
    return (edges + [y1], [x0] + [(lo + hi) / 2 for lo, hi in gutters]
            + [x1], [], [], None)


def spans(columns: list[float], posts: list, top: float,
          bottom: float) -> list[tuple[int, int]]:
    """The cells of one row as [first, last) column ranges: the row is cut
    at a column edge where a vertical stroke crosses its middle. A row
    that no stroke crosses (heads above the grid) is cut at every edge."""
    mid = (top + bottom) / 2
    crossing = [k for k in range(1, len(columns) - 1)
                if any(abs(x - columns[k]) <= TOUCH
                       and y0 - TOUCH <= mid <= y1 + TOUCH
                       for x, y0, y1 in posts)]
    if not any(y0 - TOUCH <= mid <= y1 + TOUCH for _, y0, y1 in posts):
        crossing = list(range(1, len(columns) - 1))
    cuts = [0] + crossing + [len(columns) - 1]
    return list(zip(cuts, cuts[1:]))


def _cells(g: Glyphs, every: list[list[int]], rows: list[float],
           columns: list[float]) -> dict[tuple[int, int], list[list[int]]]:
    """The words in each cell, by where their ink's centre is."""
    cells: dict[tuple[int, int], list[list[int]]] = {}
    for word in every:
        boxes = [_ink(g, i) for i in word]
        r = _band(rows, (min(b[1] for b in boxes)
                         + max(b[3] for b in boxes)) / 2)
        c = _band(columns, (min(b[0] for b in boxes)
                            + max(b[2] for b in boxes)) / 2)
        if r is not None and c is not None:
            cells.setdefault((r, c), []).append(word)
    return cells


def _filled(g: Glyphs, every: list[list[int]], rows: list[float],
            columns: list[float], posts: list) -> float:
    """Share of the cells between `rows` that hold something."""
    cells = _cells(g, every, rows, columns)
    full = total = 0
    for r in range(len(rows) - 1):
        for a, b in spans(columns, posts, rows[r], rows[r + 1]):
            total += 1
            full += any(cell_text(g, cells.get((r, c), []))
                        for c in range(a, b))
    return full / total if total else 0.0


def _tall(g: Glyphs, every: list[list[int]], rows: list[float],
          columns: list[float]) -> bool:
    """Rows far taller than the type in them: boxes drawn around a few
    words, not a table."""
    inner = [i for w in every for i in w
             if columns[0] <= g.x0[i] <= columns[-1]
             and rows[0] <= g.y0[i] <= rows[-1]]
    if not inner:
        return True
    heights = sorted(g.y1[i] - g.y0[i] for i in inner)
    pitch = sorted(b - a for a, b in zip(rows, rows[1:]))
    return pitch[len(pitch) // 2] > ROW_HEIGHT * heights[len(heights) // 2]


def _band(edges: list[float], v: float) -> int | None:
    for k in range(len(edges) - 1):
        if edges[k] <= v < edges[k + 1]:
            return k
    return None


def _ink(g: Glyphs, i: int) -> tuple[float, float, float, float]:
    """Where the glyph is: its ink box when known, else its font box."""
    box = (g.ix0[i], g.iy0[i], g.ix1[i], g.iy1[i])
    if all(v == v for v in box) and box[2] > box[0]:
        return box
    return g.x0[i], g.y0[i], g.x1[i], g.y1[i]


def words(g: Glyphs) -> list[list[int]]:
    """The page's visible glyphs, those set next to each other on one
    baseline as one word."""
    ids = sorted((i for i in range(g.n)
                  if g.text[i].strip() or g.name[i] in mathtex.CHARS),
                 key=lambda i: (round(g.base[i]), g.x0[i]))
    out: list[list[int]] = []
    for i in ids:
        if out:
            j = out[-1][-1]
            h = g.y1[j] - g.y0[j]
            if (abs(g.base[i] - g.base[j]) <= 0.2 * h
                    and -0.5 * h <= g.x0[i] - g.x1[j] <= SPACE * h):
                out[-1].append(i)
                continue
        out.append([i])
    return out


SPACE = 0.15            # x font height: a wider gap ends a word


def _glyph_text(g: Glyphs, i: int) -> str:
    text = g.text[i]
    if (not text.strip() or text.startswith("(cid:")
            or any(0xE000 <= ord(c) <= 0xF8FF for c in text)
            or "�" in text):
        return mathtex.char_of(g.fonts[g.font[i]], g.name[i])
    return text


def cell_text(g: Glyphs, cell: list[list[int]]) -> str:
    """A cell's words line by line, each line left to right, separated by
    a space; a cell of one line with mathematics in it as a formula with
    its scripts."""
    formula = _formula_cell(g, [i for w in cell for i in w])
    if formula is not None:
        return formula
    lines: list[list[list[int]]] = []
    for w in sorted(cell, key=lambda w: g.base[w[0]]):
        h = g.y1[w[0]] - g.y0[w[0]]
        if lines and g.base[w[0]] - g.base[lines[-1][0][0]] <= 0.5 * h:
            lines[-1].append(w)
        else:
            lines.append([w])
    words_ = [w for ln in lines
              for w in sorted(ln, key=lambda w: min(g.x0[i] for i in w))]
    return " ".join(t for t in (_word_text(g, w) for w in words_) if t)


def _formula_cell(g: Glyphs, ids: list[int]) -> str | None:
    """One line of mathematics, or None when the cell has no mathematics,
    more than one line, or words of prose."""
    ids = [i for i in ids if g.text[i].strip()]
    if not ids or not any(mathtex.is_math(g, i)
                          and g.name[i] not in mathtex.CHARS for i in ids):
        return None
    tall = max(g.y1[i] - g.y0[i] for i in ids)
    mids = [(g.y0[i] + g.y1[i]) / 2 for i in ids]
    if max(mids) - min(mids) > 0.8 * tall:
        return None
    ids.sort(key=lambda i: g.x0[i])
    main = max(g.size[i] for i in ids)
    prose = set()
    k = 0
    while k < len(ids):                 # words of two text-font letters
        j = k
        while (j < len(ids) and not mathtex.is_math(g, ids[j])
               and g.text[ids[j]].isalpha() and g.size[ids[j]] >= main * 0.95
               and (j == k or g.x0[ids[j]] - g.x1[ids[j - 1]]
                    <= SPACE * tall)):
            j += 1
        if j - k >= 2:
            prose.update(ids[k:j])
        k = max(j, k + 1)
    if prose:
        return None                     # words with a sign among them
    out, run = [], []
    for i in ids + [None]:
        if i is not None and i not in prose:
            run.append(i)
            continue
        if run:
            latex = mathtex.to_latex(g, run)
            out.append("\\(" + latex + "\\)" if latex else "")
            run = []
        if i is not None:
            if out and out[-1] and not out[-1].endswith("\\)") and \
                    g.x0[i] - g.x1[prev] <= SPACE * tall:
                out[-1] += mathpix.escape(g.text[i])
            else:
                out.append(mathpix.escape(g.text[i]))
            prev = i
    return " ".join(t for t in out if t)


def _word_text(g: Glyphs, ids: list[int]) -> str:
    """A word's glyphs: runs in a mathematics font as `\\(...\\)`, the
    rest as text."""
    ids = sorted(ids, key=lambda i: (g.x0[i], g.y0[i]))
    out, run = [], []

    def flush() -> None:
        if run:
            latex = mathtex.to_latex(g, run)
            if latex and "�" not in latex:
                out.append("\\(" + latex + "\\)")
            else:
                out.append(mathpix.escape("".join(_glyph_text(g, i)
                                                  for i in run)))
            run.clear()

    for i in ids:
        if not g.text[i].strip() and g.name[i] not in mathtex.CHARS:
            continue
        if mathtex.is_math(g, i) and g.name[i] not in mathtex.CHARS:
            run.append(i)
        else:
            flush()
            out.append(mathpix.escape(_glyph_text(g, i)))
    flush()
    return "".join(out).strip()


def _box(ln: dict) -> tuple[float, float, float, float]:
    r = ln["region"]
    return (r["top_left_x"], r["top_left_y"],
            r["top_left_x"] + r["width"], r["top_left_y"] + r["height"])


def _inside(box, x0, y0, x1, y1) -> float:
    w = max(0.0, min(box[2], x1) - max(box[0], x0))
    h = max(0.0, min(box[3], y1) - max(box[1], y0))
    area = (box[2] - box[0]) * (box[3] - box[1])
    return w * h / area if area else 0.0


def process(page: dict, record, own: list[int]):
    from . import unpack
    g, rules = unpack(record)
    if not GRID:
        return []
    posts_ = getattr(record, "posts", None)
    found = [(rows, columns, posts, rows, True)
             for rows, columns, posts in grids(rules, posts_)]
    every = words(g)
    if OPEN:
        found += open_tables(g, every, rules, posts_, page.get("page_width")
                             or 0)
    if POSTS:
        # a ruled or open table may have a column rule or two
        found += apart(found, post_tables(g, every, rules, posts_))
    if UNRULED:
        # running heads and folios are page furniture, never a table
        found += unruled_tables(g, [(c[0], r[0], c[-1], r[-1])
                                    for r, c, *_ in found] + [
            _box(ln) for ln in page["lines"] if ln["type"] == "page_info"],
            rules)
    if not found:
        return []
    lines = page["lines"]
    number = max((ln.get("line", 0) for ln in lines), default=0)
    patches: list = []
    taken: set[str] = set()
    for rows, columns, posts, rules_y, heads in found:
        n_cols = len(columns) - 1
        rows = list(rows)
        if (_filled(g, every, rows, columns, posts) < FILLED
                or _tall(g, every, rows, columns)):
            continue                    # a frame or a chart, not a table
        pitch = sorted(b - a for a, b in zip(rows, rows[1:]))[(len(rows) - 1) // 2]
        # a row of column heads right above the top rule, of foots under
        # the bottom one, when it fills the columns as a row does; a table
        # of rules only takes no foots (its caption stands there)
        # a table without rules has no edge to look beyond
        for edge in (() if heads is None else (0, -1) if heads else (0,)):
            band = ([rows[0] - pitch, rows[0]] if edge == 0
                    else [rows[-1], rows[-1] + pitch])
            if _filled(g, every, band, columns, []) >= HEADS:
                rows = [band[0]] + rows if edge == 0 else rows + [band[1]]
        x0, x1, y0, y1 = columns[0], columns[-1], rows[0], rows[-1]
        inside = [ln for ln in lines if "parent_id" not in ln
                  and ln["id"] not in taken
                  and _inside(_box(ln), x0, y0, x1, y1) >= INSIDE]
        if not inside or heads is None and sum(
                ln["type"] in ("math", "equation_number") for ln in inside
                ) >= MATH * len(inside):
            continue                    # a display: a matrix, an array
        n_rows = len(rows) - 1
        cells = _cells(g, every, rows, columns)
        ruled = [any(abs(y - r) <= TOUCH for r in rules_y) for y in rows]
        texts: dict[tuple[int, int], tuple[int, str]] = {}
        body = []
        for r in range(n_rows):
            row = []
            for a, b in spans(columns, posts, rows[r], rows[r + 1]):
                text = cell_text(g, [w for c in range(a, b)
                                     for w in cells.get((r, c), [])])
                if text:
                    texts[(r, a)] = (b, text)
                row.append(text if b - a == 1 else
                           f"\\multicolumn{{{b - a}}}{{|l|}}{{{text}}}")
            body.append(("\\hline " if ruled[r] else "")
                        + " & ".join(row) + " \\\\")
        tabular = ("\\begin{tabular}{|" + "l|" * n_cols + "}\n"
                   + "\n".join(body)
                   + ("\n\\hline" if ruled[-1] else "")
                   + "\n\\end{tabular}")
        first = inside[0]
        table_id = first["id"]
        size = first.get("font_size", 0)
        kids: list[dict] = []

        def kid(kind: str, box, text: str = "", **cell) -> dict:
            nonlocal number
            number += 1
            ln = mathpix.line(table_id, page["page"], number, kind, text,
                              text, tuple(round(v) for v in box), size,
                              conversion_output=False, parent_id=table_id)
            ln.update(cell)
            return ln

        for c in range(n_cols):
            kids.append(kid("table_column",
                            (columns[c], y0, columns[c + 1], y1)))
        for r in range(n_rows):
            kids.append(kid("table_row", (x0, rows[r], x1, rows[r + 1])))
        for (r, c), (end, text) in sorted(texts.items()):
            kids.append(kid("simple_cell",
                            (columns[c], rows[r], columns[end],
                             rows[r + 1]), text, cell_row=r, cell_column=c))
        table = mathpix.line(table_id, page["page"], first["line"], "table",
                             tabular, "\n\n" + tabular,
                             (round(x0), round(y0), round(x1), round(y1)),
                             size)
        table["id"] = table_id
        tail = {k: table.pop(k) for k in ("text", "text_display",
                                          "confidence", "confidence_rate")}
        table["children_ids"] = [k["id"] for k in kids]
        table.update(tail)
        patches.append((table_id, [table] + kids))
        gone = [ln["id"] for ln in inside[1:]] + [
            k for ln in inside for k in ln.get("children_ids", [])]
        patches += [(line_id, None) for line_id in gone]
        taken.update(ln["id"] for ln in inside)
    return patches
