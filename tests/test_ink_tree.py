r"""B1/B2 — the merged tree, and the three residual classes that audit it.

Each ink blob attaches to its DEEPEST containing MathPix region. Flat list,
`parent` referencing the region id: physical nesting does not survive a round
trip, a parent reference does. `ink.parent_type` rides on each blob so a
consumer can ask "which of these are body text" in one field instead of
walking.

The tree is the product; the RESIDUALS are the audit, and none of them may be
silently dropped:

  orphan       no containing region — on a page MathPix partly misses, these
               ARE the finding
  straddler    crosses a region boundary — no correct parent exists, and
               forcing one destroys the evidence that the boundary is wrong
               (it is how a clipped integral sign stops being visible)
  tie          two containing regions at the same depth, neither inside the
               other — rare, but it must be a recorded decision rather than
               whichever the sort happened to put first

Counts reconcile to the component total. That is the acceptance criterion and
it is asserted, because a partition that quietly loses blobs would report a
cleaner tree for having dropped the awkward ones.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.ink_tree import ORPHAN, STRADDLER, TIE, build_tree  # noqa: E402


def _r(rid, x0, y0, x1, y1, typ="text"):
    return (rid, (float(x0), float(y0), float(x1), float(y1)), typ)


def _b(bid, x0, y0, x1, y1, area=10):
    return (bid, (float(x0), float(y0), float(x1), float(y1)), area)


# --------------------------------------------------------------- B1: the tree
def test_a_blob_attaches_to_the_deepest_region_containing_it():
    """A cell inside a row inside a table: the parent is the CELL.

    All three contain the blob. Attaching to the outermost would make every
    cell's ink a child of the table and throw away the structure MathPix did
    get right.
    """
    regions = [_r("table#0", 0, 0, 100, 100, "table"),
               _r("row#1", 0, 0, 100, 20, "table_row"),
               _r("cell#2", 0, 0, 30, 20, "simple_cell")]
    tree = build_tree([_b(1, 5, 5, 10, 15)], regions)
    node, = tree["nodes"]
    assert node["parent"] == "cell#2"
    assert node["parent_type"] == "simple_cell"


def test_parent_type_is_carried_so_a_consumer_need_not_walk_the_tree():
    regions = [_r("t#0", 0, 0, 100, 100, "text"),
               _r("d#1", 200, 0, 300, 100, "diagram")]
    tree = build_tree([_b(1, 5, 5, 10, 10), _b(2, 205, 5, 210, 10)], regions)
    assert {n["id"]: n["parent_type"] for n in tree["nodes"]} == {
        1: "text", 2: "diagram"}
    assert tree["by_parent_type"]["text"] == 1


def test_every_blob_is_a_node_or_a_residual_and_the_counts_reconcile():
    """The acceptance criterion, asserted rather than assumed."""
    regions = [_r("a#0", 0, 0, 10, 10), _r("b#1", 5, 0, 15, 10)]
    boxes = [_b(1, 1, 1, 2, 2),          # inside a only
             _b(2, 100, 100, 101, 101),  # orphan
             _b(3, 9, 1, 11, 2),         # crosses a's edge -> straddler
             _b(4, 6, 1, 7, 2)]          # inside both, neither nests -> tie
    tree = build_tree(boxes, regions)
    total = (len(tree["nodes"]) + len(tree["residuals"][ORPHAN])
             + len(tree["residuals"][STRADDLER]) + len(tree["residuals"][TIE]))
    assert total == tree["components"] == 4
    ids = ([n["id"] for n in tree["nodes"]]
           + tree["residuals"][ORPHAN] + tree["residuals"][STRADDLER]
           + tree["residuals"][TIE])
    assert sorted(ids) == [1, 2, 3, 4] and len(ids) == len(set(ids))


# ----------------------------------------------------------- B2: the residuals
def test_a_straddler_is_never_given_a_parent():
    """A blob crossing a boundary is evidence the BOUNDARY is wrong.

    Assigning it to the region it mostly overlaps destroys that evidence, and
    the case it destroys is the clipped tall glyph — a region fitted to the
    body of a line while the integral sign extends above and below it.
    """
    regions = [_r("a#0", 0, 0, 10, 10)]
    tree = build_tree([_b(1, 8, 1, 20, 2)], regions)
    assert tree["residuals"][STRADDLER] == [1]
    assert tree["nodes"] == []


def test_an_orphan_is_reported_rather_than_attached_to_the_nearest_region():
    regions = [_r("a#0", 0, 0, 10, 10)]
    tree = build_tree([_b(1, 500, 500, 501, 501)], regions)
    assert tree["residuals"][ORPHAN] == [1]


def test_a_tie_between_two_regions_at_the_same_depth_is_recorded_not_broken():
    """Two regions contain the blob and neither contains the other. There is
    no deepest, so there is no answer — and picking one silently would make a
    coin toss look like a measurement. The candidates travel with it."""
    regions = [_r("a#0", 0, 0, 10, 10), _r("b#1", 5, 0, 15, 10)]
    tree = build_tree([_b(1, 6, 1, 7, 2)], regions)
    assert tree["residuals"][TIE] == [1]
    assert sorted(tree["tie_candidates"]["1"]) == ["a#0", "b#1"]


def test_nesting_resolves_what_would_otherwise_look_like_a_tie():
    """Two containing regions, but one is inside the other — that is a depth,
    not a tie. Only mutually non-containing candidates are ambiguous."""
    regions = [_r("outer#0", 0, 0, 100, 100), _r("inner#1", 0, 0, 50, 50)]
    tree = build_tree([_b(1, 1, 1, 2, 2)], regions)
    assert tree["residuals"][TIE] == []
    assert tree["nodes"][0]["parent"] == "inner#1"


def test_a_region_with_no_children_is_still_listed():
    """B4 collapses on the tree, so a region that got nothing must appear —
    otherwise "expand this region" has no entry to open and an empty region
    becomes invisible instead of being the finding."""
    regions = [_r("a#0", 0, 0, 10, 10), _r("empty#1", 900, 900, 910, 910)]
    tree = build_tree([_b(1, 1, 1, 2, 2)], regions)
    assert tree["children"]["empty#1"] == []
    assert tree["children"]["a#0"] == [1]


def test_the_tree_does_not_depend_on_input_order():
    regions = [_r("a#0", 0, 0, 10, 10), _r("b#1", 5, 0, 15, 10)]
    boxes = [_b(1, 1, 1, 2, 2), _b(2, 100, 100, 101, 101), _b(3, 6, 1, 7, 2)]
    assert build_tree(boxes, regions) == build_tree(list(reversed(boxes)),
                                                    list(reversed(regions)))
