#!/usr/bin/env python3
"""Detect a shaded equation box in a scan crop.

out/067 found 1211.3375's displayed equations sit in grey boxes. auto_mask
thresholds at 200, so the box interior is neither paper nor ink: it fragments
and hands the scan components the render has no counterpart for. That is an
instrument artifact and it must be detectable rather than excluded by name —
excluding one document by hand leaves the next shaded document to be
discovered by the same surprise.

The test is the mass of MID-GREY pixels: luminance in [150, 245], neither
paper (>245) nor ink (<150). Measured, not guessed:

    shaded crops (1211.3375)   0.88 .. 0.94
    clean crops                0.03 .. 0.08

An order of magnitude of margin, so the 0.5 cut is nowhere near either
population. It also fires per CROP, not per document: five of 1211.3375's
eight hits are unshaded and score 6-8 ink, while its three shaded ones score
128, 181 and 213.
"""
import sys
from pathlib import Path

from PIL import Image

MID_LO, MID_HI, SHADED_AT = 150, 246, 0.5


def midgrey_fraction(path) -> float:
    """Share of pixels that are neither paper nor ink."""
    with Image.open(path) as im:
        hist = im.convert("L").histogram()
    tot = sum(hist) or 1
    return sum(hist[MID_LO:MID_HI]) / tot


def is_shaded(path, threshold: float = SHADED_AT) -> bool:
    try:
        return midgrey_fraction(path) >= threshold
    except Exception:
        return False        # unreadable is not evidence of shading


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(f"{midgrey_fraction(p):.3f}  {'SHADED' if is_shaded(p) else 'clean '}  {p}")
