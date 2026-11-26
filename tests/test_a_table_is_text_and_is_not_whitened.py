"""A table is text: it is read, not whitened (B8a, 2026-11-26).

The model lane whitens what the layout detector boxes before the page is read,
and again out of the ink the lines are found in. `yololayout.whiten` gives its
reasons and every one is about a PICTURE — the model "invent[s] axis labels and
tick values that are not printed anywhere", and the alignment must see "no
figure strokes to hand to a passing text line".

But both call sites took `figure_boxes`' default, which is figures AND tables.
MEASURED on a board scan, lib:9027b2a8b957 p2, an invoice-type page:

    dark pixels in the table area    printed 190,801   shown to the model 4,757
    whole page                       printed 552,877   shown to the model 229,738

97.5 % of the table and 58 % of the page erased before the read. The model
transcribed about 15 of the page's ~100 printed lines, the assembler spread 15
items over ~100 ink rows (a 5-word line 6 px tall), and `gd3-learn` labelled 0
of 1934 units from the result — B8's dictionary refused for a reading that had
never been shown the page.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import gemma_reader as GR
from pdfdrill import yololayout as Y


def _det(cls, box):
    return Y.Det(model="layout", cls=cls, conf=0.9, box=box)


def test_only_a_picture_is_whitened():
    dets = [_det("table", (10, 10, 200, 100)), _det("figure", (10, 200, 200, 300))]
    got = Y.figure_boxes(dets, classes=GR._PICTURE_CLASSES)
    assert got == [(10, 200, 200, 300)]


def test_figure_boxes_still_serves_its_other_callers():
    """`layoutgeom` asks for tables and figures separately; the DEFAULT is
    unchanged, so nothing outside the reader moves."""
    dets = [_det("table", (10, 10, 200, 100)), _det("figure", (10, 200, 200, 300))]
    assert len(Y.figure_boxes(dets)) == 2


def test_both_call_sites_in_the_reader_say_which_boxes():
    """There are TWO places a box is whitened — the image the model reads and
    the ink the lines are found in — and the defect was both taking the default.
    A later edit that drops `classes=` at either one brings the invoice back."""
    src = Path(GR.__file__).read_text(encoding="utf-8")
    calls = re.findall(r"figure_boxes\(([^)]*)\)", src)
    assert len(calls) == 2, calls
    assert all("_PICTURE_CLASSES" in c for c in calls), calls
