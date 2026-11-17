r"""One box per occurrence, not one box around all of them.

The owner: "some very large formual rectangles appeared on this document!" On
0864 p1 a Formula box ran [189,1605]..[1936,2215] across both columns, with
`latex` just "p"; another, `latex` "Y", covered [189,1142]..[1941,1928].

Neither is a reader defect. `FormulaProcessor` dedupes by latex on purpose
(`_dedupe`), so every occurrence of an inline `Y` is ONE DocObject carrying one
surface realization per place it appears — 13 of them on that document. The box
was then the union of every realization on the object's page, which is a
rectangle around thirteen unrelated occurrences and corresponds to nothing on
the paper.

MathPix's own reading of the same PDF does it too, and worse: 23 Formula boxes
over 120 px tall, the tallest 1640 px, against the Gemma reading's 27 and
1333 px. So this is pdfdrill's geometry, not anybody's reading.

A realization is the unit. Its own anchors still union — a paragraph wholly on
one page is one box over all its lines, which `test_docinspect_page_union`
pins — but two realizations never merge.
"""
from __future__ import annotations

from pdfdrill import docinspect


def _sidx(payload: dict, order: list[str]) -> dict:
    return {"payload": payload, "order": {"mathpix_lines": order}}


def _line(page, x, y, w=40, h=30, text="x"):
    return {"_page": page, "text": text,
            "region": {"top_left_x": x, "top_left_y": y, "width": w, "height": h}}


def _repeated(anchors, page=1):
    """One object, one single-anchor realization per occurrence — what
    FormulaProcessor's dedupe builds."""
    return {"props": {"page": page},
            "realizations": [{"stream": "mathpix_lines", "start": a, "end": a}
                             for a in anchors]}


PAYLOAD = {"a": _line(1, 200, 300, text="p"),
           "b": _line(1, 1500, 1800, text="p"),
           "c": _line(1, 400, 2100, text="p")}
ORDER = ["a", "b", "c"]


def test_the_box_is_one_occurrence_not_the_hull_of_all_of_them():
    page, bbox, _ = docinspect.object_geometry(_repeated(ORDER), _sidx(PAYLOAD, ORDER))
    assert page == 1
    assert bbox["w"] <= 40 and bbox["h"] <= 30, (
        "a box around 3 occurrences spans the page; it must be one occurrence")
    assert (bbox["x"], bbox["y"]) == (200, 300), "the first occurrence in reading order"


def test_every_occurrence_is_offered_as_its_own_box():
    boxes = docinspect.object_boxes(_repeated(ORDER), _sidx(PAYLOAD, ORDER), 1)
    assert len(boxes) == 3
    assert sorted((b["x"], b["y"]) for b in boxes) == [(200, 300), (400, 2100), (1500, 1800)]
    for b in boxes:
        assert b["w"] == 40 and b["h"] == 30


def test_the_preview_still_joins_every_occurrence():
    _, _, preview = docinspect.object_geometry(_repeated(ORDER), _sidx(PAYLOAD, ORDER))
    assert preview == "p p p"


def test_one_realization_over_several_lines_is_still_one_box():
    """The union within a realization is right and must survive."""
    payload = {"l1": _line(1, 100, 200, w=800, h=40, text="one"),
               "l2": _line(1, 90, 250, w=820, h=40, text="two")}
    obj = {"props": {"page": 1},
           "realizations": [{"stream": "mathpix_lines", "start": "l1", "end": "l2"}]}
    page, bbox, preview = docinspect.object_geometry(obj, _sidx(payload, ["l1", "l2"]))
    assert (bbox["x"], bbox["y"]) == (90, 200)
    assert bbox["x"] + bbox["w"] == 910 and bbox["y"] + bbox["h"] == 290
    assert docinspect.object_boxes(obj, _sidx(payload, ["l1", "l2"]), 1) == [bbox]
    assert preview == "one two"


def test_occurrences_on_another_page_are_not_boxed_here():
    payload = dict(PAYLOAD)
    payload["d"] = _line(2, 700, 700, text="p")
    order = ORDER + ["d"]
    boxes = docinspect.object_boxes(_repeated(order), _sidx(payload, order), 1)
    assert len(boxes) == 3, "page 2's occurrence belongs to page 2's overlay"
    boxes2 = docinspect.object_boxes(_repeated(order), _sidx(payload, order), 2)
    assert len(boxes2) == 1 and (boxes2[0]["x"], boxes2[0]["y"]) == (700, 700)


def test_an_object_with_one_occurrence_offers_exactly_one_box():
    boxes = docinspect.object_boxes(_repeated(["a"]), _sidx(PAYLOAD, ORDER), 1)
    assert len(boxes) == 1 and boxes[0]["x"] == 200
