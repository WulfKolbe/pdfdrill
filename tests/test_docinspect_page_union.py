r"""An inspector box belongs to ONE page.

`object_geometry` unioned the regions of every anchor in an object's
realization. A paragraph — and every inline Formula inside it — routinely runs
across a page turn, so that union mixed two pages' coordinate frames and the
result was then drawn at the object's `page`, which is one of them.

MEASURED on a 20-page scanned example: 14 Formula boxes outside their own
page's frame, the worst reaching 1.135 of its page width. A scan makes it
visible because each page has its own pixel size; on a born-digital document,
where every page is the same size, the box does not hang off the edge — it is
simply over the wrong part of a right-looking page, which is worse, because
nothing in the picture says so.

Every consumer assumes one page: the overlay filters `e.page === curPage` and
`cropBlob` cuts the box out of that page's bitmap. The same defect class as
T-0024's wrong-page crops, in the inspector instead of the rasterizer.
"""
from __future__ import annotations

from pdfdrill import docinspect


def _sidx(payload: dict, order: list[str]) -> dict:
    return {"payload": payload, "order": {"mathpix_lines": order}}


def _obj(start: str, end: str, page: int | None = None) -> dict:
    props = {} if page is None else {"page": page}
    return {"props": props,
            "realizations": [{"stream": "mathpix_lines",
                              "start": start, "end": end}]}


def test_a_realization_spanning_a_page_turn_is_boxed_on_its_own_page():
    """Pages of different widths, as a scan has. The box must stay inside the
    object's own page, and the text must still span both."""
    payload = {
        "p1_last": {"_page": 1, "text": "der vorliegende Theil der",
                    "region": {"top_left_x": 60, "top_left_y": 2400,
                               "width": 1600, "height": 40}},
        "p2_first": {"_page": 2, "text": "Untersuchung ist abgeschlossen.",
                     "region": {"top_left_x": 80, "top_left_y": 200,
                                "width": 1850, "height": 40}},
    }
    sidx = _sidx(payload, ["p1_last", "p2_first"])

    page, bbox, preview = docinspect.object_geometry(
        _obj("p1_last", "p2_first", page=1), sidx)
    assert page == 1
    # page 1's line ends at x=1660; page 2's at 1930. The union of both would
    # be 1930 wide, which is off the edge of page 1.
    assert bbox["x"] + bbox["w"] == 1660, bbox
    assert bbox["y"] == 2400 and bbox["h"] == 40
    # the TEXT does span the turn, and that part was never wrong
    assert "vorliegende" in preview and "abgeschlossen" in preview


def test_the_same_object_anchored_on_the_second_page_takes_that_pages_box():
    payload = {
        "p1_last": {"_page": 1, "text": "A",
                    "region": {"top_left_x": 60, "top_left_y": 2400,
                               "width": 1600, "height": 40}},
        "p2_first": {"_page": 2, "text": "B",
                     "region": {"top_left_x": 80, "top_left_y": 200,
                                "width": 1850, "height": 40}},
    }
    sidx = _sidx(payload, ["p1_last", "p2_first"])
    page, bbox, _ = docinspect.object_geometry(
        _obj("p1_last", "p2_first", page=2), sidx)
    assert page == 2
    assert (bbox["x"], bbox["w"]) == (80, 1850)


def test_an_object_with_no_declared_page_takes_the_first_anchors_page():
    """And then only that page's anchors, so the fallback cannot reintroduce
    the mixed-frame union by the back door."""
    payload = {
        "a": {"_page": 3, "text": "x",
              "region": {"top_left_x": 10, "top_left_y": 20,
                         "width": 100, "height": 30}},
        "b": {"_page": 4, "text": "y",
              "region": {"top_left_x": 900, "top_left_y": 40,
                         "width": 500, "height": 30}},
    }
    page, bbox, _ = docinspect.object_geometry(
        _obj("a", "b"), _sidx(payload, ["a", "b"]))
    assert page == 3
    assert (bbox["x"], bbox["w"]) == (10, 100)


def test_several_lines_on_one_page_still_union_into_one_box():
    """The union itself is right and must survive: a paragraph wholly on one
    page is boxed over all of its lines."""
    payload = {
        "l1": {"_page": 1, "text": "one",
               "region": {"top_left_x": 100, "top_left_y": 200,
                          "width": 800, "height": 40}},
        "l2": {"_page": 1, "text": "two",
               "region": {"top_left_x": 90, "top_left_y": 250,
                          "width": 820, "height": 40}},
    }
    page, bbox, preview = docinspect.object_geometry(
        _obj("l1", "l2", page=1), _sidx(payload, ["l1", "l2"]))
    assert page == 1
    assert (bbox["x"], bbox["y"]) == (90, 200)
    assert bbox["x"] + bbox["w"] == 910
    assert bbox["y"] + bbox["h"] == 290
    assert preview == "one two"


def test_an_object_that_realizes_nothing_falls_back_to_its_own_region():
    """Image objects carry their region on props and realize only into the
    cdn stream."""
    obj = {"props": {"page": 2, "region": {"top_left_x": 5, "top_left_y": 6,
                                           "width": 70, "height": 80}},
           "realizations": [{"stream": "cdn", "start": "c1", "end": "c1"}]}
    page, bbox, preview = docinspect.object_geometry(obj, _sidx({}, []))
    assert page == 2 and bbox == {"x": 5, "y": 6, "w": 70, "h": 80}
    assert preview == ""
