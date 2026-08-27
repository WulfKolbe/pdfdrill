"""248 — ListProcessor reads MathPix's typed list_item containers.

`"list_item"` appeared nowhere in src/: 80,035 lines across 882 of 1,350
documents, skipped by `type != "text": continue`. The container carries the
STRUCTURE, not the words — 53,716 of the 80,035 have empty text and
children_ids pointing at the lines that hold them. So the old lexical scan was
not missing the items (the children are text lines and do start with markers);
it was missing their BOUNDARIES.
"""
from docmodel.core import Document, Stream
from docmodel.modules.list_items import ListProcessor
from docmodel.modules.paragraph import _BREAK_TYPES


def _doc(lines):
    doc = Document()
    st = doc.ensure_stream("mathpix_lines")
    for l in lines:
        st.append(**l)
    return doc


def _proc():
    p = ListProcessor.__new__(ListProcessor)
    p.bibkey = "T"
    p.LINES_STREAM = "mathpix_lines"
    p.counters = {}
    return p


def test_a_container_joins_its_continuation_lines():
    """The whole gain. 137,439 text children corpus-wide carry NO marker: each
    was a paragraph fragment under the old scan, and the item it belonged to
    stopped at its first line."""
    doc = _doc([
        {"id": "c", "type": "list_item", "text": "", "children_ids": ["a", "b"]},
        {"id": "a", "type": "text", "text": "- By providing two regularisations we can"},
        {"id": "b", "type": "text", "text": "describe both the spin-foam models."},
    ])
    items = _proc().find_items(doc)
    assert len(items) == 1, items
    assert items[0]["marker"] == "-"
    assert items[0]["content"] == \
        "By providing two regularisations we can describe both the spin-foam models."
    assert items[0]["source"] == "typed"


def test_a_claimed_child_is_not_counted_twice():
    """The child is a `text` line starting with a marker — exactly what the
    lexical path also matches."""
    doc = _doc([
        {"id": "c", "type": "list_item", "text": "", "children_ids": ["a"]},
        {"id": "a", "type": "text", "text": "- only once"},
    ])
    items = _proc().find_items(doc)
    assert len(items) == 1 and items[0]["source"] == "typed"


def test_a_container_with_its_own_text():
    """26,319 of 80,035 carry the text themselves."""
    doc = _doc([{"id": "c", "type": "list_item",
                 "text": "1. the first thing", "children_ids": []}])
    items = _proc().find_items(doc)
    assert items[0]["marker"] == "1." and items[0]["content"] == "the first thing"


def test_an_item_with_no_lexical_marker_is_still_an_item():
    """12,013 containers carry text with NO recognisable marker. The lexical
    scan could never have found them."""
    doc = _doc([{"id": "c", "type": "list_item",
                 "text": "no bullet glyph at all here", "children_ids": []}])
    items = _proc().find_items(doc)
    assert len(items) == 1
    assert items[0]["content"] == "no bullet glyph at all here"


def test_non_text_children_are_claimed_but_not_flattened():
    """7,148 math and 1,163 equation_number children corpus-wide. An equation
    inside a list item is an Equation; folding it into the prose would lose
    it."""
    doc = _doc([
        {"id": "c", "type": "list_item", "text": "", "children_ids": ["m", "t"]},
        {"id": "m", "type": "math", "text": "x^2 = 1"},
        {"id": "t", "type": "text", "text": "- and therefore"},
    ])
    items = _proc().find_items(doc)
    assert len(items) == 1
    assert "x^2" not in items[0]["content"]
    assert items[0]["child_ids"] == ["t"]        # the math child is not claimed


def test_lines_outside_any_container_still_use_the_lexical_path():
    """The only thing that works on documents MathPix typed no list_item for
    — 468 of 1,350 have none at all."""
    doc = _doc([{"id": "x", "type": "text", "text": "- a loose bullet"}])
    items = _proc().find_items(doc)
    assert len(items) == 1 and items[0]["source"] == "lexical"


def test_an_empty_container_yields_nothing():
    doc = _doc([{"id": "c", "type": "list_item", "text": "", "children_ids": []}])
    assert _proc().find_items(doc) == []


def test_list_item_now_breaks_a_paragraph():
    """It was in neither _PROSE_TYPES nor _BREAK_TYPES, so it silently welded
    the text before a list to the text after it."""
    assert "list_item" in _BREAK_TYPES
