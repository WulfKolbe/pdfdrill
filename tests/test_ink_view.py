"""P4 — the payload split that makes an inkdrill-scale page viewable.

3,390-4,105 components per page, 33-154 of them structural. One DOM div each is
a rendering problem before it is a filtering one, and a page uniformly covered
in rectangles shows nothing. So: tens keep the DOM, thousands become one flat
array for a single canvas, and the default view is the suspicious ones.

The six suspicion classes are POSITIVE signals. "We could not tell" must never
count, or every unmeasured element is suspicious and the view it exists to keep
small is the whole page again.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.ink_view import (CATEGORIES, DEFAULT_OFF, HOLE_DISAGREE, INVERTED,
                               NON_WHITE, NO_REGION, REJECTED, STRADDLES,
                               blob_arrays, category, is_structure, suspicions)


# ------------------------------------------------------------------ category
def test_inkdrill_states_the_category_and_it_wins():
    assert category("Blob", {"ink.kind": "tick"}) == "tick"
    assert category("Picture", {"ink.kind": "rule"}) == "rule"


def test_an_unstated_category_is_inferred_from_the_type():
    assert category("TableCell", {}) == "cell"
    assert category("Diagram", {}) == "raster"
    assert category("Table", {}) == "frame"
    assert category("Blob", {"ink.is_rule": True}) == "rule"


def test_anything_unrecognised_is_a_glyph_and_glyphs_are_off_by_default():
    assert category("Blob", {}) == "glyph"
    assert category("Whatever", None) == "glyph"
    assert "glyph" in DEFAULT_OFF and "frame" not in DEFAULT_OFF


def test_a_bogus_stated_category_does_not_leak_into_the_toggles():
    """A toggle set is a fixed vocabulary; an unknown value must fall back."""
    assert category("Blob", {"ink.kind": "wibble"}) == "glyph"


# ---------------------------------------------------------------- suspicion
def test_each_of_the_six_classes_fires_on_its_own_signal():
    assert suspicions({}, has_region=False) == [NO_REGION]
    assert suspicions({"ink.straddles_region": True}, has_region=True) == [STRADDLES]
    assert suspicions({"ink.ground": "grey"}, has_region=True) == [NON_WHITE]
    assert suspicions({"ink.classification": "rejected"}, has_region=True) == [REJECTED]
    assert suspicions({"ink.body_height": -3}, has_region=True) == [INVERTED]
    assert suspicions({"ink.holes": 52, "ink.holes_expected": 48},
                      has_region=True) == [HOLE_DISAGREE]


def test_an_ordinary_element_is_not_suspicious():
    assert suspicions({"ink.ground": "white", "ink.body_height": 9,
                       "ink.holes": 4, "ink.holes_expected": 4},
                      has_region=True) == []


def test_absent_measurements_are_not_suspicion():
    """The distinction the view depends on: unmeasured is not the same as wrong.
    An element inkdrill never looked at must not fill the default view."""
    assert suspicions({}, has_region=True) == []
    assert suspicions(None, has_region=True) == []
    assert suspicions({"ink.holes": 4}, has_region=True) == []      # no expectation
    assert suspicions({"ink.body_height": 0}, has_region=True) == []  # 0 is not inverted


def test_several_classes_can_fire_at_once():
    got = suspicions({"ink.ground": "grey", "ink.classification": "rejected"},
                     has_region=False)
    assert set(got) == {NO_REGION, NON_WHITE, REJECTED}


# ------------------------------------------------------------------ the split
def test_every_pdfdrill_object_keeps_its_dom_node():
    """The blob layer is for INKDRILL components. Defaulting the other way
    routed `Formula` into the canvas and dropped it from the inspector on all
    3,300 existing documents, none of which have any inkdrill data."""
    for t in ("Table", "TableCell", "Section", "Equation", "Picture", "Formula",
              "Reference", "Link", "Sidenote", "AnythingNewWeAddLater"):
        assert is_structure(t, {}) is True, t


def test_an_inkdrill_component_is_a_blob():
    assert is_structure("Blob", {}) is False
    assert is_structure("Component", None) is False
    assert is_structure("Glyph", {}) is False


def test_inkdrill_can_promote_a_blob_to_structure():
    assert is_structure("Blob", {"ink.structural": True}) is True


def test_the_blob_layer_is_flat_parallel_arrays_not_objects():
    """4,000 dicts is ~1 MB of JSON and 4,000 GC objects in the client."""
    blobs = [{"id": f"b{i}", "cat": "glyph",
              "bbox": {"x": i, "y": 2 * i, "w": 3, "h": 4},
              "suspicions": ([NO_REGION] if i % 100 == 0 else [])}
             for i in range(4000)]
    a = blob_arrays(blobs)
    assert a["n"] == 4000
    for k in ("x", "y", "w", "h", "cat", "susp", "id"):
        assert len(a[k]) == 4000, k
    assert a["x"][10] == 10 and a["y"][10] == 20
    assert sum(a["susp"]) == 40                      # one in a hundred
    assert a["cat"][0] == CATEGORIES.index("glyph")
    assert a["categories"] == list(CATEGORIES)


def test_an_empty_blob_layer_is_empty_arrays_not_an_error():
    a = blob_arrays([])
    assert a["n"] == 0 and a["x"] == [] and a["categories"] == list(CATEGORIES)


def test_a_blob_with_no_bbox_still_occupies_its_slot():
    """Parallel arrays only work if every blob contributes exactly one entry."""
    a = blob_arrays([{"id": "b0"}, {"id": "b1", "bbox": {"x": 5, "y": 6, "w": 1, "h": 1}}])
    assert a["n"] == 2 and a["x"] == [0.0, 5.0] and a["id"] == ["b0", "b1"]
