"""A page is cut into strips between its printed lines, never across one.

THE OVERLAP WAS THE DEFECT, NOT THE CURE. `gemma_reader` read a page as six
strips overlapping by 6 %, because a printed line falling on a cut has to be
whole in one of them, and the prompt asked the model not to transcribe such a
line twice. It does.

Measured on a board scan extract, page 1, read on a local host: the model
returned `(ii) If we adjoin a new generator` at the end of one chunk and
`(ii) If we adjust a new generator ... instead of` at the start of the next,
and `at the same time, add to relations (9.16)` twice as well. The assembler
then had more items than the page had ink rows: it gave one duplicate NO BOX AT
ALL (y=0, h=0), squeezed another into a 26 px sliver of the row above, and from
there every item was one row out — 16 of 31 text lines carried their
NEIGHBOUR's text, on boxes matching a known-good reading of the same page at
IoU 0.93-0.98. `gd3-learn` then labelled 572 of 4646 units (0.123) where the
same pages read by the same model elsewhere give 2760 (0.594).

A reading whose boxes are right and whose text is shifted by one line is worse
than a missing one. So the duplicate is PREVENTED rather than detected: the
page's own ink says where the printed lines are, and a cut through a blank band
splits no line.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import gemma_reader as GR


def _page(tmp_path, rows, *, width=200, height=600, band=20, gap=30, top=20):
    """A white page with `rows` black bands, each `band` tall, `gap` apart."""
    Image = pytest.importorskip("PIL.Image")
    pytest.importorskip("numpy")
    im = Image.new("L", (width, height), 255)
    bands = []
    y = top
    for _ in range(rows):
        if y + band > height:
            break
        for yy in range(y, y + band):
            for xx in range(10, width - 10):
                im.putpixel((xx, yy), 0)
        bands.append((y, y + band))
        y += band + gap
    png = tmp_path / "page.png"
    im.save(png)
    return png, bands


def test_every_cut_falls_in_a_blank_band(tmp_path):
    png, bands = _page(tmp_path, rows=12)
    cuts = GR.strip_cuts(png, strips=6)
    assert cuts is not None and len(cuts) == 5
    for c in cuts:
        assert not any(top <= c < bot for top, bot in bands), \
            f"cut {c} falls inside a printed line"


def test_the_cuts_are_in_order_and_distinct(tmp_path):
    png, _ = _page(tmp_path, rows=12)
    cuts = GR.strip_cuts(png, strips=6)
    assert cuts == sorted(cuts) and len(set(cuts)) == len(cuts)


def test_the_strips_tile_the_page_with_no_overlap(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    png, bands = _page(tmp_path, rows=12)
    out = GR.page_strips(png, tmp_path / "strips", strips=6)
    assert len(out) == 6
    heights = [Image.open(p).size[1] for p in out]
    assert sum(heights) == Image.open(png).size[1], \
        "the strips must tile the page exactly: no overlap, nothing dropped"


def test_a_page_with_no_ink_keeps_the_overlapping_strips(tmp_path):
    """A page whose ink cannot be read is the ONE case where a line may still
    fall on a cut, and there the overlap is still the best available answer."""
    Image = pytest.importorskip("PIL.Image")
    pytest.importorskip("numpy")
    png = tmp_path / "blank.png"
    Image.new("L", (200, 600), 255).save(png)
    assert GR.strip_cuts(png, strips=6) is None
    out = GR.page_strips(png, tmp_path / "strips", strips=6)
    assert len(out) == 6
    heights = [Image.open(p).size[1] for p in out]
    assert sum(heights) > 600, "the fallback still overlaps"


def test_a_page_with_fewer_lines_than_strips_keeps_the_fallback(tmp_path):
    png, _ = _page(tmp_path, rows=3)
    assert GR.strip_cuts(png, strips=6) is None


def test_a_strip_is_never_empty(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    png, _ = _page(tmp_path, rows=12)
    for p in GR.page_strips(png, tmp_path / "strips", strips=6):
        assert Image.open(p).size[1] > 0
