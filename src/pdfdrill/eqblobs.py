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

def _render_pgm(pdf: Path, page: int, out: Path, dpi: int) -> Path:
    """One page → 8-bit greyscale PGM, which is what blobcc reads natively.

    Ghostscript is pdfdrill's only rasterizer; `pgmraw` avoids a PNG decode and
    an image dependency, keeping the pass pure-stdlib.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pgmraw",
         f"-r{int(dpi)}", f"-dFirstPage={page}", f"-dLastPage={page}",
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


def _group_lines(blobs: Sequence[Any], height: int) -> list[list[Any]]:
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
    rows = [0] * (height + 1)
    for b in usable:
        lo, hi = int(max(0, b.min_y)), int(min(height, b.max_y))
        rows[lo] += 1
        rows[hi] += -1            # difference array: one pass, no per-row loop
    bands, run, acc = [], None, 0
    for y in range(height + 1):
        acc += rows[y]
        if acc > 0 and run is None:
            run = y
        elif acc <= 0 and run is not None:
            bands.append((run, y))
            run = None
    if run is not None:
        bands.append((run, height))
    if not bands:
        return []

    lines: list[list[Any]] = [[] for _ in bands]
    for b in usable:
        mid = (b.min_y + b.max_y) / 2.0
        for i, (lo, hi) in enumerate(bands):
            if lo <= mid <= hi:
                lines[i].append(b)
                break
    return [ln for ln in lines if ln]


def _count_columns(lines: Sequence[Sequence[Any]], body_x0: float,
                   body_x1: float) -> int:
    """1 or 2, from whether the middle of the body column is persistently blank."""
    if not lines:
        return 1
    mid = (body_x0 + body_x1) / 2.0
    band = (body_x1 - body_x0) * 0.04
    crossing = sum(1 for ln in lines
                   if min(b.min_x for b in ln) < mid - band
                   and max(b.max_x for b in ln) > mid + band)
    return 1 if crossing > len(lines) * 0.25 else 2


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

    lines = _group_lines(blobcc.scan(binary, w, h, axis="row"), h)
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
    geo.columns = _count_columns(lines, body_x0, body_x1)

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
