# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""font_size from the font size the PDF states, not from a box height."""
from __future__ import annotations

from collections import Counter

from ..bboxlayout import PX_PER_PT

# MathPix `font_size` over the dominant font size of the line in page pixels.
FONT_SIZE_PER_EM = 0.87


def process(page: dict, record, own: list[int]) -> list[tuple[str, dict]]:
    glyphs = getattr(record, "glyphs", record)
    sizes: dict[int, Counter] = {}
    for g in range(glyphs.n):
        if own[g] >= 0 and glyphs.text[g].strip():
            sizes.setdefault(own[g], Counter())[round(glyphs.size[g], 2)] += 1
    patches = []
    for i, ln in enumerate(page["lines"]):
        if i in sizes:
            em = sizes[i].most_common(1)[0][0]
            patches.append((ln["id"], {
                "font_size": round(em * PX_PER_PT * FONT_SIZE_PER_EM)}))
    return patches
