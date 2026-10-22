r"""A model-read page -> a MathPix-shaped `lines.json`, the same lane shape as
`mathpix_client`.

WHY IT MIRRORS THE MATHPIX LANE SO CLOSELY
------------------------------------------
Two readers that produce the same artefact under different names are two
pipelines, and everything downstream has to learn both. So this module is
deliberately the same SHAPE as `mathpix_client`:

    mathpix_client.expected_outputs(pdf)  ->  gemma_reader.expected_outputs(pdf)
    mathpix_client.upload_preflight(...)  ->  gemma_reader.read_preflight(...)
    mathpix_client.fetch_mathpix(pdf)     ->  gemma_reader.fetch_gemma(pdf)
      {"status": cached|downloaded, "files": {...}}   same dict, same keys

and it writes the SAME file names beside the PDF (`<base>.lines.json`,
`<base>.md`) with the SAME per-line and per-page keys, so `model`, `inspect`,
every projector and the whole prerequisite graph read it without knowing which
reader ran. The one field that differs is the one that must: top-level
`source`, which says who read the page. `_is_mathpix_lines` still answers "was
this bought from MathPix?" with no, and that is correct — it is the question
four money-spending call sites ask.

THE THREE STAGES, AND WHY ONLY ONE OF THEM COSTS MONEY
------------------------------------------------------
    render   gs at >=400 dpi (`pdf_reading.rasterize`) — free, offline
    read     the page image -> Markdown, via `vision_router` — PAID
    assemble Markdown + the page's ink -> lines.json — free, offline

`assemble` is a separate public function for one reason: a 10 EUR account with
0.28 EUR already spent cannot fund a verification loop. Keeping the assembler
pure (Markdown in, ink in, lines.json out) means every change to the geometry,
the types or the container shape is testable against readings already on disk —
including against MathPix's own reading of the same pages, which is what
`linescmp` scores. The paid stage is the thin one, and it is declared
`network: true` so `--ensure` names it instead of running it.

GEOMETRY: WHAT A BOX IS MADE OF
-------------------------------
The model returns no coordinates, so every box here is measured from the page's
own ink and assigned by ORDER: the items are the printed lines in reading
order, the ink rows are the printed rows in reading order, and the alignment is
a monotone matching between them. Each box therefore carries `geometry` saying
how it was arrived at — `ink` when it is the tight box of the row's components,
`ink-split` when a shared row was divided, `ink-span` when one item consumed
several rows, `estimated` when the alignment had to interpolate, `container`
for a parent's union. A consumer that needs to know how much to trust a box can
read that field; `pdfdrill` itself ignores it, as it ignores MathPix's
`confidence`.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional, Sequence

from . import pagemd
from .pagemd import Item

#: The reader's name in the artefact. `_TYPED_GEOMETRY_SOURCES` admits it:
#: these readings carry MathPix's line types in PAGE PIXELS, which is the pair
#: of properties that gate asks about.
SOURCE = "gemma4-ink-yolo"

#: The render resolution. `pdf_reading.rasterize` floors every request at
#: `RASTER_MIN_DPI` (400) anyway; naming it here keeps the number that the
#: regions are expressed in visible at the top of the file, because a region
#: is meaningless without the page pixel size it was measured in.
DPI = 400

#: A text item may consume at most this many ink rows. One is the rule (the
#: prompt asks for one output line per printed line); two covers a model that
#: joined a hyphenated pair. A display equation may consume many more, because
#: MathPix groups a multi-line display into ONE `math` line and the prompt asks
#: the model to do the same with `\begin{aligned}`.
MAX_ROWS_PROSE = 2
MAX_ROWS_BLOCK = 12

#: A component taller than this many line heights is not a printed line — it
#: is the scan: a gutter band, a fold, the edge of the platen. It is kept out
#: of the row grouping (see `inkbox.rows`), where one such component collapses
#: a whole page into a single row.
TALL_DROP = 6.0

def _owns_no_ink(it: Item) -> bool:
    """A CONTAINER owns no ink of its own: its box is the union of its
    children's. Tested by `children` and not by type, because MathPix uses the
    container shape for four different types (`footnote`, `section_header`,
    `title`, `authors`) and a container that is allowed to consume an ink row
    steals it from the line that is actually printed there — which shifts
    every box after it on the page. That cost 7 text lines and 4 displays the
    first time this was keyed off a type list.
    """
    return bool(it.children)


class ReadRefused(RuntimeError):
    """The read was refused before any paid call — never a partial spend."""


# --------------------------------------------------------------------------- #
#  The lane's file contract — same names, same place, as MathPix
# --------------------------------------------------------------------------- #

def base_name(pdf_path: str | Path) -> str:
    p = str(pdf_path)
    return p[:-4] if p.lower().endswith(".pdf") else p


def expected_outputs(pdf_path: str | Path) -> dict[str, str]:
    """Where this lane's outputs go — the SAME paths MathPix would use.

    One lines.json per document, whoever read it. Two readers writing two
    differently-named readings beside one PDF is how a document ends up with a
    stale one being served (`_stale_or_absent` guards against age, not against
    a sibling), so the lane that runs last owns the file and `source` says who
    that was. A displaced MathPix reading is parked by the caller, exactly as
    `model --reader` already parks one.
    """
    base = base_name(pdf_path)
    return {"lines.json": f"{base}.lines.json", "md": f"{base}.md"}


def is_gemma_lines(path: str | Path) -> bool:
    """True when this lines.json was written by this lane (cheap, no parse)."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            head = fh.read(4096)
    except OSError:
        return False
    return f'"source": "{SOURCE}"' in head or f'"source":"{SOURCE}"' in head


# --------------------------------------------------------------------------- #
#  Preflight — the budget gate
# --------------------------------------------------------------------------- #

#: Measured 2026-10-19 over the 390 pages this reader's provider had billed:
#: 1,711,193 tokens for 0.28 EUR, i.e. 0.000718 EUR per page at 6 strips.
#: Used for the ESTIMATE a preflight prints, never as a billing record — the
#: record is what `callog` writes after the call, from the provider's own
#: `usage`.
EUR_PER_PAGE = 0.000718

#: Refuse rather than start a read whose estimate exceeds the budget the
#: operator declared. `PDFDRILL_OCR_BUDGET_EUR` is the whole account's
#: remaining balance as the operator knows it; absent, no ceiling is enforced
#: and the estimate is still reported. A metered account with a hard stop is
#: not a rate limit: when it empties the function stops, mid-document, and a
#: half-read document is worse than an unread one.
BUDGET_ENV = "PDFDRILL_OCR_BUDGET_EUR"


def read_preflight(pages: Optional[int], *,
                   budget_eur: Optional[float] = None) -> tuple[bool, str, str]:
    """(ok, level, message) before any paid call. Mirrors `upload_preflight`."""
    if budget_eur is None:
        raw = os.environ.get(BUDGET_ENV, "").strip()
        try:
            budget_eur = float(raw) if raw else None
        except ValueError:
            budget_eur = None
    if not pages:
        return True, "warn", ("page count unknown — cost cannot be estimated; "
                              "run `pdfdrill size` first")
    est = pages * EUR_PER_PAGE
    shape = f"{pages} pages, estimated {est:.4f} EUR at {EUR_PER_PAGE:.6f}/page"
    if budget_eur is None:
        return True, "ok", shape + f" (no {BUDGET_ENV} set — no ceiling enforced)"
    if est > budget_eur:
        return False, "refuse", (
            f"{shape}, but {BUDGET_ENV}={budget_eur:.4f} EUR remains. A metered "
            f"account that empties mid-document leaves a half-read document; "
            f"read fewer pages (--pages) or raise the budget.")
    if est > 0.25 * budget_eur:
        return True, "warn", (shape + f" — a quarter or more of the declared "
                              f"{budget_eur:.4f} EUR budget")
    return True, "ok", shape + f" (budget {budget_eur:.4f} EUR)"


# --------------------------------------------------------------------------- #
#  Geometry: items <-> ink rows
# --------------------------------------------------------------------------- #

Box = tuple[int, int, int, int]


@dataclass
class Placed:
    """One item with the box it was given and how that box was arrived at."""
    item: Item
    box: Optional[Box]
    geometry: str
    #: The ink components the item was given, kept because a box is a lossy
    #: summary of them: splitting a shared row (an equation and its number,
    #: a running head and its folio) needs the gap BETWEEN components, which
    #: the union box has already thrown away.
    comps: list[Box] = field(default_factory=list)


def _rel_width(text: str) -> float:
    """A printed line's width, guessed from its content, on a 0..1 scale.

    Not a rendering: a monospace-ish count of the characters that take width,
    with LaTeX markup discounted because `\\left(` is six characters of source
    and one glyph of ink. It only has to be good enough to tell a 10-character
    line from a 70-character one, which is what keeps the alignment from
    sliding when the model merges or splits a line.
    """
    t = re.sub(r"\\[a-zA-Z]+\s*", "x", text)          # a command is one glyph
    t = re.sub(r"[{}$\\]", "", t)
    t = t.replace("\\(", "").replace("\\)", "")
    return min(1.0, len(t) / 72.0)


def _row_box(rows: Sequence[list[Box]], a: int, b: int) -> Box:
    """The union box of rows[a:b]."""
    from .inkbox import union_box
    comps = [c for row in rows[a:b] for c in row]
    u = union_box(comps)
    return u if u is not None else (0, 0, 0, 0)


def _max_rows(it: Item) -> int:
    if it.type in ("math", "diagram", "table", "title"):
        return MAX_ROWS_BLOCK
    return MAX_ROWS_PROSE


def _shared_row_items(items: Sequence[Item]) -> dict[int, int]:
    """Items that share another item's ink row -> that item's index.

    Two sources. The parser already knows one of them — the second and later
    cells of a printed table row carry `shares` — and the other is a run of
    `page_info`, because a folio and a running head are printed at opposite
    ends of ONE row. Both are handled by the same split, since both are "k
    pieces of text printed side by side on one row of ink".
    """
    at = {id(it): i for i, it in enumerate(items)}
    out: dict[int, int] = {}
    head: Optional[int] = None
    for i, it in enumerate(items):
        if it.shares is not None:
            j = at.get(id(it.shares))
            if j is not None:
                out[i] = j
        if it.type != "page_info":
            head = None
            continue
        if head is None:
            head = i
        else:
            out[i] = head
    return out


def align(items: Sequence[Item], rows: Sequence[list[Box]], *,
          page_width: int) -> list[Placed]:
    r"""Assign each ink-bearing item a box, monotonically, by order.

    THE PROBLEM. The model returns N printed lines in reading order; the page's
    ink gives M rows in reading order. N and M agree on most pages and not on
    all: the model joins a hyphenated pair, or splits one display into two, or
    the page has a speck row nobody wrote down. A greedy 1:1 walk is wrong in
    exactly the case that matters — one mismatch early shifts every box after
    it, and a shifted box is not a wrong number, it is a crop of the wrong line
    with nothing in the output saying so. That is the same failure T-0024
    found in `rasterize`, arrived at from the other direction.

    THE METHOD. A dynamic program over (item, row) that minimises
    disagreement, where the moves are: an item takes one row, an item takes k
    consecutive rows (`_max_rows`, so prose cannot swallow a display), or a row
    is skipped as unwritten ink. The cost of a match is the difference between
    how wide the item's text should be and how wide the row's ink actually is,
    which is the only independent signal available without a second OCR pass.

    Items with no ink of their own — a footnote container — are skipped here
    and given the union of their children afterwards.
    """
    # Three kinds of item do NOT consume an ink row of their own:
    #   * a container, which has no ink (its box is its children's union);
    #   * an `equation_number`, printed BESIDE its display on the display's
    #     own row;
    #   * the second and later `page_info` of a page, because the folio and
    #     the running head are printed at opposite ends of ONE row. MathPix
    #     emits two boxes for that row and so do we, by splitting it.
    # Letting any of them consume a row steals it from the line that is
    # actually printed there and shifts every box below it.
    shared = _shared_row_items(items)
    consuming = [i for i, it in enumerate(items)
                 if not _owns_no_ink(it) and it.type != "equation_number"
                 and i not in shared]

    n, m = len(consuming), len(rows)
    if n == 0 or m == 0:
        return [Placed(it, None, "none") for it in items]

    INF = float("inf")
    SKIP_ROW = 0.55           # charging less than this lets rows be dropped
    SPAN = 0.22               # per extra row an item consumes
    # An item that gets NO row. Expensive, but it MUST be possible: a page
    # whose reading has more lines than the page has ink rows is otherwise
    # infeasible, and an infeasible page yielded zero boxes for every line on
    # it — measured as 34 placed boxes out of 311 lines on the 10-page
    # reference document before this move existed. Dearer than SKIP_ROW so
    # the solver drops stray ink before it drops a line somebody read.
    MISS = 1.30

    # best[i][r] = cost of having placed the first i items using the first r rows
    best = [[INF] * (m + 1) for _ in range(n + 1)]
    back: list[list[Optional[tuple[int, int]]]] = [
        [None] * (m + 1) for _ in range(n + 1)]
    best[0][0] = 0.0
    for r in range(1, m + 1):                      # leading ink nobody wrote
        best[0][r] = best[0][r - 1] + SKIP_ROW
        back[0][r] = (0, r - 1)
    for i in range(1, n + 1):
        it = items[consuming[i - 1]]
        want = _rel_width(it.text or it.md)
        kmax = _max_rows(it)
        # this item gets no row at all, before any row is consumed
        best[i][0] = best[i - 1][0] + MISS
        back[i][0] = (i - 1, 0)
        for r in range(1, m + 1):
            # skip this row entirely
            cand = best[i][r - 1] + SKIP_ROW
            arg: Optional[tuple[int, int]] = (i, r - 1)
            if best[i - 1][r] + MISS < cand:       # this item gets no row
                cand, arg = best[i - 1][r] + MISS, (i - 1, r)
            for k in range(1, min(kmax, r) + 1):
                prev = best[i - 1][r - k]
                if prev == INF:
                    continue
                box = _row_box(rows, r - k, r)
                got = (box[2] - box[0]) / page_width if page_width else 0.0
                c = prev + abs(want - got) + SPAN * (k - 1)
                if c < cand:
                    cand, arg = c, (i - 1, r - k)
            best[i][r] = cand
            back[i][r] = arg

    # Walk back and record each item's row span.
    span: dict[int, tuple[int, int]] = {}
    i, r = n, m
    while i > 0 or r > 0:
        step = back[i][r]
        if step is None:                           # unreachable: no rows left
            break
        pi, pr = step
        if pi == i - 1 and r > pr:        # consumed rows pr..r-1
            span[consuming[i - 1]] = (pr, r)
        i, r = pi, pr                     # pi == i-1 and pr == r is a MISS

    out: list[Placed] = []
    for idx, it in enumerate(items):
        if _owns_no_ink(it):
            out.append(Placed(it, None, "container"))
            continue
        if it.type == "equation_number" or idx in shared:
            out.append(Placed(it, None, "pending-split"))
            continue
        sp = span.get(idx)
        if sp is None:
            out.append(Placed(it, None, "none"))
            continue
        a, b = sp
        comps = [c for row in rows[a:b] for c in row]
        box = _row_box(rows, a, b)
        out.append(Placed(it, box, "ink" if b - a == 1 else "ink-span",
                          comps=comps))
    return out


#: How far from its rough ink position a display may be matched to a detector
#: box, in line heights. Six is wide enough to survive the drift a dense page
#: accumulates above the formula and narrow enough that two formulas on one
#: page cannot swap.
ANCHOR_REACH = 6.0


def _row_centre(row: Sequence[Box]) -> float:
    return (min(b[1] for b in row) + max(b[3] for b in row)) / 2.0


def _rows_in(rows: Sequence[list[Box]], box: Box, *,
             slack: float = 0.0) -> tuple[int, int]:
    """The half-open range of rows whose centre lies inside `box`."""
    first = last = None
    for i, row in enumerate(rows):
        cy = _row_centre(row)
        if box[1] - slack <= cy <= box[3] + slack:
            first = i if first is None else first
            last = i + 1
    return (0, 0) if first is None else (first, last)


def _match_displays(disp: Sequence[int], rough: dict[int, Box],
                    boxes: Sequence[Box], line_height: float
                    ) -> dict[int, Box]:
    """Monotone matching of display ITEMS to detector BOXES, by closeness.

    Monotone because both sequences are in reading order, and a matching that
    may cross is a matching that will: the model writes the rows of one
    printed system as separate displays, so several items legitimately sit at
    one box's position and a greedy nearest-box walk pairs them with the
    neighbours' boxes instead.
    """
    n, m = len(disp), len(boxes)
    if not n or not m:
        return {}
    thr = ANCHOR_REACH * max(1.0, line_height)
    best = [[0.0] * (m + 1) for _ in range(n + 1)]
    back: list[list[str]] = [[""] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        rb = rough.get(disp[i - 1])
        cy = (rb[1] + rb[3]) / 2.0 if rb else None
        for j in range(1, m + 1):
            opts = [(best[i - 1][j], "i"), (best[i][j - 1], "j")]
            if cy is not None:
                d = abs(cy - (boxes[j - 1][1] + boxes[j - 1][3]) / 2.0)
                if d < thr:
                    opts.append((best[i - 1][j - 1] + 1.0 - d / thr, "m"))
            else:
                # A display the plain walk could NOT place has no distance to
                # judge, and it is the display that most needs an anchor: a
                # page whose reading has more lines than the page has ink rows
                # leaves its formulas unplaced first, because they are the
                # items allowed to consume several rows. Matching it on
                # monotonicity alone, at half the credit of a measured match,
                # is what lets one row carry three written displays.
                opts.append((best[i - 1][j - 1] + 0.5, "m"))
            best[i][j], back[i][j] = max(opts, key=lambda o: o[0])
    out: dict[int, Box] = {}
    i, j = n, m
    while i > 0 and j > 0:
        step = back[i][j]
        if step == "m":
            out[disp[i - 1]] = boxes[j - 1]
            i -= 1
            j -= 1
        elif step == "i":
            i -= 1
        else:
            j -= 1
    return out


def align_anchored(items: Sequence[Item], rows: Sequence[list[Box]], *,
                   page_width: int, displays: Sequence[Box] = (),
                   line_height: float = 40.0) -> list[Placed]:
    r"""`align`, with the detector's display boxes as fixed points.

    WHY ANCHORS AND NOT A BETTER COST FUNCTION. `align` is one monotone walk
    down the page, so its errors are CUMULATIVE: a single display whose row
    count it guesses wrong shifts every box below it, and the cost function
    cannot tell, because a formula's ink width is not predictable from its
    LaTeX the way a prose line's is. MEASURED on penev_A: 5 of 116 display
    formulas and 3 of 116 equation numbers boxed at IoU >= 0.5 by the ink walk
    alone.

    A detector box is independent evidence of exactly the thing the walk
    guesses. So the displays are matched to those boxes first, and then the
    walk runs only BETWEEN two anchors, over that band's rows alone — which
    bounds every error to the band it happens in. A page with no detector and
    a page whose displays all failed to match both fall back to the plain walk,
    which is why this wraps `align` instead of replacing it.
    """
    placed = align(items, rows, page_width=page_width)
    if not displays or not rows:
        return placed

    disp = [i for i, it in enumerate(items) if it.type == "math"]
    if not disp:
        return placed
    rough = {i: p.box for i, p in enumerate(placed) if p.box is not None}
    matched = _match_displays(disp, rough, list(displays), line_height)
    if not matched:
        return placed

    # Each anchor carries the GROUP of consecutive display items that belong
    # to its box: the model writes a printed system's rows as separate `$$`
    # blocks while the detector boxes the system once.
    dset = set(disp)
    anchors: list[tuple[list[int], Box, tuple[int, int]]] = []
    taken: set[int] = set()
    for k in sorted(matched):
        if k in taken:
            continue
        box = matched[k]
        group = [k]
        # A neighbouring display joins the group when its rough position is
        # inside the box OR when it has no rough position at all: an unplaced
        # display next to an anchored one is a row of the same printed system
        # far more often than it is a formula of its own, and leaving it
        # unplaced is the outcome anchoring exists to avoid.
        j = k - 1
        while (j in dset and j not in matched and j not in taken
               and _groupable(rough.get(j), box, line_height)):
            group.insert(0, j)
            j -= 1
        j = k + 1
        while (j in dset and j not in matched and j not in taken
               and _groupable(rough.get(j), box, line_height)):
            group.append(j)
            j += 1
        taken.update(group)
        span = _rows_in(rows, box, slack=line_height / 2.0)
        anchors.append((group, box, span))

    # Monotone in BOTH sequences or not an anchor: a matching that went
    # backwards would make a segment with a negative row range, and the walk
    # inside it would place boxes above the formula that precedes them.
    kept: list[tuple[list[int], Box, tuple[int, int]]] = []
    last_item = -1
    last_row = 0
    for group, box, span in sorted(anchors, key=lambda a: a[0][0]):
        if span[1] <= span[0] or group[0] <= last_item or span[0] < last_row:
            continue
        kept.append((group, box, span))
        last_item = group[-1]
        last_row = span[1]
    if not kept:
        return placed

    out = list(placed)
    for group, box, span in kept:
        a, b = span
        if len(group) == 1:
            out[group[0]] = Placed(items[group[0]], box, "yolo",
                                   comps=[c for row in rows[a:b] for c in row])
            continue
        # One detector box, several written displays: divide it along the ink
        # rows inside it when the counts agree, and evenly when they do not.
        if b - a == len(group):
            for idx, ri in zip(group, range(a, b)):
                row = rows[ri]
                out[idx] = Placed(items[idx], _row_box(rows, ri, ri + 1),
                                  "yolo-row", comps=list(row))
        else:
            step = (box[3] - box[1]) / float(len(group))
            for n, idx in enumerate(group):
                part = (box[0], box[1] + n * step, box[2],
                        box[1] + (n + 1) * step)
                out[idx] = Placed(items[idx],
                                  (int(part[0]), int(part[1]),
                                   int(part[2]), int(part[3])),
                                  "yolo-even")

    # The bands between the anchors, each walked on its own rows only.
    bounds: list[tuple[int, int, int, int]] = []
    prev_item, prev_row = 0, 0
    for group, _box, (a, b) in kept:
        bounds.append((prev_item, group[0], prev_row, a))
        prev_item, prev_row = group[-1] + 1, b
    bounds.append((prev_item, len(items), prev_row, len(rows)))

    for i0, i1, r0, r1 in bounds:
        if i1 <= i0:
            continue
        seg_items = list(items[i0:i1])
        seg_rows = list(rows[r0:r1])
        if not seg_rows:
            for off, it in enumerate(seg_items):
                out[i0 + off] = Placed(it, None,
                                       "container" if _owns_no_ink(it) else "none")
            continue
        for off, p in enumerate(align(seg_items, seg_rows,
                                      page_width=page_width)):
            out[i0 + off] = p
    return out


def _inside_y(box: Optional[Box], outer: Box, line_height: float) -> bool:
    if box is None:
        return False
    cy = (box[1] + box[3]) / 2.0
    return outer[1] - line_height / 2.0 <= cy <= outer[3] + line_height / 2.0


def _groupable(box: Optional[Box], outer: Box, line_height: float) -> bool:
    """`_inside_y`, and also true for an item the walk never placed."""
    return box is None or _inside_y(box, outer, line_height)


def split_numbers(placed: list[Placed], items: Sequence[Item], *,
                  page_width: int, line_height: float = 40.0) -> int:
    r"""Give each `equation_number` its own box, cut out of its display's row.

    The number is printed BESIDE the display, at one margin. Its box is the
    display's outermost component group on that side, and the display's box
    shrinks to exclude it. Doing this here rather than leaving the number
    boxless is what lets `eqnums` and T-0024's splitter find it: a number with
    no region is a number no crop can show and no measurement can reach.

    Returns how many numbers were placed.
    """
    from .inkbox import union_box
    placed_n = 0
    where = {id(p.item): p for p in placed}
    for p in placed:
        it = p.item
        if it.type != "equation_number" or it.numbers is None:
            continue
        host = where.get(id(it.numbers))
        if host is None or host.item.type != "math" or not host.comps:
            continue
        comps = sorted(host.comps, key=lambda b: b[0])
        if len(comps) < 2:
            continue
        # THE NUMBER IS THE CLUSTER ACROSS THE WIDEST GAP, not a fixed slab of
        # the host's box. Measured against MathPix on the reference pages: its
        # number boxes are 3.6-3.7% of page width and ONE line tall, while the
        # display they sit beside is 27-54% wide and may be six lines tall. A
        # geometric fraction of the host therefore misses on both axes at
        # once, which is why the first version of this scored 1 of 51.
        gaps = [(comps[i + 1][0] - comps[i][2], i)
                for i in range(len(comps) - 1)]
        gap, at = max(gaps)
        # A gap has to be a real separation and not inter-word space. The
        # yardstick is the page's own LINE HEIGHT, not a share of page width:
        # measured against MathPix, the margin between a number and its
        # display runs from 70 px to 204 px on pages whose width is the same
        # 1,952 — 3.6% to 10% — so a page-width threshold either misses the
        # tight ones (23 of 51 missed at 4%) or starts cutting displays apart.
        # One line height sits above every word space and below every margin.
        if gap < max(1.0 * line_height, 0.02 * page_width):
            continue
        left = comps[:at + 1]
        right = comps[at + 1:]
        # The number is the SMALLER cluster — a display is wider than its
        # label on either convention (left margin in the 19th century, right
        # in modern practice), so which side it is on need not be assumed.
        lb, rb = union_box(left), union_box(right)
        if lb is None or rb is None:
            continue
        num_side, host_side = ((left, right) if (lb[2] - lb[0]) <= (rb[2] - rb[0])
                               else (right, left))
        nb = union_box(num_side)
        hb = union_box(host_side)
        if nb is None or hb is None:
            continue
        # A number is narrow. Requiring that is what stops the widest gap
        # INSIDE a display (an `aligned` block's column separation can exceed
        # a line height) from being read as the margin and half the equation
        # from being handed to the number.
        if (nb[2] - nb[0]) > 0.12 * page_width:
            continue
        p.box, p.comps, p.geometry = nb, list(num_side), "ink-split"
        host.box, host.comps = hb, list(host_side)
        host.geometry = "ink-split"
        placed_n += 1
    return placed_n


def split_into(comps: Sequence[Box], k: int) -> Optional[list[list[Box]]]:
    """Cut one row's components into `k` left-to-right clusters.

    The cuts go at the `k-1` WIDEST gaps. That is the whole method, and it is
    the right one for a printed row: the space between two cells of a table,
    or between a folio and a running head, is by construction wider than the
    space between two words inside either of them — a compositor sets it that
    way so a reader can tell the columns apart.
    """
    if k <= 0 or len(comps) < k:
        return None
    cs = sorted(comps, key=lambda b: b[0])
    if k == 1:
        return [cs]
    gaps = sorted(((cs[i + 1][0] - cs[i][2], i) for i in range(len(cs) - 1)),
                  reverse=True)
    cuts = sorted(i for _g, i in gaps[:k - 1])
    out, start = [], 0
    for c in cuts:
        out.append(cs[start:c + 1])
        start = c + 1
    out.append(cs[start:])
    return out if all(out) else None


def split_cells(placed: list[Placed], items: Sequence[Item], *,
                page_width: int) -> int:
    r"""Each table cell its own box, cut out of its printed row.

    MEASURED: MathPix gives every `simple_cell` a tight box — 15 of them on
    one reference page, 2,364 on another document — and those boxes are where
    a table's geometry lives. A reader that boxes the ROW and not the cells
    has no geometry for any cell in any table it reads, which is 82% of the
    lines on a table-heavy document.
    """
    groups: dict[int, list[int]] = {}
    shared = _shared_row_items(items)
    for idx, it in enumerate(items):
        if it.type != "simple_cell":
            continue
        head = shared.get(idx, idx)
        groups.setdefault(head, []).append(idx)
    from .inkbox import union_box
    done = 0
    for head, members in groups.items():
        members = sorted(set(members) | {head})
        hp = placed[head]
        if hp.box is None or not hp.comps:
            continue
        # SPLIT INTO AS MANY CLUSTERS AS THERE ARE CELLS WITH CONTENT, not as
        # many as there are cells. A printed table row has empty cells — a
        # ditto mark column, a blank — and an empty cell deposits no ink, so
        # asking the row's components for one cluster per cell asks for more
        # clusters than the row has components and the split refuses.
        # Measured on a 14-page document with 2,364 cells: 735 cells were
        # left with no box at all because ONE empty cell in their row made the
        # whole row unsplittable. An empty cell having no box is right; its
        # neighbours losing theirs is not.
        filled = [i for i in members if (placed[i].item.text or "").strip()]
        if not filled:
            continue
        parts = split_into(hp.comps, len(filled))
        if parts is None:
            # Still more cells than clusters: two cells' content merged into
            # one component group, or a cell the model read that is not
            # there. Give what ink there is to the cells in order and leave
            # the rest boxless rather than box them wrongly.
            parts = split_into(hp.comps, min(len(filled), len(hp.comps)))
            if parts is None:
                continue
        for idx, part in zip(filled, parts):
            b = union_box(part)
            if b is None:
                continue
            placed[idx].box = b
            placed[idx].comps = list(part)
            placed[idx].geometry = "ink-split"
        done += 1
    return done


def split_furniture(placed: list[Placed], items: Sequence[Item], *,
                    page_width: int) -> int:
    r"""The folio and the running head, printed at opposite ends of one row.

    MEASURED on both reference readings: MathPix emits TWO `page_info` lines
    per page, one for each, with boxes tens of pixels tall at opposite margins
    — never one box spanning the row. A single spanning box scores zero
    against both of them and, worse, declares the whole top row furniture,
    which is a line of body text wide on a page whose head the model did not
    print.

    The row is cut at its widest internal gap and the pieces handed out left
    to right, in the order the items appear.
    """
    from .inkbox import union_box
    shared = _shared_row_items(items)
    done = 0
    for idx, head in shared.items():
        if items[idx].type != "page_info":
            continue                      # table cells: `split_cells`
        p, hp = placed[idx], placed[head]
        if hp.box is None or len(hp.comps) < 2:
            continue
        comps = sorted(hp.comps, key=lambda b: b[0])
        gaps = [(comps[i + 1][0] - comps[i][2], i)
                for i in range(len(comps) - 1)]
        gap, at = max(gaps)
        if gap < 0.05 * page_width:
            continue
        left, right = comps[:at + 1], comps[at + 1:]
        lb, rb = union_box(left), union_box(right)
        if lb is None or rb is None:
            continue
        # The items are in the order the comment wrote them; the boxes in
        # page order. Pair them up positionally.
        hp.box, hp.comps, hp.geometry = lb, list(left), "ink-split"
        p.box, p.comps, p.geometry = rb, list(right), "ink-split"
        done += 1
    return done


def close_containers(placed: list[Placed], items: Sequence[Item]) -> None:
    """A parent's box is the union of its children's — MathPix's rule."""
    from .inkbox import union_box
    where = {id(p.item): p for p in placed}
    for p in placed:
        if not p.item.children:
            continue
        kids = [where[id(k)].box for k in p.item.children
                if id(k) in where and where[id(k)].box is not None]
        u = union_box([b for b in kids if b is not None])
        if u is not None:
            p.box = u
            p.geometry = "container"


# --------------------------------------------------------------------------- #
#  The writer — MathPix's page and line keys, exactly
# --------------------------------------------------------------------------- #

def _region(box: Optional[Box]) -> dict:
    if box is None:
        return {"top_left_x": 0, "top_left_y": 0, "width": 0, "height": 0}
    x0, y0, x1, y1 = box
    return {"top_left_x": int(x0), "top_left_y": int(y0),
            "width": int(x1 - x0), "height": int(y1 - y0)}


def _cnt(box: Optional[Box]) -> list[list[int]]:
    """MathPix's `cnt`: the region as a 4-point polygon, clockwise from the
    top-left. Carried because readers of a bought reading read `cnt` and not
    `region` (`glyphcensus.region_to_points` takes either), and a reading that
    omits a field those readers use is a reading they silently see as empty."""
    if box is None:
        return []
    x0, y0, x1, y1 = (int(v) for v in box)
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def page_lines(placed: list[Placed], page_no: int) -> list[dict]:
    """The `lines` array of one page, in MathPix's shape."""
    ids = [uuid.uuid4().hex for _ in placed]
    at = {id(p.item): n for n, p in enumerate(placed)}
    out: list[dict] = []
    for n, p in enumerate(placed):
        it = p.item
        rec: dict = {
            "cnt": _cnt(p.box),
            "region": _region(p.box),
            "line": n + 1,
            "column": 0,
            "is_printed": True,
            "is_handwritten": False,
            "id": ids[n],
            "type": it.type,
            # MathPix sets this false for everything that is not flowed text:
            # furniture, an equation number, a container. Measured on both
            # reference readings.
            "conversion_output": it.type not in (
                "page_info", "equation_number", "footnote", "figure_label",
                "diagram", "title"),
            "text": it.text,
            "text_display": pagemd.text_display(it),
            # A model gives no per-line confidence. MathPix's fields are
            # carried as null rather than omitted: a consumer that reads
            # `line["confidence"]` must see None (unknown) and not raise a
            # KeyError, and must not see a number this reader cannot justify.
            "confidence": None,
            "confidence_rate": None,
            "text_confidence": None,
            "layout_confidence": None,
            # Additive, this reader's own: how the box was arrived at.
            "geometry": p.geometry,
        }
        if it.cells:
            rec["cells"] = it.cells
        if it.subtype:
            rec["subtype"] = it.subtype
        if it.children:
            rec["children_ids"] = [ids[at[id(k)]] for k in it.children
                                   if id(k) in at]
        if it.parent is not None and id(it.parent) in at:
            rec["parent_id"] = ids[at[id(it.parent)]]
        out.append(rec)
    return out


def place_by_order(placed: list[Placed], items: Sequence[Item],
                   boxes: Sequence[Box], *, types: Sequence[str],
                   geometry: str) -> int:
    """Give the still-unboxed items of `types` the detector's boxes, in order.

    By ORDER and not by position, because these are the items for which no
    position was derived: an `equation_number` the row split could not cut
    out, a `diagram` the model described rather than transcribed. Both
    sequences are in reading order, so the k-th unboxed one is the k-th box.
    A surplus on either side is left alone rather than forced.
    """
    want = [i for i, it in enumerate(items)
            if it.type in types and placed[i].box is None]
    n = 0
    for i, box in zip(want, boxes):
        placed[i] = Placed(items[i], (int(box[0]), int(box[1]),
                                      int(box[2]), int(box[3])), geometry)
        n += 1
    return n


#: How much of a line's box must lie inside an `abandon` box for the line to be
#: that furniture. Not all of it: the detector's box is drawn around the ink it
#: saw, and a folio's descender or a rule under a running head falls outside.
FURNITURE_SHARE = 0.6

#: …and how near the paper's edge furniture sits.
FURNITURE_BAND = 0.12

#: …and how wide it is. A running head and a folio are SHORT; a line of body
#: text runs the full measure. Measured the other way round first: with the
#: band and the detector's word alone, 128 lines were retyped on penev_A and
#: the score fell from 2,696 of 3,080 reference lines to 2,617 — 79 lines of
#: body text, typed as furniture and dropped from the Markdown, because the top
#: twelfth of a scanned page holds the first body line as often as a head.
FURNITURE_WIDTH = 0.55

#: …and how tall the detector's own box is. `abandon` drawn over a whole block
#: is the detector mislabelling a block, not a page carrying a four-line
#: running head.
FURNITURE_LINES = 2.2


def retype_furniture(placed: list[Placed], boxes: Sequence[Box], *,
                     page_height: int, page_width: int = 0,
                     line_height: float = 0.0) -> int:
    """Retype a `text` line that is the page's own furniture as `page_info`.

    Reading ONE PRINTED PAGE, the model has no document to count pages in, so
    it writes the folio as a bare line — `23`, or `CHAPTER 2  23` — instead of
    the `<!-- page N | Head -->` comment the whole-document prompt asks for.
    Those land as `text`, and a running head is not a sentence: the
    transclusion gate, the reading order and every projection treat it as one.
    MEASURED on penev_A: 15 `page_info` lines against MathPix's 98.

    The detector already names them (`abandon`) and the class was parsed and
    unused. FOUR conditions, and the conjunction is the whole of it: the
    detector's word, the margin band, a short line, and a detector box no
    taller than a line or two. Each alone is dangerous in the same direction —
    `markdown()` drops a `page_info` line, so retyping a body paragraph deletes
    its prose from the output, and a deletion is not visible in the result.

    Returns how many lines were retyped.
    """
    if not boxes or page_height <= 0:
        return 0
    top = FURNITURE_BAND * page_height
    bottom = (1.0 - FURNITURE_BAND) * page_height
    max_w = FURNITURE_WIDTH * page_width if page_width else None
    max_h = FURNITURE_LINES * line_height if line_height else None
    n = 0
    for p in placed:
        if p.box is None or p.item.type != "text":
            continue
        x0, y0, x1, y1 = p.box
        if not (y1 <= top or y0 >= bottom):
            continue                       # not in a margin band
        if max_w is not None and (x1 - x0) > max_w:
            continue                       # a full-measure line is body text
        area = max(1.0, (x1 - x0) * (y1 - y0))
        for b in boxes:
            if max_h is not None and (b[3] - b[1]) > max_h:
                continue                   # the detector boxed a block
            ix = max(0.0, min(x1, b[2]) - max(x0, b[0]))
            iy = max(0.0, min(y1, b[3]) - max(y0, b[1]))
            if ix * iy / area >= FURNITURE_SHARE:
                p.item.type = "page_info"
                n += 1
                break
    return n


def emit_figures(placed: list[Placed], boxes: Sequence[Box]) -> int:
    """Add a `diagram` line for each detected figure nobody wrote down.

    `pagemd` already makes a `diagram` item when the model DESCRIBES a figure
    (`[Graph ...]`, `[Figure ...]`), and those are matched to detector boxes by
    `place_by_order`. What is left over is a figure the model passed over in
    silence — which, once the figure is whitened before the read, is the
    common case rather than the exception: there is nothing on the page for it
    to transcribe.

    MEASURED on penev_A: 1 of 14 `diagram` and 2 of 11 `chart` reference lines
    boxed without this, against 13 and 11 by the reading this lane is being
    held to. A figure the detector found and the reading does not mention is a
    hole in the page that nothing downstream can see — `inspect` draws no box
    there and `model` builds no object, so the page looks complete and is not.

    Inserted IN READING ORDER rather than appended, because `line` numbers a
    page top to bottom and a reader turning to a figure listed after the
    footnotes is being told something false. Insertion is safe precisely
    because every cross-reference between items is an object reference and
    not an index.
    """
    added = 0
    for box in boxes:
        item = Item("diagram", "", md="", described=True)
        entry = Placed(item, (int(box[0]), int(box[1]),
                              int(box[2]), int(box[3])), "yolo")
        at = len(placed)
        for n, p in enumerate(placed):
            if p.box is not None and p.box[1] > box[1]:
                at = n
                break
        placed.insert(at, entry)
        added += 1
    return added


def _whiten_array(gray, boxes: Sequence[Box], *, pad: int = 2):
    """A copy of `gray` with `boxes` filled with paper white.

    The ink alignment runs on THIS and not on the page: a figure is a large
    connected mass of ink belonging to no printed line, and the row banding —
    which must consume rows monotonically — hands it to whatever text line is
    passing. MEASURED as the cause of the 97x3413 gutter band that collapsed
    a whole Hilbert page to one ink row.
    """
    if not boxes:
        return gray
    out = gray.copy()
    h, w = out.shape
    for x0, y0, x1, y1 in boxes:
        a = max(0, int(y0) - pad)
        b = min(h, int(y1) + pad)
        c = max(0, int(x0) - pad)
        d = min(w, int(x1) + pad)
        if b > a and d > c:
            out[a:b, c:d] = 255
    return out


def assemble_page(md: str, png: Optional[Path], page_no: int, *,
                  dets: Optional[Sequence] = None) -> dict:
    """One page of Markdown + its render -> one `pages[]` entry.

    With no render (`png=None`) the page still gets its lines, with zero
    regions and `geometry: "none"`. That is deliberately not an error: a
    reading whose text is right and whose boxes are missing is still a reading
    `model` can build prose from, and saying so in the field beats refusing the
    whole document because one page failed to rasterize.
    """
    items = pagemd.items(md)
    if png is None or not Path(png).is_file():
        placed = [Placed(it, None, "none") for it in items]
        return {"page": page_no, "page_width": 0, "page_height": 0,
                "image_id": "", "lines": page_lines(placed, page_no),
                "parse_status": "no_render", "fallback_count": len(items),
                "page_confidence": None, "languages_detected": []}

    from . import inkbox, yololayout
    gray = inkbox.load_gray(Path(png))
    h, w = gray.shape
    dets = list(dets or ())
    figures = yololayout.figure_boxes(dets) if dets else []
    comps = inkbox.components(_whiten_array(gray, figures))
    lh = inkbox.median_height(comps)
    comps = [b for b in comps
             if max(b[2] - b[0], b[3] - b[1]) >= inkbox.SPECK * lh]
    comps = inkbox.drop_scan_edges(comps, w, h)
    rows = inkbox.rows(comps, max_height=TALL_DROP * lh)
    rows = inkbox.drop_speck_rows(rows, lh)
    rows = inkbox.prune_row_outliers(rows, lh)

    displays = yololayout.display_boxes(dets) if dets else []
    placed = align_anchored(items, rows, page_width=w, displays=displays,
                            line_height=lh)
    split_numbers(placed, items, page_width=w, line_height=lh)
    split_furniture(placed, items, page_width=w)
    split_cells(placed, items, page_width=w)
    if dets:
        # The detector answers for exactly the two it is better at than any
        # row split: a number printed clear of its display, and a figure the
        # model described instead of transcribing.
        place_by_order(placed, items, yololayout.eqnum_boxes(dets),
                       types=("equation_number",), geometry="yolo")
        used = place_by_order(placed, items, figures,
                              types=("diagram", "table", "chart"),
                              geometry="yolo")
    close_containers(placed, items)
    furniture = 0
    if dets:
        emit_figures(placed, figures[used:])
        # LAST, because it changes a line's TYPE and every pass above reads the
        # type: a line retyped before `split_furniture` would be split as
        # furniture twice, and one retyped before `close_containers` would be
        # a container's child of the wrong kind.
        furniture = retype_furniture(placed, yololayout.abandon_boxes(dets),
                                     page_height=h, page_width=w,
                                     line_height=lh)
    missing = sum(1 for p in placed if p.box is None)
    return {
        "page": page_no,
        "page_width": int(w),
        "page_height": int(h),
        "image_id": "",
        "lines": page_lines(placed, page_no),
        "parse_status": "parsed",
        "fallback_count": missing,
        "furniture_retyped": furniture,
        "page_confidence": None,
        "languages_detected": [],
    }


# --------------------------------------------------------------------------- #
#  The geometry-only lane: the OCR path used for nothing but the page's shape
# --------------------------------------------------------------------------- #
#
# A reading has two halves and only one of them costs money. The words come
# from the model; the SHAPE — where the lines are, which of them is a formula,
# which is a running head, which is a figure — comes from the page's own ink
# and from a detector that runs offline. On an install with no reading key the
# second half is still available, and refusing the whole document because the
# first half is not is a worse answer than giving what there is and saying what
# is missing.
#
# What this produces is a lines.json with every field in its place and `text`
# empty: `model` builds a Document from it, `inspect` draws it, `linescmp`
# scores its geometry against a reference. What it must never do is pretend to
# be a reading — hence `source: "yolo-geometry"`, `text_source: "none"` on
# every line, and a `geometry_only` flag on the document that `model` reads.


def geometry_page(png: Optional[Path], page_no: int, *,
                  dets: Optional[Sequence] = None) -> dict:
    """One page's SHAPE, with no words in it.

    The ink gives the rows, the detector gives each row its type, and a figure
    or a table is one object rather than the ink rows its strokes form. A row
    inside no detector box is `text`, which is what an unclassified printed row
    on a page of prose is.
    """
    from . import inkbox, yololayout
    if png is None or not Path(png).is_file():
        return {"page": page_no, "page_width": 0, "page_height": 0,
                "image_id": "", "lines": [], "parse_status": "no_render",
                "fallback_count": 0, "page_confidence": None,
                "languages_detected": []}
    dets = list(dets or ())
    gray = inkbox.load_gray(Path(png))
    h, w = gray.shape
    wholes = [(k, b) for k, b in yololayout.typed_boxes(dets)
              if k in yololayout.WHOLE_BOX_TYPES]
    comps = inkbox.components(_whiten_array(gray, [b for _k, b in wholes]))
    lh = inkbox.median_height(comps)
    comps = [b for b in comps
             if max(b[2] - b[0], b[3] - b[1]) >= inkbox.SPECK * lh]
    comps = inkbox.drop_scan_edges(comps, w, h)
    rows = inkbox.rows(comps, max_height=TALL_DROP * lh)
    rows = inkbox.drop_speck_rows(rows, lh)
    rows = inkbox.prune_row_outliers(rows, lh)

    typed = yololayout.typed_boxes(dets)
    # EVERY LINE USED TO CLAIM `ink-yolo`, DETECTOR OR NOT (an auditing session,
    # finding I). On the untyped half of this lane no detector runs at all —
    # `dets` is empty, every row's type falls back to `text` — and the
    # lines.json still said its geometry came from the ink AND the detector.
    # The `geometry` field is PROVENANCE: it is read to decide whether a box can
    # be trusted as a Formula's extent or is just the ink under a row. Saying
    # `ink-yolo` where no detector looked makes the weaker half of the lane
    # indistinguishable from the stronger one, which is the one thing a
    # provenance field exists to prevent.
    #
    #   yolo      the detector's own box, kept whole (a figure, a table)
    #   ink-yolo  an ink row the detector TYPED (its centre fell in a box)
    #   ink       an ink row and nothing else — type is `text` by default
    parts: list[tuple[str, Box, str]] = [(k, b, "yolo") for k, b in wholes]
    for row in rows:
        box = inkbox.union_box(row)
        if box is None:
            continue
        kind, from_detector = _type_for_row(box, typed)
        parts.append((kind, box, "ink-yolo" if from_detector else "ink"))
    parts.sort(key=lambda kb: (kb[1][1], kb[1][0]))

    placed = [Placed(Item(type=k, text=""), b, g) for k, b, g in parts]
    lines = page_lines(placed, page_no)
    for ln in lines:
        # Said once per line, because a line is what a consumer reads: this
        # one has a box and no words, and nothing downstream may infer the
        # words are empty on the page.
        ln["text_source"] = "none"
    return {"page": page_no, "page_width": int(w), "page_height": int(h),
            "image_id": "", "lines": lines, "parse_status": "geometry_only",
            "fallback_count": 0, "page_confidence": None,
            "languages_detected": []}


def _type_for_row(box: Box, typed: Sequence[tuple[str, Box]]) -> tuple[str, bool]:
    """`(type, came_from_the_detector)` for one ink row.

    The type of the SMALLEST detector box that contains this row's centre, or
    `text`. Smallest, because an equation number sits inside the formula block
    as often as beside it, and the inner box is the one that names what the row
    actually is.

    The second half of the answer is what the caller writes into the line's
    `geometry` provenance: `text` because the detector said so and `text`
    because nothing looked are not the same claim.
    """
    cx = (box[0] + box[2]) / 2.0
    cy = (box[1] + box[3]) / 2.0
    best: Optional[tuple[float, str]] = None
    for kind, b in typed:
        if b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
            area = max(1.0, (b[2] - b[0]) * (b[3] - b[1]))
            if best is None or area < best[0]:
                best = (area, kind)
    return (best[1], True) if best else ("text", False)


def assemble_geometry(pages: Iterable[tuple[int, Optional[Path], Sequence]], *,
                      detector: str = "") -> dict:
    """The whole document's shape — the geometry-only counterpart of
    `assemble`."""
    out = {
        # `source` NAMES THE READER, so it may not name a half that did not run.
        # It was `yolo-geometry` unconditionally — on the untyped lane, over a
        # document whose own lane line said no detector was available (finding I,
        # second half). Set below, once the pages are in and the provenance of
        # the lines says which halves actually contributed.
        "source": "yolo-geometry",
        "geometry_only": True,
        "ocr": {"lane": "geometry", "detector": detector,
                "words": "NOT READ — this document's lines carry a box and no "
                         "text. `pdfdrill gemmaocr <pdf>` reads the words "
                         "(METERED); this lane never spends."},
        "pages": [],
    }
    for page_no, png, dets in pages:
        out["pages"].append(geometry_page(png, page_no, dets=dets))
    # WHICH HALF RAN, said once for the document, from the lines themselves
    # rather than from `detector` — the detector can be installed and still
    # have produced nothing for these pages, and the head may not promise types
    # the pages do not carry (finding I).
    kinds = {ln.get("geometry") for pg in out["pages"]
             for ln in (pg.get("lines") or [])}
    out["ocr"]["types"] = (
        "from the layout detector" if kinds & {"yolo", "ink-yolo"} else
        "NONE — no detector box reached these pages, so every line's type is "
        "the `text` default, not a measurement. Set PDFDRILL_YOLO_PYTHON for "
        "the typed half of this lane.")
    out["ocr"]["geometry_kinds"] = sorted(k for k in kinds if k)
    # The ink always runs (it is the lane's floor); the detector may not have.
    if not (kinds & {"yolo", "ink-yolo"}):
        out["source"] = "ink-geometry"
    return out


def assemble(pages: Iterable[tuple[int, str, Optional[Path]]], *,
             prompt_name: str = "", model: str = "",
             md_text: str = "") -> dict:
    """The whole document: (page_no, markdown, png) triples -> a lines.json.

    FREE AND OFFLINE. This is the function every test calls, and the reason
    this lane can be verified at all without spending from a metered account.
    """
    out_pages = []
    for entry in pages:
        # (page, markdown, png) or (page, markdown, png, detections). The
        # three-element form is what every test and every caller without a
        # detector passes, and it must keep working unchanged.
        page_no, md, png = entry[0], entry[1], entry[2]
        dets = entry[3] if len(entry) > 3 else None
        out_pages.append(assemble_page(md, png, page_no, dets=dets))
    # `source` FIRST, and this is a contract and not a preference.
    # `commands._lines_source` is the cheap reader every routing decision
    # uses, and it searches only the first 8,192 bytes — "both producers emit
    # `source` near the top". A reading that declares its producer at the END
    # of a 1.5 MB file declares it to nobody: measured, the lane's own cache
    # check ("is this already our reading?") missed and the command tried to
    # buy a reading that was already on disk.
    doc = {
        "source": SOURCE,
        "ocr": {
            "reader": "pdfdrill.gemma_reader",
            "prompt": prompt_name,
            "model": model,
            "dpi": DPI,
            "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "pages": out_pages,
    }
    return doc


# --------------------------------------------------------------------------- #
#  The PAID stage — one page, in strips, to Markdown
# --------------------------------------------------------------------------- #

#: Horizontal strips per page. A host scales each image to a FIXED token
#: budget, so detail comes from cutting the page up, not from rendering it at
#: a higher dpi — six strips for a book page, ten for a dense or tabular one.
STRIPS = 6
#: Strips overlap by this share of a strip's height, so a printed line falling
#: on a cut is whole in one of them. The prompt tells the model the strips
#: overlap and that a line must not be transcribed twice.
STRIP_OVERLAP = 0.06
TASK = "page_ocr_markdown"


def page_strips(png: Path, out_dir: Path, *, strips: int = STRIPS,
                overlap: float = STRIP_OVERLAP) -> list[Path]:
    """Cut one page render into overlapping horizontal strips."""
    from PIL import Image
    out_dir.mkdir(parents=True, exist_ok=True)
    out: list[Path] = []
    with Image.open(png) as im:
        w, h = im.size
        step = h / max(1, strips)
        pad = int(step * overlap)
        for i in range(strips):
            top = max(0, int(i * step) - pad)
            bot = min(h, int((i + 1) * step) + pad)
            dst = out_dir / f"{png.stem}.strip{i:02d}.png"
            im.crop((0, top, w, bot)).save(dst)
            out.append(dst)
    return out


def read_page(png: Path, work: Path, *, blob_dir: Optional[Path] = None,
              run_id: str = "", strips: int = STRIPS,
              max_tokens: int = 8192) -> dict:
    """ONE page image -> Markdown. THE ONLY FUNCTION HERE THAT SPENDS MONEY.

    Routed through `vision_router` so the provider is the router's choice and
    not this module's: `makora` when its key is present (cheapest and fastest
    measured), then `gemma` on Novita, then OpenAI, then the keyless Claude
    delegation. Every call is written to the call log with its prompt
    identity AND its `usage`, so what the page cost is a fact on disk.
    """
    from . import callog, gemma_client, prompts, vision_router
    pieces = page_strips(png, work, strips=strips)
    # The host was measured to hang on four or more images in one request, so
    # a page goes up in batches. This is a property of the host, which is why
    # the limit lives beside its credentials and not here.
    limit = max(1, gemma_client.MAKORA_MAX_IMAGES)
    chunks = [pieces[i:i + limit] for i in range(0, len(pieces), limit)]
    parts: list[str] = []
    total = {"prompt_tokens": 0, "completion_tokens": 0}
    provider = ""
    for chunk in chunks:
        t0 = time.monotonic()
        rec = vision_router.run(TASK, image=str(chunk[0]),
                                images=[str(c) for c in chunk],
                                max_tokens=max_tokens)
        if rec.get("error"):
            raise ReadRefused(str(rec["error"]))
        provider = rec.get("provider") or provider
        parts.append(rec.get("text") or "")
        u = rec.get("usage") or {}
        total["prompt_tokens"] += u.get("prompt_tokens") or 0
        total["completion_tokens"] += u.get("completion_tokens") or 0
        if blob_dir is not None and run_id:
            callog.log_call(
                blob_dir, run_id,
                prompt=prompts.load("page-ocr-markdown"),
                system=gemma_client.SYSTEM_PROMPT,
                reply=rec.get("text") or "", model=rec.get("model", ""),
                max_tokens=max_tokens, finish=rec.get("finish_reason", ""),
                seconds=round(time.monotonic() - t0, 2),
                images=[str(c) for c in chunk], subject=png.name,
                arm=f"{provider}/{strips}strips",
                prompt_name="page-ocr-markdown",
                usage=u,
                eur_per_page=EUR_PER_PAGE / max(1, len(chunks)))
    for f in pieces:                              # the strips are scratch
        try:
            f.unlink()
        except OSError:
            pass
    return {"markdown": "\n\n".join(p.strip() for p in parts if p.strip()),
            "provider": provider, "usage": total}


def fetch_gemma(pdf_path: str | Path, *, pages: Optional[Sequence[int]] = None,
                force: bool = False, strips: int = STRIPS,
                blob_dir: Optional[Path] = None, nup: str = "auto",
                nup_order: str = "column", layout: bool = True,
                allow_download: bool = False, rebuild: bool = False,
                geometry_only: bool = False) -> dict:
    """Read `pdf_path` with the model lane and write the outputs beside it.

    Returns `{"status": "cached"|"read", "files": {...}, "usage": {...}}` —
    the same shape `fetch_mathpix` returns, so a caller handles either lane
    with one branch. IDEMPOTENT in the same way: outputs already on disk cost
    nothing, and `force` is the only way to spend again.
    """
    from . import pdf_reading
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")
    targets = expected_outputs(pdf_path)
    # The geometry-only lane writes the same file under the same name, so a
    # reading already on disk must not be replaced by a shape: the words cost
    # money and the shape is free, and the free thing never overwrites the
    # bought one. It refuses and names what it found.
    if geometry_only and not force and is_gemma_lines(targets["lines.json"]):
        import json as _json
        try:
            head = _json.loads(Path(targets["lines.json"]).read_text(
                encoding="utf-8"))
        except Exception:                                    # noqa: BLE001
            head = {}
        if not head.get("geometry_only"):
            raise ReadRefused(
                f"{Path(targets['lines.json']).name} is a READING (words and "
                f"boxes) and --geometry-only would replace it with boxes "
                f"alone. That reading was paid for. Run `pdfdrill gemmaocr "
                f"{pdf_path.stem} --rebuild` to re-assemble it for free, or "
                f"--force if the shape is really what you want.")
    if not force and not rebuild and is_gemma_lines(targets["lines.json"]):
        return {"status": "cached", "files": targets, "usage": {},
                "provider": ""}

    from . import nup as _nup, sanitize as _san, yololayout as _yolo
    work = (Path(blob_dir) if blob_dir else pdf_path.parent) / "gemmaocr"
    sheets = pdf_reading.rasterize(pdf_path, work / "pages",
                                   pages=list(pages) if pages else None,
                                   dpi=DPI, gray=True)
    sheet_by_no = {pdf_reading.page_of(p): p for p in sheets}

    # STAGE 1 (free): the printed pages. A sheet is not always a page, and a
    # reading made on the sheet cannot be repaired into one made on the page.
    amap = _nup.split([(n, sheet_by_no[n])
                       for n in sorted(k for k in sheet_by_no if k is not None)],
                      work / "printed", order=nup_order, nup=nup)
    identity = _nup.is_identity(amap)
    printed = {int(k): work / "printed" / f"page-{int(k):04d}.png"
               for k in amap}
    shape_kind = next(iter({m["kind"] for m in amap.values()}), "1-up")

    # The per-page Markdown now lives BESIDE the printed page it was read
    # from, so it is archived with the map when the map changes and can never
    # be served against a different picture. A document read before the split
    # existed has it one directory up, and for a 1-up document those are the
    # same pages under the same numbers — so it is carried over rather than
    # bought again. For an n-up document it is NOT carried over, because
    # there the numbers mean something else.
    if identity:
        for n in sorted(printed):
            new = work / "printed" / f"page-{n:04d}.md"
            old = work / f"page-{n:04d}.md"
            if old.is_file() and not new.is_file():
                new.write_text(old.read_text(encoding="utf-8"),
                               encoding="utf-8")

    # STAGE 2 (free, offline): the layout detector, BEFORE the paid read,
    # because what it finds changes the image that is read — a figure is
    # whitened so the model stops transcribing a picture.
    dets: dict[int, list] = {}
    layout_note = ""
    if layout:
        try:
            info = _yolo.detect([printed[n] for n in sorted(printed)],
                                work / "yolo", force=force,
                                allow_download=allow_download)
            dets = {n: _yolo.load_for(work / "yolo", printed[n])
                    for n in sorted(printed)}
            layout_note = (f"layout: {info['ran']} detected, "
                           f"{info['cached']} cached")
        except _yolo.DetectorMissing as exc:
            layout_note = f"layout: SKIPPED — {exc}"

    # STAGE 2b (free): the whole lane, when only the shape was asked for. No
    # strips are cut, no call is made, and nothing can be charged — the branch
    # is here, above the read, so there is no path from `--geometry-only` to a
    # provider call to be reasoned about.
    if geometry_only:
        doc = assemble_geometry(
            ((n, printed[n], dets.get(n) or []) for n in sorted(printed)),
            detector=_yolo.describe())
        doc["ocr"]["nup"] = {"shape": shape_kind, "order": nup_order,
                             "printed_pages": len(amap),
                             "sheets": len({m["sheet"]
                                            for m in amap.values()})}
        if not identity:
            doc = _nup.merge(doc, amap)
        doc = _san.sanitize(doc, {n: sheet_by_no[n] for n in sheet_by_no
                                  if n is not None})
        write_lines(doc, Path(targets["lines.json"]))
        n_lines = sum(len(pg.get("lines") or []) for pg in doc["pages"])
        return {"status": "geometry", "files": {"lines.json":
                                                targets["lines.json"]},
                "usage": {"prompt_tokens": 0, "completion_tokens": 0,
                          "pages": 0},
                "provider": "", "nup": shape_kind,
                "printed_pages": len(amap), "layout": layout_note,
                "lines": n_lines,
                "folios_ascending": [None, 0],
                "sanitize": (doc.get("sanitize") or {}).get("stats") or {}}

    read_from: dict[int, Path] = {}
    for n in sorted(printed):
        figs = _yolo.figure_boxes(dets[n]) if dets.get(n) else []
        if not figs:
            read_from[n] = printed[n]
            continue
        dst = work / "whitened" / f"page-{n:04d}.png"
        if force or not dst.is_file():
            _yolo.whiten(printed[n], figs, dst)
        read_from[n] = dst

    # STAGE 3: the only stage that spends money, and the only place where
    # what it will cost is actually known. The outer preflight in
    # `cmd_gemmaocr` counts the PDF's pages, which is the right number for a
    # 1-up document and a quarter of the right number for penev_A: the paid
    # unit is a PRINTED page. It is also only the pages not already on disk,
    # so a resumed run is charged for what it still has to buy and not for
    # the document.
    pending = [n for n in sorted(printed)
               if force or not (work / "printed" / f"page-{n:04d}.md").is_file()]
    if rebuild and pending:
        # `--rebuild` means "assemble again from what has been bought", and a
        # rebuild that quietly bought the missing pages would be the opposite
        # of what it says. The distinction matters on a fixed prepayment:
        # every change to the geometry, the types or the containers wants to
        # be re-measured, and none of them should cost anything.
        raise ReadRefused(
            f"--rebuild assembles from the Markdown already read, but "
            f"{len(pending)} of {len(printed)} printed pages have none. "
            f"Run without --rebuild to read them (that SPENDS), or with "
            f"--pages to assemble a part of the document.")
    if not rebuild:
        ok_pf, level_pf, msg_pf = read_preflight(len(pending))
        if not ok_pf:
            raise ReadRefused(msg_pf)

    quads: list[tuple[int, str, Optional[Path], list]] = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "pages": 0}
    provider = ""
    run_id = ""
    if blob_dir is not None:
        from . import callog
        run_id = callog.new_run_id("gemmaocr")
        callog.open_run(blob_dir, "gemmaocr", script=__name__)
    for n in sorted(printed):
        md_path = work / "printed" / f"page-{n:04d}.md"
        if md_path.is_file() and not force:
            md = md_path.read_text(encoding="utf-8")       # a resumed run
        else:
            got = read_page(read_from[n], work / "strips", blob_dir=blob_dir,
                            run_id=run_id, strips=strips)
            md = got["markdown"]
            md_path.write_text(md, encoding="utf-8")
            provider = got["provider"] or provider
            usage["prompt_tokens"] += got["usage"]["prompt_tokens"]
            usage["completion_tokens"] += got["usage"]["completion_tokens"]
            usage["pages"] += 1
        quads.append((n, md, printed[n], dets.get(n) or []))

    # STAGE 4 (free): assemble on the printed pages, then back to the sheets
    # the PDF has, because `page` indexes the PDF's own pages everywhere
    # downstream. Then one last pass over the boxes against the SHEET's ink.
    doc = assemble(quads, prompt_name="page-ocr-markdown", model=provider)
    doc["ocr"]["nup"] = {"shape": shape_kind, "order": nup_order,
                         "printed_pages": len(amap),
                         "sheets": len({m["sheet"] for m in amap.values()})}
    if not identity:
        doc = _nup.merge(doc, amap)
    ok, cmp_pairs = _nup.ascending(_nup.folios(doc))
    doc["ocr"]["nup"]["folios_ascending"] = [ok, cmp_pairs]
    doc = _san.sanitize(doc, {n: sheet_by_no[n] for n in sheet_by_no
                              if n is not None})

    write_lines(doc, Path(targets["lines.json"]))
    Path(targets["md"]).write_text(markdown(doc), encoding="utf-8")
    if blob_dir is not None and run_id:
        from . import callog
        callog.close_run(blob_dir, run_id, calls=usage["pages"],
                         outcome="read", extra=usage)
    return {"status": "rebuilt" if rebuild else "read",
            "files": targets, "usage": usage,
            "provider": provider, "nup": shape_kind,
            "printed_pages": len(amap), "layout": layout_note,
            "folios_ascending": [ok, cmp_pairs],
            "furniture": sum(int(pg.get("furniture_retyped") or 0)
                             for pg in doc.get("pages") or []),
            "sanitize": (doc.get("sanitize") or {}).get("stats") or {}}


def write_lines(doc: dict, path: Path) -> Path:
    """Atomically, next to the PDF, under the name MathPix would have used."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, path)
    return path


def markdown(doc: dict) -> str:
    """The document's Markdown, assembled from the pages — MathPix writes one
    `<base>.md` beside the lines.json and so does this lane."""
    parts = []
    for pg in doc.get("pages") or []:
        body = "\n".join(
            l["text_display"] or l["text"]
            for l in pg.get("lines") or []
            if l["type"] not in ("page_info", "equation_number"))
        parts.append(body.strip())
    return "\n\n".join(p for p in parts if p) + "\n"
