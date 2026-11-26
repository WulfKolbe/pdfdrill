r"""The free Markdown of a paper with source keeps its tables, references and
title (the owner, 2026-11-26).

The owner drilled arXiv 2307.04341v1 — its LaTeX source is free — and then
bought a MathPix reading "because the markdown from the LaTeX was full of LaTeX
macros and I needed the correct text with all math for ChatGPT". Measured
against that MathPix reading of the same paper:

                        free (from the source)     MathPix
    table rows               0                       32
    References section       absent                  present
    title heading            absent                  present

None of it was missing from the MODEL — 5 Table objects with their `tabular`,
25 Reference objects with their `.bbl` text, and `\title` in `doc.meta`. The
projector had no way to say any of it: a Table without MathPix's measured
`cells` came out as its caption alone, `Reference` had no branch at all, and
the title came only from a Title OBJECT, which a source model does not have.

After this, the same paper: 39 table rows, 25 references, its title.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from docmodel.core import Document, DocObject                # noqa: E402
from docops.base import OperatorConfig                       # noqa: E402
from docops.projectors.markdown import MarkdownProjector, _bbl_text  # noqa: E402


def _doc(*objs, meta=None):
    d = Document()
    d.meta["bibkey"] = "doc"
    # A model BUILT FROM THE SOURCE, which is the case this file is about:
    # `source_counts` is the positive marker `_is_latex_source` reads, and it
    # is what lets `$…$` in a cell stay maths rather than be escaped as prose.
    d.meta["source_counts"] = {"tables": 1}
    d.meta.update(meta or {})
    for i, o in enumerate(objs):
        o.props.setdefault("flow_index", i)
        d.add(o)
    return d


def _md(doc):
    return MarkdownProjector(OperatorConfig(
        op="projector", classname="MarkdownProjector",
        params={"front_matter": False})).project(doc)


def _pipe_rows(md):
    return [l for l in md.splitlines() if l.startswith("|")]


# ── tables ────────────────────────────────────────────────────────────────

TABULAR = r"""\begin{tabular}{c|c}
        \hline
        {\bf Name} & {\bf Description}\\
        \hline
        Target Data & Target character image \\
        SegNet Feature & Feature data at $64\times64$ size \\
        \hline
\end{tabular}"""


def test_a_table_from_the_source_becomes_a_pipe_table():
    doc = _doc(DocObject(type="Table", props={
        "latex_code": TABULAR, "caption": "Inputs of the ExtractNet."}))
    out = _md(doc)
    rows = _pipe_rows(out)
    assert rows[0] == "| **Name** | **Description** |"
    assert rows[1] == "| --- | --- |"
    assert "| Target Data | Target character image |" in rows
    assert any("$64\\times64$" in r for r in rows), "maths in a cell is kept"
    assert "\\hline" not in out
    assert "Inputs of the ExtractNet." in out, "the caption still comes with it"


def test_a_span_keeps_its_columns():
    r"""`\multicolumn{2}{c}{CCSEDB}` heads TWO columns. Written as one cell it
    pushed every label after it one column left: on 2307.04341v1 RHSEDB sat
    over column 3 and heads 4 and 5."""
    tab = (r"\begin{tabular}{lcccc}"
           r" & \multicolumn{2}{c}{CCSEDB} & \multicolumn{2}{c}{RHSEDB} \\"
           r" & a & b & c & d \\ \end{tabular}")
    rows = _pipe_rows(_md(_doc(DocObject(type="Table", props={"latex_code": tab}))))
    assert rows[0] == "|  | CCSEDB |  | RHSEDB |  |"
    assert rows[2] == "|  | a | b | c | d |"


def test_bold_has_no_space_inside_its_markers():
    """`**Our Method **` is not bold in Markdown — CommonMark wants no space
    just inside the markers, and `\\textbf{Our Method }` has one."""
    tab = r"\begin{tabular}{cc} \textbf{Our Method } & \textbf{0.924} \\ \end{tabular}"
    rows = _pipe_rows(_md(_doc(DocObject(type="Table", props={"latex_code": tab}))))
    assert rows[0] == "| **Our Method** | **0.924** |"


def test_a_brace_group_and_an_escaped_ampersand_do_not_split():
    tab = (r"\begin{tabular}{cc} \makecell{two \\ lines} & R\&D \\"
           r" x & y \\ \end{tabular}")
    rows = _pipe_rows(_md(_doc(DocObject(type="Table", props={"latex_code": tab}))))
    assert len(rows) == 3, rows                     # header, rule, one body row
    assert "R&D" in rows[0] or "R\\&D" in rows[0]


def test_measured_cells_still_win_over_the_tabular():
    """MathPix's measured grid is the reading of the PAGE; the tabular is the
    author's intent. Where both exist, nothing changes."""
    doc = _doc(DocObject(type="Table", props={
        "latex_code": TABULAR,
        "cells": [{"row": 0, "col": 0, "text": "M"}, {"row": 0, "col": 1, "text": "N"}]}))
    assert _pipe_rows(_md(doc))[0] == "| M | N |"


def test_a_table_that_cannot_be_split_keeps_its_caption():
    doc = _doc(DocObject(type="Table", props={
        "latex_code": r"\includegraphics{t.png}", "caption": "A table image."}))
    out = _md(doc)
    assert not _pipe_rows(out) and "A table image." in out


# ── references ───────────────────────────────────────────────────────────

def _ref(n, key, text):
    return DocObject(type="Reference", props={
        "number": n, "citekey": key, "raw_text": text, "ref_source": "bbl"})


def test_the_bibliography_is_the_last_section():
    doc = _doc(DocObject(type="Paragraph", props={"text": "Body."}),
               _ref(2, "b", "Second, B. 2020. A title."),
               _ref(1, "a", "First, A. 2019. VoxelMorph: x. 38(8): 1788--1800."))
    out = _md(doc)
    tail = out[out.index("## References"):]
    assert tail.index("First, A.") < tail.index("Second, B."), "in .bbl order"
    assert "1. [a] First, A." in tail and "2. [b] Second, B." in tail
    assert "1788–1800" in tail


def test_a_citation_can_be_followed_to_its_entry():
    """The body cites by key — "character generation [liu2021fontrl]" on
    2307.04341v1 — so the entry carries the key, or the reader has no way from
    one to the other."""
    doc = _doc(DocObject(type="Paragraph", props={"text": "See [liu2021fontrl]."}),
               _ref(1, "liu2021fontrl", "Liu, Y.; and Lian, Z. 2021. FontRL."))
    assert "[liu2021fontrl] Liu, Y.; and Lian, Z. 2021" in _md(doc)


def test_a_printed_references_list_is_not_repeated():
    """A model built from a READING carries the printed list as a Section of
    its own, already in the flow — `reference_section_ids` is the projectors'
    shared test for that."""
    sec = DocObject(type="Section", props={"caption": "References", "level": 1})
    doc = _doc(sec, _ref(1, "a", "First, A. 2019."))
    assert _md(doc).count("References") == 1


def test_a_bbl_entry_is_text_not_latex():
    assert _bbl_text(r"Imaging \& Visualization, 6(3): 248--252.") == \
        "Imaging & Visualization, 6(3): 248–252."
    assert _bbl_text(r"{VoxelMorph}: a~frame---work") == "VoxelMorph: a frame—work"
    assert _bbl_text(r"as $a--b$ shows") == "as $a--b$ shows", "maths is left alone"


# ── title ────────────────────────────────────────────────────────────────

def test_a_source_models_title_and_authors_head_the_file():
    doc = _doc(DocObject(type="Section", props={"caption": "Abstract", "level": 1}),
               meta={"title": "Stroke Extraction of Chinese Character",
                     "authors": [r"Meng Li\textsuperscript{\rm1}, "
                                 r"Yahan Yu\textsuperscript{\rm1,\rm2}"]})
    out = _md(doc)
    assert out.startswith("# Stroke Extraction of Chinese Character\n\nMeng Li, Yahan Yu")
    assert "textsuperscript" not in out


def test_no_title_no_heading():
    out = _md(_doc(DocObject(type="Paragraph", props={"text": "Body."})))
    assert not out.startswith("#")
