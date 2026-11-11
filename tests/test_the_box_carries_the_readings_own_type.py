r"""A rectangle is labelled with the word the READING uses for it.

OWNER, 2026-11-11, looking at the inspect.html built from GLYPHDRILL3's
reading: "I see ... with some areas called reading record??"

WHAT WAS WRONG. A record no module recognises is stored as a `ReadingRecord`
(docmodel.modules.unclaimed) because `DocObject.type` is a closed vocabulary
that five readers enforce — `column` or `gd3_block` in that field would be
refused. That is a STORAGE decision, and it leaked onto the page: the box tag,
the ELEMENTS badge and the inspector header all read "ReadingRecord" where the
reading says `column`, `gd3_white`, `gd3_block`. The label named OUR container
instead of THEIR stage — in a view whose whole purpose is adjusting that stage.

THE RULE. `lines_type` is passed through verbatim to the label: not prettified,
not title-cased, not mapped onto a type this repo happens to know. Same reason
the region is not re-scaled or clipped — a viewer that renames its input is
useless for correcting the thing that produced it.

`obj["type"]` itself is untouched, so `ink_view.category`, `is_structure`,
`layoutgeom.not_printed` and the client's renderer registry still see the
object they were written for. Only the displayed record changes.
"""
from pdfdrill.docinspect import build_stream_index, collect_elements


def _model(records):
    """A model in the shape `model_io.load_model` returns, one page."""
    anchors = [f"a{i}" for i in range(len(records))]
    objects = []
    for aid, rec in zip(anchors, records):
        objects.append({
            "id": f"obj-{aid}",
            "type": rec.pop("_obj_type", "ReadingRecord"),
            "props": {"page": 1, "lines_type": rec.get("type"),
                      "region": rec["region"], "text": rec.get("text", "")},
            "realizations": [{"stream": "mathpix_lines", "start": aid,
                              "end": aid, "role": "surface"}],
        })
    return {
        "meta": {"pages": [{"page": 1, "page_width": 3307, "page_height": 4677}]},
        "objects": objects,
        "streams": {"mathpix_lines": {
            "anchors": anchors,
            "payload": {aid: dict(r, _page=1) for aid, r in zip(anchors, records)},
        }},
    }


GD3 = [
    {"type": "column", "text": "",
     "region": {"top_left_x": 389, "top_left_y": 1667,
                "width": 1222, "height": 2667}},
    {"type": "gd3_white", "text": "",
     "region": {"top_left_x": 1622, "top_left_y": 1667,
                "width": 61, "height": 2667}},
    {"type": "gd3_block", "text": "block 1",
     "region": {"top_left_x": 389, "top_left_y": 1667,
                "width": 1222, "height": 667}},
]


def _elements(records):
    model = _model([dict(r) for r in records])
    els, _pages = collect_elements(model, build_stream_index(model))
    return els


def test_the_tag_on_the_box_is_the_readings_own_word():
    """`e.type` is what the overlay prints in the box tag and the tree badge."""
    kinds = sorted(e["type"] for e in _elements(GD3))
    assert kinds == ["column", "gd3_block", "gd3_white"], kinds


def test_a_record_with_no_text_is_not_labelled_readingrecord():
    """The label falls back to the type when there is no prose, and a `column`
    carries none — which is how the owner came to see "readingrecord" twice
    over, once as the badge and once as the name beside it."""
    labels = {e["type"]: e["label"] for e in _elements(GD3)}
    assert labels["column"] == "column"
    assert labels["gd3_white"] == "gd3_white"
    assert labels["gd3_block"] == "block 1"     # prose wins when there is prose
    assert not any("readingrecord" in l.lower() for l in labels.values())


def test_the_type_is_not_prettified_on_the_way_through():
    """Verbatim: no title-casing, no underscore-to-space, no mapping onto a
    type this repo knows. `gd3_white` is the name the C stage emits and the
    name the owner is looking for on screen."""
    assert "gd3_white" in {e["type"] for e in _elements(GD3)}


def test_a_recognised_object_keeps_its_own_type():
    """A Paragraph is still a Paragraph — this touches only the records that
    had no word of their own, and `lines_type` is ignored for the rest."""
    rec = dict(GD3[2]); rec["_obj_type"] = "Paragraph"
    els = _elements([rec])
    assert [e["type"] for e in els] == ["Paragraph"]


def test_an_untyped_record_still_says_what_it_is():
    """A reading that names no type at all: the stored type is all there is,
    and the label must not become empty — an unlabelled rectangle is worse
    than one labelled with our own container."""
    rec = {"type": None, "text": "",
           "region": {"top_left_x": 1, "top_left_y": 2, "width": 3, "height": 4}}
    els = _elements([rec])
    assert els[0]["type"] == "ReadingRecord"
    assert els[0]["label"]
