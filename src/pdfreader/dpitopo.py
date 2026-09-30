"""dpitopo — does glyph topology change between render resolutions?

The claim under test: Mathpix renders at a constant 250 dpi, but glyph
TOPOLOGY is not stable at that resolution, so inkdrill needs 400 dpi.

Topology here means what inkdrill means by it: the number of connected ink
components and the number of holes (counters) they enclose. A component count
that changes between resolutions means strokes merged or broke; a hole count
that changes means a counter filled in or opened up. Either makes a glyph a
different object to a topology-first recogniser, however similar it looks.

Components are 8-connected and holes 4-connected, the pairing inkdrill uses
(`nest`: fg conn=8, bg conn=4). Hole count per component equals its cycle rank,
which is what `sweep.Component.cycle_count` reports.

METHOD
  render the same page at each dpi with Ghostscript to stdout (png16m: gs does
  not halftone truecolour, so what is measured is content, not dithering),
  then compare per-GLYPH using the LTChar boxes as the sampling windows, scaled
  to each raster. Comparing whole-page totals alone would hide compensating
  errors -- one glyph gaining a component while another loses one.
"""
from __future__ import annotations

import io
import subprocess
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

GS = "gs"


def render(pdf: str, page: int, dpi: int, device: str = "png16m") -> Image.Image:
    """Rasterize one page straight to stdout -- no temporary file."""
    cmd = [GS, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER",
           f"-sDEVICE={device}", f"-r{dpi}",
           f"-dFirstPage={page}", f"-dLastPage={page}",
           "-sOutputFile=-", pdf]
    out = subprocess.run(cmd, capture_output=True, check=True).stdout
    return Image.open(io.BytesIO(out))


def topology(mask: np.ndarray) -> tuple[int, int]:
    """(ink components, holes) for a boolean ink mask."""
    if not mask.any():
        return 0, 0
    _, ncomp = ndimage.label(mask, structure=np.ones((3, 3), dtype=int))
    # holes: background regions that do not touch the border. Pad by one so
    # the outside is a single region and the border test is a label lookup.
    bg = np.pad(~mask, 1, constant_values=True)
    lab, nbg = ndimage.label(bg)          # 4-connected by default
    outside = lab[0, 0]
    holes = nbg - (1 if outside else 0)
    return ncomp, holes


def ink(im: Image.Image, thresh: int = 128) -> np.ndarray:
    return np.asarray(im.convert("L")) < thresh


def compare(pdf: str, page: int, lo: int = 250, hi: int = 400,
            max_glyphs: int | None = None):
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTChar

    layout = next(iter(extract_pages(pdf, page_numbers=[page - 1])))
    chars = []

    def walk(o):
        if isinstance(o, LTChar):
            chars.append(o)
        elif hasattr(o, "__iter__"):
            for c in o:
                walk(c)

    for e in layout:
        walk(e)

    # Only measure glyphs whose box no neighbour intrudes on. At normal
    # kerning an adjacent letter's ink enters the box and is counted as an
    # extra component, which would inflate the change rate without any glyph
    # having changed. Isolation is the difference between measuring topology
    # and measuring crowding.
    def overlaps(a, b) -> bool:
        return not (a.x1 + 0.5 < b.x0 or b.x1 + 0.5 < a.x0
                    or a.y1 + 0.5 < b.y0 or b.y1 + 0.5 < a.y0)

    isolated = []
    for i, a in enumerate(chars):
        if not any(overlaps(a, b) for j, b in enumerate(chars) if i != j):
            isolated.append(a)
    crowded = len(chars) - len(isolated)
    chars = isolated
    if max_glyphs:
        chars = chars[:max_glyphs]

    imgs = {d: render(pdf, page, d) for d in (lo, hi)}
    masks = {d: ink(im) for d, im in imgs.items()}
    page_w, page_h = layout.width, layout.height

    changed_comp = changed_hole = 0
    per_dpi = {lo: [0, 0], hi: [0, 0]}
    examples = []
    for ch in chars:
        res = {}
        for d in (lo, hi):
            m = masks[d]
            H, W = m.shape
            sx, sy = W / page_w, H / page_h
            # one pixel of margin so a stroke on the box edge is not clipped
            x0 = max(0, int(ch.x0 * sx) - 1)
            x1 = min(W, int(ch.x1 * sx) + 2)
            y0 = max(0, int((page_h - ch.y1) * sy) - 1)
            y1 = min(H, int((page_h - ch.y0) * sy) + 2)
            if x1 <= x0 or y1 <= y0:
                res[d] = (0, 0)
                continue
            res[d] = topology(m[y0:y1, x0:x1])
            per_dpi[d][0] += res[d][0]
            per_dpi[d][1] += res[d][1]
        if res[lo][0] != res[hi][0]:
            changed_comp += 1
        if res[lo][1] != res[hi][1]:
            changed_hole += 1
        if res[lo] != res[hi] and len(examples) < 12:
            examples.append((ch.get_text(), ch.fontname.split("+")[-1],
                             round(ch.size, 1), res[lo], res[hi]))

    return {
        "glyphs": len(chars),
        "crowded_skipped": crowded,
        "sizes": {d: imgs[d].size for d in imgs},
        "totals": {d: tuple(per_dpi[d]) for d in per_dpi},
        "changed_components": changed_comp,
        "changed_holes": changed_hole,
        "changed_any": sum(1 for _ in ()) or None,
        "examples": examples,
    }


if __name__ == "__main__":
    pdf = sys.argv[1]
    page = int(sys.argv[2]) if len(sys.argv) > 2 else 209
    lo = int(sys.argv[3]) if len(sys.argv) > 3 else 250
    hi = int(sys.argv[4]) if len(sys.argv) > 4 else 400
    r = compare(pdf, page, lo, hi)
    print(f"page {page}: {r['glyphs']} isolated glyphs measured "
          f"({r['crowded_skipped']} skipped as crowded)")
    for d, s in r["sizes"].items():
        print(f"  {d} dpi raster {s[0]}x{s[1]}   "
              f"components={r['totals'][d][0]} holes={r['totals'][d][1]}")
    print(f"  glyphs whose COMPONENT count differs: {r['changed_components']} "
          f"({100.0 * r['changed_components'] / max(r['glyphs'], 1):.1f}%)")
    print(f"  glyphs whose HOLE count differs:      {r['changed_holes']} "
          f"({100.0 * r['changed_holes'] / max(r['glyphs'], 1):.1f}%)")
    print("\n  examples (char, font, pt, (comp,holes)@lo -> @hi):")
    for e in r["examples"]:
        print(f"    {e[0]!r:6} {e[1]:<22} {e[2]:>5}  {e[3]} -> {e[4]}")
