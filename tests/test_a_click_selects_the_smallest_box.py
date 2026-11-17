"""A click on the page selects the smallest box that contains the point.

The owner reported it as "Overlapping rectangle make it hard to inspect the
page!" and, on another document, a rectangle showing one thing while the record
showed another. Measured on his own pages: 0864 has 42 near-identical box pairs
(23 Formula/Formula, 10 Reference/Reference, 3 Formula/Paragraph at IoU > 0.95)
and 41 overlapping pairs whose areas tie within 2%.

`renderPage` sorts by area descending so the smallest paints last and the click
hits it. That is right until two boxes have the SAME area, and then the order
is arbitrary: the rectangle that lights up belongs to one object while the
record shown belongs to the other. Paint order cannot express "and if they tie,
always the same one".

So the hit test is explicit and total: smallest area wins, a tie goes to the
more specific type, and a remaining tie goes to the lower id — the same click
always selects the same object. This runs the SHIPPED block in node rather than
asserting that a string appears in the template.
"""
import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import docinspect

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")

_START = "/* ---------- hit test: the smallest box wins ---------- */"
_END = "/* ---------- hit test ends ---------- */"


def _hit_block() -> str:
    """The shipped block, verbatim — not a copy that can drift from it."""
    tpl = docinspect._TEMPLATE
    i = tpl.index(_START)
    j = tpl.index(_END, i)
    return tpl[i:j]


def _pick(elements, page, fx, fy):
    js = textwrap.dedent("""
    %s
    const EL = %s;
    const hit = boxAt(EL, %s, %s, %s);
    console.log(JSON.stringify(hit ? hit.id : null));
    """) % (_hit_block(), json.dumps(elements), page, fx, fy)
    p = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip().splitlines()[-1])


def _box(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h}


def test_the_small_box_inside_a_big_one_wins():
    els = [{"id": "para", "type": "Paragraph", "page": 1, "bbox": _box(0, 0, 400, 200)},
           {"id": "form", "type": "Formula", "page": 1, "bbox": _box(50, 50, 40, 20)}]
    assert _pick(els, 1, 60, 60) == "form"
    # outside the formula, still inside the paragraph
    assert _pick(els, 1, 300, 150) == "para"


def test_two_coincident_boxes_pick_the_more_specific_type():
    """A Formula whose box equals its Paragraph's: 6 such pairs on 2312.11532."""
    a = {"id": "p1", "type": "Paragraph", "page": 1, "bbox": _box(10, 10, 100, 30)}
    b = {"id": "f1", "type": "Formula", "page": 1, "bbox": _box(10, 10, 100, 30)}
    assert _pick([a, b], 1, 50, 20) == "f1"
    assert _pick([b, a], 1, 50, 20) == "f1", "the answer must not depend on input order"


def test_a_tie_between_one_type_is_broken_by_id_not_by_order():
    """23 Formula/Formula pairs on 0864 are near-identical; the click must be stable."""
    a = {"id": "aaa", "type": "Formula", "page": 1, "bbox": _box(0, 0, 50, 50)}
    b = {"id": "bbb", "type": "Formula", "page": 1, "bbox": _box(0, 0, 50, 50)}
    assert _pick([a, b], 1, 25, 25) == "aaa"
    assert _pick([b, a], 1, 25, 25) == "aaa"


def test_a_point_on_no_box_selects_nothing():
    els = [{"id": "x", "type": "Paragraph", "page": 1, "bbox": _box(0, 0, 10, 10)}]
    assert _pick(els, 1, 500, 500) is None


def test_the_page_frame_is_never_the_click_target():
    els = [{"id": "pg", "type": "Page", "page": 1, "bbox": _box(0, 0, 1000, 1000)},
           {"id": "para", "type": "Paragraph", "page": 1, "bbox": _box(0, 0, 400, 200)}]
    assert _pick(els, 1, 10, 10) == "para"
    assert _pick(els, 1, 900, 900) is None


def test_a_box_on_another_page_is_never_picked():
    els = [{"id": "other", "type": "Formula", "page": 2, "bbox": _box(0, 0, 10, 10)},
           {"id": "here", "type": "Paragraph", "page": 1, "bbox": _box(0, 0, 400, 200)}]
    assert _pick(els, 1, 5, 5) == "here"


def test_an_element_without_a_box_is_skipped():
    els = [{"id": "nobox", "type": "Formula", "page": 1, "bbox": None},
           {"id": "here", "type": "Paragraph", "page": 1, "bbox": _box(0, 0, 400, 200)}]
    assert _pick(els, 1, 5, 5) == "here"


def test_the_overlay_hover_does_not_disagree_with_the_click():
    """The CSS `.box:hover` rule highlighted whatever was physically topmost,
    which is the overlay stack, not the record a click would select. The
    highlight must come from the same hit test."""
    tpl = docinspect._TEMPLATE
    assert ".box:hover{" not in tpl, (
        "a bare .box:hover rule lets the highlight disagree with the click")
    assert "boxAt(" in tpl, "the page must use the hit test it ships"
