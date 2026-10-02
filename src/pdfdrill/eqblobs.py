"""Keyless page geometry from connected components — display-equation regions.

A pure geometry pass. It answers *where* things sit on the page, never *what*
they say: no OCR, no network, no key. The LaTeX for an equation comes from the
author's source (`injectlatex`) or a keyed route (`mathpix`); what neither of
those supplies for a born-digital paper is the region on the page, which is
what `report`/`inspect`/`compare` need to show a crop.

The pipeline is Ghostscript → PGM → `vendor.blobcc` (8-connectivity union-find
with moment aggregates) → line grouping → display-equation heuristics.

Why blobs rather than the text layer: a display equation is laid out, not
written. Its glyphs come from many fonts at several baselines (limits, indices,
fraction bars), so the reading-order text layer scatters it across "lines" that
do not correspond to what a reader sees as one equation. Ink geometry keeps it
whole.

Detection is deliberately conservative — a line is a display-equation candidate
when it is *indented from both margins* relative to the body column (display
math is centred) or *materially taller* than the body line height (fractions,
sums, matrices). Both signals are layout facts, not content guesses, so a false
positive costs a spurious region, never a wrong formula.
"""

from __future__ import annotations

import math
import statistics
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

from .vendor import blobcc

__all__ = ["PageGeometry", "EquationRegion", "analyse_pdf", "analyse_page"]

#: ink specks below this many pixels are dust/antialiasing, not glyphs
_MIN_BLOB_AREA = 6
#: two blobs belong to the same line when their vertical spans overlap by this
#: fraction of the shorter one
_LINE_OVERLAP = 0.35
#: a line must be inset from BOTH body margins by this fraction of the body
#: width before centring alone marks it as display math
_INSET_FRAC = 0.06
#: ... or be this much taller than the median body line
_TALL_FACTOR = 1.55


@dataclass
class EquationRegion:
    """A display-math candidate, in PDF points, top-left origin."""
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    reason: str
    height_ratio: float
    ink: int

    def as_dict(self) -> dict[str, Any]:
        return {"page": self.page, "x0": round(self.x0, 2), "y0": round(self.y0, 2),
                "x1": round(self.x1, 2), "y1": round(self.y1, 2),
                "units": "pt", "reason": self.reason,
                "height_ratio": round(self.height_ratio, 2), "ink": self.ink}


@dataclass
class PageGeometry:
    """What the ink says about one page, independent of any text layer."""
    page: int
    width_pt: float
    height_pt: float
    skew_deg: float
    body_x0: float
    body_x1: float
    line_count: int
    median_line_height: float
    columns: int
    equations: list[EquationRegion] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"page": self.page,
                "width_pt": round(self.width_pt, 1),
                "height_pt": round(self.height_pt, 1),
                "skew_deg": round(self.skew_deg, 4),
                "body_x0": round(self.body_x0, 1),
                "body_x1": round(self.body_x1, 1),
                "line_count": self.line_count,
                "median_line_height": round(self.median_line_height, 1),
                "columns": self.columns,
                "equations": [e.as_dict() for e in self.equations]}


# ---------------------------------------------------------------------------
# rasterisation
# ---------------------------------------------------------------------------


def _gs_threads() -> list[str]:
    """Shared gs threading/banding flags (see pdf_reading.gs_render_args)."""
    try:
        from .pdf_reading import gs_render_args
        return gs_render_args()
    except Exception:                            # noqa: BLE001
        return []


def _render_pgm(pdf: Path, page: int, out: Path, dpi: int) -> Path:
    """One page → 8-bit greyscale PGM, which is what blobcc reads natively.

    Ghostscript is pdfdrill's only rasterizer; `pgmraw` avoids a PNG decode and
    an image dependency, keeping the pass pure-stdlib.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", *_gs_threads(),
         "-sDEVICE=pgmraw", f"-r{int(dpi)}", f"-dFirstPage={page}", f"-dLastPage={page}",
         f"-sOutputFile={out}", str(pdf)],
        check=True, capture_output=True, timeout=300)
    return out


# ---------------------------------------------------------------------------
# grouping
# ---------------------------------------------------------------------------

def _overlap_frac(a_lo: float, a_hi: float, b_lo: float, b_hi: float) -> float:
    lo, hi = max(a_lo, b_lo), min(a_hi, b_hi)
    if hi <= lo:
        return 0.0
    return (hi - lo) / max(1.0, min(a_hi - a_lo, b_hi - b_lo))


#: 848 — a gutter is at least this fraction of the body wide, and carries at
#: most this fraction of the page's peak ink. Measured at 300 dpi over five
#: pages: a two-column page shows a 126 px blank run (4.5% of a 2,810 px body)
#: and a single-column page shows ZERO, so the two populations do not touch and
#: the constants sit in the middle of the gap rather than on either edge.
_GUTTER_MIN_FRAC = 0.02
_GUTTER_MAX_INK = 0.08


def _gutter_x(blobs: Sequence[Any], width: int) -> Optional[float]:
    r"""The x of a blank vertical gutter in the middle of the body, or None.

    848 — THE QUESTION `_count_columns` COULD NOT ANSWER. It counted banded
    LINES crossing the midline, and on a two-column page every band already
    spans both columns, so the crossing count was always high and the answer was
    always 1. Measured: `pfahler_morik_2020a` reported 1-column on all 9 pages
    while the glyph reader found 2 column containers on every one of them and
    `pdftotext -layout` prints the two blocks side by side.

    Counting BLOBS that cross is no better — a connected component at 300 dpi is
    a glyph, and 0.00% of them cross the midline on a single-column page OR a
    two-column one. The signal is the vertical INK PROFILE: how many blobs cover
    each x. A two-column page has a sustained near-zero run in the middle; a
    single-column page has none at all.

    Per page, not per document, with None meaning "band the whole page": a page
    whose gutter is bridged by a full-width figure HAS no gutter, and banding it
    as one column is then right. Cat2Type's page 3 is that case.
    """
    if not blobs:
        return None
    xs0 = min(b.min_x for b in blobs)
    xs1 = max(b.max_x for b in blobs)
    body = xs1 - xs0
    if body <= 0:
        return None
    prof = [0] * (width + 2)
    for b in blobs:
        prof[int(max(0, b.min_x))] += 1
        prof[int(min(width, b.max_x))] -= 1
    acc, cov = 0, []
    for x in range(width + 2):
        acc += prof[x]
        cov.append(acc)
    peak = max(cov[int(xs0):int(xs1)] or [0])
    if peak <= 0:
        return None
    lo = int(xs0 + 0.25 * body)
    hi = int(xs0 + 0.75 * body)
    best, run, at = 0, 0, None
    for x in range(lo, hi):
        if cov[x] <= _GUTTER_MAX_INK * peak:
            run += 1
            if run > best:
                best, at = run, x - run // 2
        else:
            run = 0
    return float(at) if best >= _GUTTER_MIN_FRAC * body else None


def _bands(ys: "list[tuple[int, int]]", height: int) -> "list[tuple[int, int]]":
    """Merge (lo, hi) ink spans into maximal non-overlapping bands."""
    rows = [0] * (height + 2)
    for lo, hi in ys:
        rows[lo] += 1
        rows[hi] += -1
    out, run, acc = [], None, 0
    for y in range(height + 2):
        acc += rows[y]
        if acc > 0 and run is None:
            run = y
        elif acc <= 0 and run is not None:
            out.append((run, y))
            run = None
    if run is not None:
        out.append((run, height))
    return out


def _group_lines(blobs: Sequence[Any], height: int,
                 width: int = 0) -> list[list[Any]]:
    """Cluster blobs into visual lines via a horizontal ink-projection profile.

    Pairwise vertical overlap was tried first and is wrong here: a display
    equation is taller than the prose around it, so its span reaches into the
    neighbouring text line and the two merge. Every line then measured as
    full-body-width and no equation was ever short-and-centred — the detector
    found nothing on a paper with 34 of them.

    Projecting ink onto the y axis instead gives the blank gutters between
    lines directly, and a display equation keeps its own band because the
    gutters around it are *wider*, not narrower.
    """
    usable = [b for b in blobs if b.area >= _MIN_BLOB_AREA
              and b.max_x > b.min_x and b.max_y > b.min_y]
    if not usable:
        return []

    # 848 — PROJECT PER COLUMN, NOT PER PAGE. A projection over the whole page
    # puts a left-column line and an unrelated right-column line in one band, so
    # every band measures full-body-width and nothing is ever short-and-centred
    # — which is the exact failure this projection was introduced to FIX (see
    # above), reintroduced by the two-column case. inkdrill measured a
    # row-profile band model at 18.8% recall on two-column pages against 92.9%
    # on single-column, with no overlap: it does not degrade, it breaks. Seven
    # of their twenty sampled library documents are two-column.
    #
    # A blob that spans the gutter is a full-width element — a rule, a wide
    # figure, a spanning heading — and gets its own slab, so it still forms one
    # band instead of being cut in half.
    gx = _gutter_x(usable, width) if width else None
    if gx is None:
        slabs = [usable]
    else:
        left = [b for b in usable if b.max_x <= gx]
        right = [b for b in usable if b.min_x >= gx]
        full = [b for b in usable if b.min_x < gx < b.max_x]
        slabs = [sl for sl in (full, left, right) if sl]

    lines: list[list[Any]] = []
    for slab in slabs:
        bands = _bands([(int(max(0, b.min_y)), int(min(height, b.max_y)))
                        for b in slab], height)
        if not bands:
            continue
        buckets: list[list[Any]] = [[] for _ in bands]
        for b in slab:
            mid = (b.min_y + b.max_y) / 2.0
            for i, (lo, hi) in enumerate(bands):
                if lo <= mid <= hi:
                    buckets[i].append(b)
                    break
        lines.extend(ln for ln in buckets if ln)
    # document order within the page: top to bottom, then left to right
    lines.sort(key=lambda ln: (min(b.min_y for b in ln), min(b.min_x for b in ln)))
    return lines


def _count_columns(lines: Sequence[Sequence[Any]], body_x0: float,
                   body_x1: float, gutter: Optional[float] = None) -> int:
    """1 or 2 columns on this page.

    848 — FROM THE GUTTER, which is measured on blobs before any banding. This
    used to count banded LINES crossing the midline, and on a two-column page
    every band already spanned both columns, so the crossing count was always
    high and the answer was always 1: `pfahler_morik_2020a` reported 1-column on
    all 9 pages while the glyph reader found 2 column containers on each. The
    question was being asked of data that had already lost the answer.

    `gutter` is None for a page with no blank middle — a genuinely
    single-column page, or one whose gutter a full-width figure bridges — and
    both are correctly one column's worth of banding.
    """
    if not lines:
        return 1
    return 2 if gutter is not None else 1


# ---------------------------------------------------------------------------
# the pass
# ---------------------------------------------------------------------------

def analyse_page(pgm_path: str, page: int, dpi: int) -> PageGeometry:
    """Blob-scan one rendered page and report its geometry, in PDF points."""
    w, h, gray = blobcc.read_pnm(pgm_path)
    binary = blobcc.binarize(gray)
    to_pt = 72.0 / float(dpi)

    # column scan isolates long horizontal rules, whose principal axis is the
    # page skew; row scan gives the glyph blobs used for everything else
    try:
        skew = blobcc.estimate_skew_deg(blobcc.scan(binary, w, h, axis="col"))
    except Exception:
        skew = 0.0
    if skew is None or not math.isfinite(skew):
        skew = 0.0

    lines = _group_lines(blobcc.scan(binary, w, h, axis="row"), h, w)
    geo = PageGeometry(page=page, width_pt=w * to_pt, height_pt=h * to_pt,
                       skew_deg=float(skew), body_x0=0.0, body_x1=w * to_pt,
                       line_count=len(lines), median_line_height=0.0, columns=1)
    if not lines:
        return geo

    lefts = [min(b.min_x for b in ln) for ln in lines]
    rights = [max(b.max_x for b in ln) for ln in lines]
    heights = [max(b.max_y for b in ln) - min(b.min_y for b in ln) for ln in lines]

    # the body column is where the bulk of lines start/end; medians shrug off
    # headers, page numbers and the odd full-width figure
    body_x0, body_x1 = statistics.median(lefts), statistics.median(rights)
    med_h = statistics.median(heights) or 1.0
    geo.body_x0, geo.body_x1 = body_x0 * to_pt, body_x1 * to_pt
    geo.median_line_height = med_h * to_pt
    geo.columns = _count_columns(
        lines, body_x0, body_x1,
        _gutter_x([b for ln in lines for b in ln], int(w)))

    inset = max(1.0, (body_x1 - body_x0) * _INSET_FRAC)
    for ln, l, r, ht in zip(lines, lefts, rights, heights):
        ratio = ht / med_h
        centred = l > body_x0 + inset and r < body_x1 - inset
        tall = ratio >= _TALL_FACTOR
        if not (centred or tall):
            continue
        # a lone speck that happens to sit mid-column is a bullet, not math
        if len(ln) < 2 and not tall:
            continue
        reason = "centred+tall" if (centred and tall) else ("centred" if centred else "tall")
        geo.equations.append(EquationRegion(
            page=page,
            x0=min(b.min_x for b in ln) * to_pt,
            y0=min(b.min_y for b in ln) * to_pt,
            x1=max(b.max_x for b in ln) * to_pt,
            y1=max(b.max_y for b in ln) * to_pt,
            reason=reason, height_ratio=ratio,
            ink=sum(b.area for b in ln)))
    return geo


def analyse_pdf(pdf: Path, pages: Sequence[int], out_dir: Path,
                dpi: int = 300) -> list[PageGeometry]:
    """Render and analyse each requested page. Returns one PageGeometry each."""
    out: list[PageGeometry] = []
    for p in pages:
        target = Path(out_dir) / f"eqblobs-p{p}.pgm"
        try:
            pgm = _render_pgm(Path(pdf), p, target, dpi)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            continue
        if not pgm.exists():          # page past the end: gs writes nothing
            continue
        try:
            out.append(analyse_page(str(pgm), p, dpi))
        finally:
            try:
                pgm.unlink()
            except OSError:
                pass
    return out
