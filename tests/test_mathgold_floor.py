"""The floor: what a born-digital text layer alone recovers of an equation.

The floor is not a recogniser. It reads the characters inside the equation's
rectangle, in reading order, and joins them left to right — no scripts, no
fractions, no structure at all. Its score is the number any real recogniser
has to beat, and the number M2.x is measured against.

Scoring uses LgEval, which compares two label graphs over THE SAME primitive
set: node ids are the correspondence, not a coincidence. Gold symbols come
from LaTeX and floor symbols come from PDF characters, so that correspondence
does not exist a priori — it has to be established and stated. `align_labels`
establishes it by sequence alignment over normalised labels, and everything
LgEval then reports is conditional on that alignment. Tests below pin the
alignment's behaviour precisely because the whole measurement rests on it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mathgold.floor import (  # noqa: E402
    align_labels,
    chars_in_box,
    chars_to_slt,
    lg_pair,
    reading_order,
    region_box,
    to_symbol,
    unmapped_commands,
)
from mathgold.slt import parse_latex_slt  # noqa: E402


def _ch(text, x0, top, size=10.0, w=5.0, h=10.0):
    return {"text": text, "x0": x0, "x1": x0 + w, "top": top,
            "bottom": top + h, "size": size}


# --------------------------------------------------------------- geometry
def test_region_box_scales_mathpix_pixels_to_pdf_points():
    # MathPix reports 2067x2924 px for a 595.276x841.89 pt page.
    box = region_box({"top_left_x": 781, "top_left_y": 1155,
                      "width": 435, "height": 200},
                     page_px=(2067, 2924), page_pt=(595.276, 841.89))
    assert [round(v, 1) for v in box] == [224.9, 332.6, 350.2, 390.1]


def test_chars_in_box_excludes_a_char_outside_the_rectangle():
    box = (10.0, 10.0, 60.0, 30.0)
    inside = _ch("a", 20, 15)
    below = _ch("b", 20, 100)
    right = _ch("c", 200, 15)
    got = chars_in_box([inside, below, right], box, pad=1.0)
    assert [c["text"] for c in got] == ["a"]


# --------------------------------------------------------------- reading order
def test_reading_order_keeps_a_subscript_beside_its_base_not_at_the_end():
    """`J_x = y` — the subscript sits below the baseline but is READ next.

    A naive row clustering that keys on `top` puts every subscript of an
    equation into its own row, and the flat reading comes out as
    `J=y...x` with all the scripts swept to the end. That is a sorting bug
    being reported as a recognition floor.
    """
    chars = [_ch("J", 10, 100),
             _ch("x", 16, 104, size=7.0, h=7.0),   # subscript: lower, smaller
             _ch("=", 25, 100),
             _ch("y", 35, 100)]
    assert [c["text"] for c in reading_order(chars)] == ["J", "x", "=", "y"]


def test_reading_order_reads_a_second_row_after_the_first():
    chars = [_ch("b", 40, 100), _ch("a", 10, 100),
             _ch("d", 40, 130), _ch("c", 10, 130)]
    assert [c["text"] for c in reading_order(chars)] == ["a", "b", "c", "d"]


# --------------------------------------------------------------- flat SLT
def test_chars_to_slt_is_a_flat_right_chain_with_no_structure():
    slt = chars_to_slt([_ch("a", 10, 10), _ch("b", 20, 10), _ch("c", 30, 10)])
    assert [n.label for n in slt.nodes] == ["a", "b", "c"]
    assert [(e.parent, e.child, e.relation) for e in slt.edges] == [
        (slt.nodes[0].id, slt.nodes[1].id, "Right"),
        (slt.nodes[1].id, slt.nodes[2].id, "Right"),
    ]


# --------------------------------------------------------------- vocabulary
def test_to_symbol_maps_a_known_command_and_leaves_an_unknown_one_alone():
    assert to_symbol(r"\times") == "×"
    assert to_symbol(r"\hbar") == "ℏ"
    # Rule 5: an unmapped command is NOT given a plausible symbol. It stays
    # itself, mismatches, and is counted — the gap stays visible.
    assert to_symbol(r"\coloneq") == r"\coloneq"
    assert to_symbol("J") == "J"


def test_unmapped_commands_reports_what_the_table_does_not_cover():
    slt = parse_latex_slt(r"a \times b \coloneq c")
    assert unmapped_commands(slt) == {r"\coloneq"}


# --------------------------------------------------------------- alignment
def test_align_labels_pairs_identical_sequences_positionally():
    assert align_labels(["a", "b", "c"], ["a", "b", "c"]) == [(0, 0), (1, 1), (2, 2)]


def test_align_labels_absorbs_an_insertion_without_shifting_the_rest():
    """The floor emits a spurious character (a combining accent, a `(cid:18)`).

    Positional comparison would then mark every later symbol wrong. The
    alignment must absorb the insertion so the rest still corresponds.
    """
    pairs = align_labels(["a", "b", "c"], ["a", "X", "b", "c"])
    assert pairs == [(0, 0), (1, 2), (2, 3)]


def test_align_labels_drops_a_gold_symbol_the_floor_never_produced():
    pairs = align_labels(["a", "b", "c"], ["a", "c"])
    assert pairs == [(0, 0), (2, 1)]


# --------------------------------------------------------------- lg emission
def test_lg_pair_gives_matched_nodes_the_same_id_in_both_graphs():
    """LgEval's node ids ARE the primitive correspondence.

    If the two files number their nodes independently, LgEval silently
    compares symbol 3 of one against symbol 3 of the other and reports a
    number that means nothing. The ids must come from the alignment.
    """
    gold = parse_latex_slt("a b")
    floor = chars_to_slt([_ch("X", 5, 10), _ch("a", 10, 10), _ch("b", 20, 10)])
    gold_lg, floor_lg, stats = lg_pair(gold, floor)

    gold_ids = {ln.split(",")[2].strip(): ln.split(",")[1].strip()
                for ln in gold_lg.splitlines() if ln.startswith("N,")}
    floor_ids = {ln.split(",")[2].strip(): ln.split(",")[1].strip()
                 for ln in floor_lg.splitlines() if ln.startswith("N,")}
    assert gold_ids["a"] == floor_ids["a"]
    assert gold_ids["b"] == floor_ids["b"]
    assert stats["matched"] == 2
    assert stats["floor_only"] == 1
    assert stats["gold_only"] == 0


def test_lg_pair_counts_a_style_wrapper_as_a_gold_node_with_no_ink():
    r"""`\mathcal` is a typeface, not a symbol: nothing in the PDF corresponds
    to it, so no reader of the page could ever recover it. It is reported
    separately (`no_ink`) rather than silently dropped or silently charged."""
    gold = parse_latex_slt(r"\mathcal{H}")
    floor = chars_to_slt([_ch("H", 10, 10)])
    _g, _f, stats = lg_pair(gold, floor)
    assert stats["matched"] == 1
    assert stats["no_ink"] == 1


def test_lg_pair_keeps_an_unmatched_node_so_lgeval_can_call_it_absent():
    """Measured, not assumed: LgEval takes the UNION of the two node sets and
    scores a node only one file declares as `ABSENT` (`nNodes,3` for a 3-vs-2
    pair). Dropping unmatched nodes would delete precisely the symbols the
    floor missed — the largest part of the error — and report a better score
    for having hidden them. So they are kept, with ids disjoint between the
    two files so nothing pairs up by accident.
    """
    gold = parse_latex_slt("a b")
    floor = chars_to_slt([_ch("X", 5, 10), _ch("a", 10, 10), _ch("b", 20, 10)])
    gold_lg, floor_lg, _ = lg_pair(gold, floor)

    floor_labels = [ln.split(",")[2].strip() for ln in floor_lg.splitlines()
                    if ln.startswith("N,")]
    assert "X" in floor_labels
    gold_only_ids = {ln.split(",")[1].strip() for ln in gold_lg.splitlines()
                     if ln.startswith("N,")}
    floor_only_ids = {ln.split(",")[1].strip() for ln in floor_lg.splitlines()
                      if ln.startswith("N,")}
    # the X's id must not collide with any gold id, or LgEval pairs it with a
    # gold symbol it has nothing to do with
    assert floor_only_ids - gold_only_ids == {"f_c0"}
    assert gold_only_ids <= floor_only_ids


def test_lg_pair_edges_only_reference_nodes_the_file_declares():
    """A `.lg` whose edge names an undeclared id is a file LgEval cannot read."""
    gold = parse_latex_slt(r"\frac{a}{b} c")
    floor = chars_to_slt([_ch("a", 10, 10), _ch("b", 10, 25), _ch("c", 30, 18)])
    gold_lg, floor_lg, _ = lg_pair(gold, floor)
    for text in (gold_lg, floor_lg):
        declared = {ln.split(",")[1].strip() for ln in text.splitlines()
                    if ln.startswith("N,")}
        for ln in text.splitlines():
            if ln.startswith("E,"):
                p, c = ln.split(",")[1].strip(), ln.split(",")[2].strip()
                assert p in declared and c in declared, ln
