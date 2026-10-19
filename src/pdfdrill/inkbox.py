r"""The ink on a rendered page, as connected components with tight boxes.

WHY THIS EXISTS, AND WHY IT IS NOT inkdrill
-------------------------------------------
Every other ink module here CONSUMES inkdrill as a subprocess (`refine.
ink_signature`, `regionink.compare_page`, `inkmeasure.measure`): inkdrill
measures a rendered artefact against a scan and answers "how far apart". That
is a different question from the one a READER asks, which is "where on this
page is the ink, in page pixels, right now" — asked once per page while a
lines.json is being assembled, for a document that has no rendered artefact
yet and may never get one. Shelling out per page would make a reader depend on
a sibling project's install (`refine.inkdrill_root` raises without it) for a
measurement that is a threshold and two projections.

So this module is deliberately small and self-contained: Pillow to decode,
numpy to threshold and label. NOT scipy — `ndimage.label` is the obvious tool
and scipy is not a pdfdrill dependency (`pyproject.toml` has numpy only in the
`layout` extra); a reader that is unavailable until someone installs scipy is a
reader nobody runs. The labelling below is a run-length union-find, which is
what `ndimage.label` does for a binary image, in 60 lines.

WHAT A COMPONENT IS
-------------------
8-connected: a diagonal touch joins. That is the right choice for printed text
at 400 dpi, where an `i`'s dot and its stem are separate components either way
but a thin italic stroke is one component only diagonally. The cost of
8-connectivity is that a broken serif or a scan speck bridging two glyphs
merges them; the cost of 4-connectivity is a stroke cut in half. A box that is
slightly too big is recoverable (it still contains its line); a stroke split
across two lines is not.

Returned boxes are HALF-OPEN in both axes — `(x0, y0, x1, y1)` with x1/y1 one
past the last ink pixel — so `x1 - x0` is the width in pixels and the box
composes with `region()` arithmetic without an off-by-one. The same convention
`pdf_reading` uses for crops.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Sequence

Box = tuple[int, int, int, int]

#: A component whose longer side is below this fraction of the body line
#: height is a speck: a scan mote, a halftone dot, the residue of a cleaned
#: fold. 0.12 keeps an `i` dot (~0.15 of line height at 400 dpi) and drops
#: single-pixel noise. Exposed so a caller can measure with it rather than
#: guess at it.
SPECK = 0.12


def _require_numpy():
    try:
        import numpy as np
    except ImportError as exc:                       # pragma: no cover - env
        raise RuntimeError(
            "ink geometry needs numpy. Install the [layout] extra: "
            "`pip install 'pdfdrill[layout]'`.") from exc
    return np


def load_gray(png: Path):
    """A page image as a 2-D uint8 array (0 = black). Pillow, no mode guessing."""
    np = _require_numpy()
    try:
        from PIL import Image
    except ImportError as exc:                       # pragma: no cover - env
        raise RuntimeError(
            "ink geometry needs Pillow. Install the [imageserver] or [scan] "
            "extra, or `pip install pillow`.") from exc
    with Image.open(png) as im:
        return np.asarray(im.convert("L"))


def otsu(gray) -> int:
    """Otsu's threshold on a uint8 array; ink is `gray <= otsu(gray)`.

    A FIXED threshold is wrong here for the same reason it is wrong in
    `scandrill`: a 19th-century scan's paper sits anywhere from 140 to 250 and
    its ink from 20 to 120, and a document whose paper is darker than another's
    ink is ordinary. Otsu reads the threshold off this page's own histogram.
    """
    np = _require_numpy()
    hist = np.bincount(gray.reshape(-1), minlength=256).astype("float64")
    total = hist.sum()
    if total <= 0:
        return 128
    levels = np.arange(256)
    w0 = np.cumsum(hist)
    w1 = total - w0
    s0 = np.cumsum(hist * levels)
    mu_t = s0[-1]
    valid = (w0 > 0) & (w1 > 0)
    if not valid.any():
        return 128
    m0 = np.where(w0 > 0, s0 / np.maximum(w0, 1), 0.0)
    m1 = np.where(w1 > 0, (mu_t - s0) / np.maximum(w1, 1), 0.0)
    between = w0 * w1 * (m0 - m1) ** 2
    between[~valid] = -1.0
    return int(np.argmax(between))


def _row_runs(mask_row) -> list[tuple[int, int]]:
    """Half-open [start, stop) runs of True in one boolean row."""
    np = _require_numpy()
    if not mask_row.any():
        return []
    edges = np.flatnonzero(np.diff(np.concatenate(
        ([False], mask_row, [False])).astype("int8")))
    return list(zip(edges[0::2].tolist(), edges[1::2].tolist()))


def components(gray, *, threshold: Optional[int] = None,
                min_side: int = 0) -> list[Box]:
    """Bounding boxes of the 8-connected ink components, in page pixels.

    `min_side` drops a component whose longer side is below it — the speck
    filter, in pixels, so the caller decides the yardstick (usually
    `SPECK * line_height`). Boxes come back in reading order (top, then left),
    which is the order every consumer wants and costs one sort.
    """
    np = _require_numpy()
    thr = otsu(gray) if threshold is None else int(threshold)
    mask = gray <= thr
    h, w = mask.shape

    # Union-find over runs. `parent` is indexed by run id; a run's id is its
    # position in `runs`, which is append-only, so ids are stable while rows
    # are still being read.
    parent: list[int] = []

    def find(a: int) -> int:
        root = a
        while parent[root] != root:
            root = parent[root]
        while parent[a] != root:                     # path compression
            parent[a], a = root, parent[a]
        return root

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    # Per run: (x0, x1, y). Only the previous row's runs are ever compared, so
    # memory is one row of runs plus the flat run list.
    runs: list[tuple[int, int, int]] = []
    prev: list[tuple[int, int, int]] = []            # (x0, x1, run_id)
    for y in range(h):
        cur: list[tuple[int, int, int]] = []
        # Both rows' runs are sorted by x0, so the previous row is swept with a
        # moving index instead of rescanned per run: a dense math page has
        # hundreds of runs per row, and the quadratic version of this loop is
        # what makes a "simple" labeller too slow to run per page.
        j = 0
        for x0, x1 in _row_runs(mask[y]):
            rid = len(runs)
            runs.append((x0, x1, y))
            parent.append(rid)
            while j < len(prev) and prev[j][1] < x0:   # ends left of us (±1)
                j += 1
            # 8-connectivity: the previous row's run touches when its column
            # span overlaps ours widened by one pixel on each side.
            k = j
            while k < len(prev) and prev[k][0] <= x1:
                union(rid, prev[k][2])
                k += 1
            cur.append((x0, x1, rid))
        prev = cur

    if not runs:
        return []

    # Accumulate each root's extent in one pass.
    acc: dict[int, list[int]] = {}
    for rid, (x0, x1, y) in enumerate(runs):
        r = find(rid)
        b = acc.get(r)
        if b is None:
            acc[r] = [x0, y, x1, y + 1]
        else:
            if x0 < b[0]:
                b[0] = x0
            if x1 > b[2]:
                b[2] = x1
            if y + 1 > b[3]:
                b[3] = y + 1
    out = [(b[0], b[1], b[2], b[3]) for b in acc.values()]
    if min_side > 0:
        out = [b for b in out
               if max(b[2] - b[0], b[3] - b[1]) >= min_side]
    out.sort(key=lambda b: (b[1], b[0]))
    return out


# --------------------------------------------------------------------------- #
#  Box arithmetic the readers share
# --------------------------------------------------------------------------- #

def union_box(boxes: Iterable[Box]) -> Optional[Box]:
    """The smallest box containing all of them, or None for an empty set."""
    it = iter(boxes)
    first = next(it, None)
    if first is None:
        return None
    x0, y0, x1, y1 = first
    for b in it:
        x0 = min(x0, b[0]); y0 = min(y0, b[1])
        x1 = max(x1, b[2]); y1 = max(y1, b[3])
    return (x0, y0, x1, y1)


def area(b: Box) -> int:
    return max(0, b[2] - b[0]) * max(0, b[3] - b[1])


def intersection(a: Box, b: Box) -> int:
    return (max(0, min(a[2], b[2]) - max(a[0], b[0]))
            * max(0, min(a[3], b[3]) - max(a[1], b[1])))


def iou(a: Box, b: Box) -> float:
    """Intersection over union. 0.0 when either box is degenerate."""
    inter = intersection(a, b)
    denom = area(a) + area(b) - inter
    return inter / denom if denom > 0 else 0.0


def rows(boxes: Sequence[Box], *, tol: float = 0.5,
         max_height: Optional[float] = None) -> list[list[Box]]:
    """Group components into printed ROWS by vertical overlap.

    A component joins the current row when it overlaps that row's running
    y-extent by at least `tol` of its OWN height. Measuring against the
    component's own height and not the row's is what keeps a tall integral
    sign from swallowing the next line: the sign overlaps two rows, but each
    row covers only a small share of the sign, so it stays with the row that
    covers most of it.

    `max_height` EXCLUDES components taller than it, and on a scan it is not
    optional. One component that spans the page — the dark band at a gutter,
    a fold, the edge of the platen — joins the first row, stretches that
    row's extent to the whole page, and then every other component on the
    page overlaps that extent by all of its own height and joins too. The
    page collapses to ONE row. Measured: a 97 x 3413 edge band on the
    reference 10-page document gave 1 row where the page has 25, and so 245
    of 311 lines got no box at all. The excluded components are not lost
    text: at six line heights nothing that tall is a printed line.
    """
    if max_height is not None:
        boxes = [b for b in boxes if (b[3] - b[1]) <= max_height]
    boxes = list(boxes)
    if not boxes:
        return []

    # TWO PHASES, and the split is the whole point. The bands are SEEDED AND
    # GROWN by ordinary-height components only; anything taller is assigned
    # afterwards to the band it overlaps most, without moving that band's
    # extent. A single pass cannot do this: a component two lines tall sorts
    # into the first of those lines, stretches that band across both, and the
    # second line's components then overlap the stretched band by all of
    # their own height and join it — two printed rows become one. An integral
    # sign, a large brace and a tall fraction all do this, and they are
    # exactly what a page of mathematics is full of.
    med = median_height(boxes)
    band_max = 2.0 * med
    ordinary = [b for b in boxes if (b[3] - b[1]) <= band_max]
    tall = [b for b in boxes if (b[3] - b[1]) > band_max]

    out: list[list[Box]] = []
    extent: list[list[int]] = []                 # [y0, y1] per band
    for b in sorted(ordinary, key=lambda b: (b[1], b[0])):
        h = max(1, b[3] - b[1])
        placed = False
        for n, (y0, y1) in enumerate(extent):
            cover = max(0, min(y1, b[3]) - max(y0, b[1])) / h
            if cover >= tol:
                out[n].append(b)
                extent[n] = [min(y0, b[1]), max(y1, b[3])]
                placed = True
                break
        if not placed:
            out.append([b])
            extent.append([b[1], b[3]])

    for b in tall:
        best, at = 0.0, -1
        for n, (y0, y1) in enumerate(extent):
            cover = max(0, min(y1, b[3]) - max(y0, b[1]))
            if cover > best:
                best, at = cover, n
        if at >= 0:
            out[at].append(b)                    # extent deliberately unchanged
        else:
            out.append([b])
            extent.append([b[1], b[3]])

    for row in out:
        row.sort(key=lambda b: b[0])
    out.sort(key=lambda row: min(c[1] for c in row))
    return out


def drop_scan_edges(boxes: Iterable[Box], width: int, height: int, *,
                    margin: int = 2) -> list[Box]:
    """Components that touch the image border — the scan, not the page.

    A printed glyph does not reach the edge of the platen. What does is the
    dark band at a book's gutter, the shadow at a lifted corner, the edge of
    the sheet against the glass. `rows(max_height=…)` already keeps the big
    band out of the row grouping, but a band that BROKE into pieces survives
    as a column of 1-2 px slivers — measured: seven of them at x=2035 of a
    2037-px page, each one joining a different text row and stretching it to
    the page edge. The reading's right margin moved from 0.941 of the page
    (the reference) to 1.000, which is every box on the page slightly wrong.
    """
    out = []
    for b in boxes:
        if (b[0] <= margin or b[1] <= margin
                or b[2] >= width - margin or b[3] >= height - margin):
            continue
        out.append(b)
    return out


def drop_speck_rows(row_list: list[list[Box]], line_height: float, *,
                    min_glyph: float = 0.6) -> list[list[Box]]:
    """Rows holding no component wide enough to be a glyph.

    A scan's fleck, a fold's shadow line, the residue of a cleaned stamp: each
    makes a row of its own, and a row is what the aligner counts. One spurious
    row costs one real line its box, because the match is monotone.
    """
    keep = []
    for row in row_list:
        if any((b[2] - b[0]) >= min_glyph * line_height for b in row):
            keep.append(row)
    return keep


def prune_row_outliers(row_list: list[list[Box]], line_height: float, *,
                       gap: float = 2.0, speck: float = 0.5
                       ) -> list[list[Box]]:
    """Drop from each row the components that are both FAR from it and SMALL.

    A row is grouped by vertical overlap, which says nothing about horizontal
    distance — so a 2x6 fleck in the outer margin, 1,500 px from the nearest
    glyph, joins the row it happens to align with and stretches that row's
    union box to the edge of the page. Measured on the reference 10-page scan:
    ten such flecks, and the reading's right margin at 0.996 of the page where
    the printed text ends at 0.94.

    BOTH conditions are required, and that is the whole design. Far-and-large
    is an equation number: printed at the margin, deliberately separated,
    45 x 40 px, and the reader needs its ink to cut it out of its display's
    row. Near-and-small is an accent or an `i` dot. Only far-and-small is
    nothing — and a threshold on either signal alone throws away one of the
    other two.

    The distance is measured to the nearest LARGE component and not to the
    nearest neighbour of any kind. Flecks arrive in clusters — two of them
    one pixel apart at the page edge — and peeling inwards one at a time
    stops at the first pair, because each one's nearest neighbour is the
    other.
    """
    out = []
    lim = speck * line_height
    for row in row_list:
        big = [b for b in row if max(b[2] - b[0], b[3] - b[1]) >= lim]
        if not big or len(big) == len(row):
            out.append(row)
            continue
        keep = []
        for b in row:
            if b in big:
                keep.append(b)
                continue
            far = min(max(0, g[0] - b[2], b[0] - g[2]) for g in big)
            if far <= gap * line_height:
                keep.append(b)
        out.append(keep or row)
    return out


def median_height(boxes: Iterable[Box], default: float = 40.0) -> float:
    """Median component height — the page's own yardstick for `SPECK`/`GAP`.

    Taken over COMPONENTS and not over rows: a row's height is distorted by
    every display formula on the page, while the glyph population is stable
    enough that half of it is body text on any page of running prose.
    """
    hs = sorted(max(0, b[3] - b[1]) for b in boxes)
    if not hs:
        return default
    return float(hs[len(hs) // 2])
