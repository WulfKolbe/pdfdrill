"""Where a word box comes from, now that pdfdrill runs no OCR engine.

Seven features wanted word geometry and every one of them got it the same way:
render the page and run tesseract. That made an OCR engine a *dependency of
measurement* rather than a reading lane — `tsv`, `elements`, `continuity`,
`ordered`, `autosegment` and `fontid` each installed, invoked and parsed it,
none of them declared it, and on a scan they all produced words nobody chose to
buy. The lane contract (`docs/LANES.md`) says which reading a document gets.
This module says where a BOX comes from once that decision is made, and it has
exactly three answers:

1. **The PDF's own text layer** — `pdftotext -tsv`, free, exact, and already
   there. Word boxes with their text, in POINTS. This is the only route that
   yields a word's *text*, because a word's text can only come from something
   that read it.
2. **The page's own ink** — connected components grouped into rows and split at
   the inter-word gap. Free, offline, no reading at all. Boxes with NO text:
   this is the word-level twin of the geometry-only lane, and it is what a
   consumer that crops pixels (`fontid`) actually needs.
3. **Nothing** — and then the caller is told which lane would give it something,
   in the same words `route` uses. Not "install tesseract".

A reading bought from a provider (`gemmaocr`, `mathpix`) is deliberately NOT a
source here: both emit LINE boxes, and a line box offered where a word box is
expected is a wrong measurement rather than a missing one — the failure class
`layoutgeom` already refuses (no box is better than a wrong box).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Optional, Sequence

# A word's box is in POINTS on every route out of this module, because that is
# the unit a model's regions are in. The ink route converts from render pixels
# with the page's own scale; the text-layer route is already in points.
UNITS = "pt"

TEXT_LAYER = "text-layer"
INK = "ink"
NONE = "none"

# The inter-word gap, as a fraction of the row's median glyph height. MEASURED
# on 2402.13444v1 (9 pages, born digital, so its own text layer is the ground
# truth for both a word's count and its extent): ink words matched against the
# text layer's 5,264 word boxes at IoU >= 0.5 —
#     gap  0.25   0.30   0.35   0.40   0.45   0.50   0.60
#     hit  77.6%  80.8%  82.9%  82.8%  82.3%  77.6%  61.7%
#     n/truth 1.148 1.032 0.951  0.945  0.939  0.900  0.767
# 0.35 is the peak and the count closest to 1 from below; mean IoU of a matched
# box is 0.786 there. The 17% that never match are mostly the inline formulas of
# a math paper, where "one word" is not a thing the ink can know. A RATIO and not
# a pixel count because one sheet carries several type sizes.
GAP_RATIO = 0.35


# ---------------------------------------------------------------------------
# 1. the PDF's own text layer
# ---------------------------------------------------------------------------

def text_layer_tsv(pdf: Path, *, timeout: int = 120) -> str:
    """The 12-column TSV of the PDF's own text layer, or "" when it has none.

    `pdftotext -tsv` and tesseract TSV share a schema to the column, which is
    why every parser in `ocr_lines` reads this unchanged.
    """
    try:
        res = subprocess.run(["pdftotext", "-tsv", str(pdf), "-"],
                             capture_output=True, text=True, timeout=timeout)
    except (subprocess.SubprocessError, OSError):
        return ""
    return res.stdout if res.returncode == 0 else ""


def has_text_layer(pdf: Path) -> bool:
    """True when the text layer carries at least one word with a box."""
    tsv = text_layer_tsv(pdf)
    if not tsv:
        return False
    from . import ocr_lines
    words, _dims = ocr_lines.parse_tsv(tsv)
    return bool(words)


def words_for(pdf: Path) -> tuple[list[dict], dict[int, tuple[float, float]], str]:
    """(words, page_dims, source) in the legacy `ocr_lines.parse_tsv` shape.

    Word boxes with their TEXT, which only the text layer can give. An empty
    list means this document has no word-level measurement to be had — see
    `no_words_note`, never an install instruction.
    """
    from . import ocr_lines
    tsv = text_layer_tsv(pdf)
    if tsv:
        words, dims = ocr_lines.parse_tsv(tsv)
        if words:
            return words, dims, TEXT_LAYER
    return [], {}, NONE


def enriched_for(pdf: Path) -> tuple[dict, str]:
    """The all-levels parse (page/block/par/line/word) of the text layer."""
    from . import ocr_lines
    tsv = text_layer_tsv(pdf)
    if tsv:
        parsed = ocr_lines.parse_tsv_enriched(tsv)
        if parsed["words"]:
            return parsed, TEXT_LAYER
    return ocr_lines._empty_enriched(), NONE


def combined_tsv(pdf: Path) -> tuple[str, str]:
    """(tsv, source) for a consumer that wants the raw TSV string.

    The page_num column already carries the real page number — the renumbering
    every per-image OCR call needed does not apply to a whole-document read.
    """
    tsv = text_layer_tsv(pdf)
    if tsv and tsv.strip():
        from . import ocr_lines
        words, _dims = ocr_lines.parse_tsv(tsv)
        if words:
            return tsv, TEXT_LAYER
    return "", NONE


# ---------------------------------------------------------------------------
# 2. the page's own ink — boxes with no text
# ---------------------------------------------------------------------------

def ink_words(png: Path, *, gap_ratio: float = GAP_RATIO,
              whiten: Optional[Sequence] = None) -> list[tuple[int, int, int, int]]:
    """Word boxes from the page's ink alone, in RENDER PIXELS, reading order.

    The same three steps `geometry_page` takes to find a row, with one more: a
    row's components are split wherever the horizontal gap exceeds
    `gap_ratio * median glyph height`. No text is read and none is implied —
    these are places where a word is, for a consumer that crops the pixels.
    """
    from . import gemma_reader, inkbox
    gray = inkbox.load_gray(Path(png))
    if whiten:
        gray = gemma_reader._whiten_array(gray, list(whiten))
    h, w = gray.shape
    comps = inkbox.components(gray)
    lh = inkbox.median_height(comps)
    comps = [b for b in comps
             if max(b[2] - b[0], b[3] - b[1]) >= inkbox.SPECK * lh]
    comps = inkbox.drop_scan_edges(comps, w, h)
    row_list = inkbox.rows(comps, max_height=gemma_reader.TALL_DROP * lh)
    row_list = inkbox.drop_speck_rows(row_list, lh)
    row_list = inkbox.prune_row_outliers(row_list, lh)

    gap = gap_ratio * lh
    out: list[tuple[int, int, int, int]] = []
    for row in row_list:
        run: list = []
        for box in sorted(row, key=lambda b: b[0]):
            if run and box[0] - run[-1][2] > gap:
                merged = inkbox.union_box(run)
                if merged is not None:
                    out.append(merged)
                run = []
            run.append(box)
        merged = inkbox.union_box(run)
        if merged is not None:
            out.append(merged)
    out.sort(key=lambda b: (b[1], b[0]))
    return out


# ---------------------------------------------------------------------------
# 3. nothing — and which lane would change that
# ---------------------------------------------------------------------------

def no_words_note(pdf: Path, *, what: str = "word boxes") -> str:
    """Why there are none, and the command that gives this document a reading.

    Deliberately NOT an install instruction. pdfdrill runs no OCR engine, so
    the answer to "no words" is a lane, and the lane is the one `route` names.
    """
    name = Path(pdf).name
    return (
        f"No {what} for {name}: it has no text layer of its own, and pdfdrill "
        f"runs no OCR engine — a word's text can only come from something that "
        f"read it.\n"
        f"  The free, offline measurement is the SHAPE, not the words:\n"
        f"    pdfdrill gemmaocr {name} --geometry-only   (boxes + types, no text)\n"
        f"    pdfdrill geometry {name} --layout          (those boxes onto a model)\n"
        f"  A reading of the words costs: `pdfdrill gemmaocr {name}` (METERED) or "
        f"`pdfdrill mathpix {name}` (PAID). Both give LINE boxes, not word boxes.\n"
        f"  `pdfdrill route {name}` states the lane this document gets."
    )
