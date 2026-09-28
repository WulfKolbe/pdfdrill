"""
823 — one MathPix `math` line can carry SEVERAL numbered equations.

MathPix sets a stacked pair of display equations as a single `math` line
holding an `aligned`, and emits one `equation_number` line per row beside it.
The pairing was greedy nearest-pair with each equation taking at most ONE
number, so the second number was dropped and — the half that was invisible —
the surviving equation kept BOTH rows under its own label.

Measured over the 1,506 `lines.json` of the library: 4,826 of the 49,161
numbers the corpus prints never reached a model (9.8%), across 307 documents.
The worked case is BH3FR page 108, section V of the 1985 Heim/Droscher
Formelregister:

    \\[ \\begin{aligned} & r=... \\\\ & m=... \\end{aligned} \\]   (25) y=327
                                                              (26) y=513

The block's box runs y 286..602 and its centre is 444, so (26) at 69 away beat
(25) at 117, and (25) — a number the book prints — existed nowhere in the
model. Splitting on the rows recovers 3,632 numbers corpus-wide and leaves
1,812.

The refusals matter as much as the splits: a row count that does not equal the
number count is a guess about which row owns which number, and that guess is
the misattribution this change exists to remove.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document
from docmodel.modules.page import ingest_lines_json, PageProcessor
from docmodel.modules.equation import (
    EquationProcessor, alignment_rows, standalone_row, number_bands,
)
from docmodel.base_module import ModuleConfig


def _cfg(name):
    return ModuleConfig(title=name, type="application/python", classname=name)


def _build(lines):
    doc = Document()
    doc.meta["bibkey"] = "T"
    ingest_lines_json(doc, lines)
    PageProcessor(_cfg("PageProcessor"), "T").process_document(doc)
    EquationProcessor(_cfg("EquationProcessor"), "T").process_document(doc)
    return sorted((o for o in doc.objects.values() if o.type == "Equation"),
                  key=lambda o: o.props["region"]["top_left_y"])


def _page(math_tex, numbers, *, top=286, height=316):
    """One math line with `numbers` = [(text, y_center)] beside it."""
    lines = [{"text": math_tex, "type": "math",
              "region": {"top_left_x": 112, "top_left_y": top,
                         "width": 900, "height": height}}]
    for text, yc in numbers:
        lines.append({"text": text, "type": "equation_number",
                      "region": {"top_left_x": 1145, "top_left_y": yc - 21,
                                 "width": 60, "height": 42}})
    return {"pages": [{"page": 108, "image_id": "img",
                       "page_height": 2000, "page_width": 1300,
                       "lines": lines}]}


BH3FR_P108 = (
    "\\[ \\begin{aligned} "
    "& r=\\frac{2 n_{r}+1}{2 n_{\\varsigma}+1} \\cdot \\varsigma \\\\ "
    "& m=2 \\sqrt{\\frac{c h}{\\gamma}} \\frac{\\sqrt[4]{2 n}}{\\sqrt{2 n-1}} "
    "\\end{aligned} \\]"
)


def test_two_numbered_rows_become_two_equations():
    eqs = _build(_page(BH3FR_P108, [("(25)", 327), ("(26)", 513)]))
    assert [e.props["refnum"] for e in eqs] == ["25", "26"]
    # each row keeps its OWN formula — the defect was (26) carrying both
    assert eqs[0].props["latex"].startswith("r=")
    assert "m=2" not in eqs[0].props["latex"]
    assert eqs[1].props["latex"].startswith("m=2")
    assert "r=\\frac" not in eqs[1].props["latex"]


def test_each_row_gets_its_own_crop_band():
    eqs = _build(_page(BH3FR_P108, [("(25)", 327), ("(26)", 513)]))
    # cut at the midpoint between the two numbers, not into equal halves
    assert eqs[0].props["region"]["top_left_y"] == 286
    assert eqs[0].props["region"]["height"] == 134
    assert eqs[1].props["region"]["top_left_y"] == 420
    assert eqs[1].props["region"]["height"] == 182
    # the bands tile the block exactly, with no gap and no overlap
    assert (eqs[0].props["region"]["height"]
            + eqs[1].props["region"]["height"]) == 316
    # integer pixels, like every other region: the pipeline reads a region
    # back with `int(...)` on a stringified tiddler field, and "286.0" raises
    # there while "286" does not — which cost these two rows their scan crop.
    for e in eqs:
        assert isinstance(e.props["region"]["top_left_y"], int)
        assert isinstance(e.props["region"]["height"], int)
    assert [e.props["split_index"] for e in eqs] == [0, 1]
    assert [e.props["split_count"] for e in eqs] == [2, 2]


def test_both_rows_surface_on_the_one_line_mathpix_emitted():
    """A Realization is many-to-one, so the split needs no stream surgery."""
    eqs = _build(_page(BH3FR_P108, [("(25)", 327), ("(26)", 513)]))
    surfaces = [r for e in eqs for r in e.realizations if r.role == "surface"]
    assert len(surfaces) == 2
    assert surfaces[0].start == surfaces[1].start


def test_row_count_must_equal_number_count_or_nothing_is_split():
    """Three numbers on a four-row alignment: which row is unnumbered is a
    guess, and a guess here is the misattribution being removed."""
    tex = ("\\[ \\begin{aligned} & a=1 \\\\ & b=2 \\\\ & c=3 \\\\ & d=4 "
           "\\end{aligned} \\]")
    eqs = _build(_page(tex, [("(1)", 320), ("(2)", 420), ("(3)", 520)]))
    assert len(eqs) == 1
    assert "a=1" in eqs[0].props["latex"] and "d=4" in eqs[0].props["latex"]


def test_a_single_number_is_paired_exactly_as_before():
    eqs = _build(_page(BH3FR_P108, [("(26)", 513)]))
    assert len(eqs) == 1
    assert eqs[0].props["refnum"] == "26"
    assert eqs[0].props["split_index"] is None


def test_a_split_number_is_not_handed_to_a_neighbour_as_well():
    """The plan runs before the greedy pairing and reserves what it takes."""
    lines = _page(BH3FR_P108, [("(25)", 327), ("(26)", 513)])
    lines["pages"][0]["lines"].append(
        {"text": "z=0", "type": "math",
         "region": {"top_left_x": 112, "top_left_y": 700,
                    "width": 900, "height": 40}})
    eqs = _build(lines)
    assert [e.props["refnum"] for e in eqs] == ["25", "26", ""]


# ── the row splitter itself ────────────────────────────────────────────────

def test_a_nested_matrix_is_never_cut():
    r"""`\\` inside a pmatrix is that matrix's row break, not the alignment's.

    Cutting there takes the matrix apart and the damage is silent: the rows
    vanish and the formula still compiles. That is exactly how the first
    Formelregister build lost the rows of 51 matrices.
    """
    rows = alignment_rows(
        "\\begin{aligned} & A=\\begin{pmatrix} 1 \\\\ 2 \\end{pmatrix} \\\\ "
        "& B=3 \\end{aligned}")
    assert len(rows) == 2
    assert "\\begin{pmatrix} 1 \\\\ 2 \\end{pmatrix}" in rows[0]


def test_one_equation_environments_are_not_alignments():
    """`cases`, `split` and a bare `array` are ONE equation set over several
    lines; splitting one invents equations the document never printed."""
    for env in ("cases", "split", "array", "pmatrix", "multline"):
        opener = "\\begin{%s}{cc}" % env if env == "array" else "\\begin{%s}" % env
        assert alignment_rows(
            "%s a \\\\ b \\end{%s}" % (opener, env)) == [], env


def test_a_row_that_still_has_an_alignment_point_keeps_a_home():
    r"""An `&` outside an alignment environment is a fatal `Misplaced
    alignment tab`; an escaped `\&` is just an ampersand."""
    assert standalone_row("& a &= b + c") == "\\begin{aligned} a &= b + c \\end{aligned}"
    assert standalone_row("& a \\& b") == "a \\& b"


def test_bands_stay_inside_the_block():
    bands = number_bands(
        {"top_left_x": 0, "top_left_y": 100, "width": 10, "height": 100},
        [110.0, 150.0, 190.0])
    assert bands[0]["top_left_y"] == 100
    assert bands[-1]["top_left_y"] + bands[-1]["height"] == 200
    assert all(b["height"] >= 0 for b in bands)
