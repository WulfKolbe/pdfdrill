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
    done = 0
    for head, members in groups.items():
        members = sorted(set(members) | {head})
        hp = placed[head]
        if hp.box is None or not hp.comps:
            continue
        parts = split_into(hp.comps, len(members))
        if parts is None:
            continue
        from .inkbox import union_box
        for idx, part in zip(members, parts):
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


def assemble_page(md: str, png: Optional[Path], page_no: int) -> dict:
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

    from . import inkbox
    gray = inkbox.load_gray(Path(png))
    h, w = gray.shape
    comps = inkbox.components(gray)
    lh = inkbox.median_height(comps)
    comps = [b for b in comps
             if max(b[2] - b[0], b[3] - b[1]) >= inkbox.SPECK * lh]
    comps = inkbox.drop_scan_edges(comps, w, h)
    rows = inkbox.rows(comps, max_height=TALL_DROP * lh)
    rows = inkbox.drop_speck_rows(rows, lh)
    rows = inkbox.prune_row_outliers(rows, lh)

    placed = align(items, rows, page_width=w)
    split_numbers(placed, items, page_width=w, line_height=lh)
    split_furniture(placed, items, page_width=w)
    split_cells(placed, items, page_width=w)
    close_containers(placed, items)
    missing = sum(1 for p in placed if p.box is None)
    return {
        "page": page_no,
        "page_width": int(w),
        "page_height": int(h),
        "image_id": "",
        "lines": page_lines(placed, page_no),
        "parse_status": "parsed",
        "fallback_count": missing,
        "page_confidence": None,
        "languages_detected": [],
    }


def assemble(pages: Iterable[tuple[int, str, Optional[Path]]], *,
             prompt_name: str = "", model: str = "",
             md_text: str = "") -> dict:
    """The whole document: (page_no, markdown, png) triples -> a lines.json.

    FREE AND OFFLINE. This is the function every test calls, and the reason
    this lane can be verified at all without spending from a metered account.
    """
    out_pages = []
    for page_no, md, png in pages:
        out_pages.append(assemble_page(md, png, page_no))
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
                blob_dir: Optional[Path] = None) -> dict:
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
    if not force and is_gemma_lines(targets["lines.json"]):
        return {"status": "cached", "files": targets, "usage": {},
                "provider": ""}

    work = (Path(blob_dir) if blob_dir else pdf_path.parent) / "gemmaocr"
    renders = pdf_reading.rasterize(pdf_path, work / "pages",
                                    pages=list(pages) if pages else None,
                                    dpi=DPI, gray=True)
    by_no = {pdf_reading.page_of(p): p for p in renders}
    triples: list[tuple[int, str, Optional[Path]]] = []
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "pages": 0}
    provider = ""
    run_id = ""
    if blob_dir is not None:
        from . import callog
        run_id = callog.new_run_id("gemmaocr")
        callog.open_run(blob_dir, "gemmaocr", script=__name__)
    for n in sorted(k for k in by_no if k is not None):
        md_path = work / f"page-{n:04d}.md"
        if md_path.is_file() and not force:
            md = md_path.read_text(encoding="utf-8")       # a resumed run
        else:
            got = read_page(by_no[n], work / "strips", blob_dir=blob_dir,
                            run_id=run_id, strips=strips)
            md = got["markdown"]
            md_path.write_text(md, encoding="utf-8")
            provider = got["provider"] or provider
            usage["prompt_tokens"] += got["usage"]["prompt_tokens"]
            usage["completion_tokens"] += got["usage"]["completion_tokens"]
            usage["pages"] += 1
        triples.append((n, md, by_no[n]))

    doc = assemble(triples, prompt_name="page-ocr-markdown", model=provider)
    write_lines(doc, Path(targets["lines.json"]))
    Path(targets["md"]).write_text(markdown(doc), encoding="utf-8")
    if blob_dir is not None and run_id:
        from . import callog
        callog.close_run(blob_dir, run_id, calls=usage["pages"],
                         outcome="read", extra=usage)
    return {"status": "read", "files": targets, "usage": usage,
            "provider": provider}


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
