r"""An inline object's rectangle is its HOST LINE's, and must say so.

The owner, on 1805.01788 p4 (inklines arm): obj_299cf545694f, a Paragraph,
appears to contain a formula, and that formula -- obj_85f7a24dcde5 -- is drawn
across a line of prose where the page prints a run-in italic section heading.

The model is RIGHT. That Formula is the inline `\(m\)`, and its two surface
realizations carry `{'offset': 55, 'length': 5}` and `{'offset': 57,
'length': 5}`: all 107 Formula realizations in that document are inline, none
claims a whole line. The inspect page is what ignores the offset. It builds a
box from the anchors a realization spans, so a five-character formula inside a
69-character line is drawn 800 px wide -- the whole line -- and the viewer sees
a `Formula` rectangle lying over prose.

NO SUB-LINE GEOMETRY EXISTS TO NARROW IT WITH. The record has no `cnt`, and
its `geometry` is the string "ink". A box cut by character proportion would be
a guess, and D-11 says a reading states what it states.

So the box is kept and MARKED: `inline: true` on the box and on the element.
The overlay draws it dashed, and clicking it says the rectangle is the line
that HOSTS the object, not the object's own extent. A viewer can then tell a
formula that occupies a line from one that merely sits in it -- which is the
distinction the owner was missing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.docinspect import object_boxes  # noqa: E402

#: One prose line, as a reading states it.
_SIDX = {
    "payload": {"a1": {"_page": 4, "region": {"top_left_x": 221,
                                              "top_left_y": 1688,
                                              "width": 800, "height": 30},
                       "text": "scores that subject \\(m\\) has gained"}},
    "order": {"mathpix_lines": ["a1"]},
}


def _obj(props):
    return {"id": "obj_x", "type": "Formula", "props": {},
            "realizations": [{"stream": "mathpix_lines", "start": "a1",
                              "end": "a1", "role": "surface", "props": props}]}


def test_an_inline_realization_is_marked_inline():
    boxes = object_boxes(_obj({"offset": 55, "length": 5}), _SIDX, 4)
    assert boxes, "the box is kept: it is where the object sits"
    assert boxes[0].get("inline") is True, boxes[0]


def test_a_whole_line_claim_is_not_marked():
    """A Paragraph over that same line owns it, and must not be dashed."""
    boxes = object_boxes(_obj({}), _SIDX, 4)
    assert boxes
    assert not boxes[0].get("inline"), boxes[0]


def test_the_marked_box_still_has_the_lines_geometry():
    """Marking is not narrowing. No sub-line geometry exists to narrow with,
    so the rectangle stays the host line's and only its meaning changes."""
    boxes = object_boxes(_obj({"offset": 55, "length": 5}), _SIDX, 4)
    assert boxes[0]["x"] == 221 and boxes[0]["w"] == 800
