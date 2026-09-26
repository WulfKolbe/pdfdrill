"""816 — the Markdown projector, and the image LINK it exists to emit.

"my Markdown editor can follow CDN links, we have some example with crop links
at the server for these, that was the intend function!"
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from docmodel.core import Document, DocObject                # noqa: E402
from docops.base import OperatorConfig                       # noqa: E402
from docops.projectors.markdown import (                     # noqa: E402
    MarkdownProjector, _unwrap_latex_wrapper, _unwidget)

TRANSCLUSION = re.compile(r"\{\{[^{}]*\|\|[A-Z]{2,4}\}\}")
BK = "doc"


def _doc(*objs, meta=None):
    d = Document()
    d.meta["bibkey"] = BK
    d.meta.update(meta or {})
    for i, o in enumerate(objs):
        o.props.setdefault("flow_index", i)
        d.add(o)
    return d


def _md(doc, **params):
    params.setdefault("front_matter", False)
    return MarkdownProjector(OperatorConfig(
        op="projector", classname="MarkdownProjector", params=params)).project(doc)


# ── images are links, and the local crop comes first ─────────────────────────

def test_a_figure_links_to_its_crop(tmp_path):
    """The crop is named after the TIDDLER TITLE, so the projector must use the
    same title scheme — `title_for` — or the link points at nothing."""
    (tmp_path / "doc_PIC_0001.jpg").write_bytes(b"\xff\xd8\xff")
    doc = _doc(DocObject(type="Picture", props={"caption": "A photo"}))
    out = _md(doc, crops_dir=str(tmp_path), crops_base="report-crops")
    assert "![A photo](report-crops/doc_PIC_0001.jpg)" in out
    assert "*A photo*" in out


def test_crops_base_may_be_a_URL_so_the_same_markdown_reads_from_a_server(tmp_path):
    (tmp_path / "doc_PIC_0001.jpg").write_bytes(b"x")
    doc = _doc(DocObject(type="Picture", props={}))
    out = _md(doc, crops_dir=str(tmp_path),
              crops_base="http://ser7:8787/a/doc/report-crops")
    assert "](http://ser7:8787/a/doc/report-crops/doc_PIC_0001.jpg)" in out


def test_the_local_crop_beats_the_cdn_url(tmp_path):
    """Not a preference: MathPix retired the crop CDN and every `cdn_url` on
    disk answers HTTP 500, so preferring it shows a broken image where a working
    file exists."""
    (tmp_path / "doc_PIC_0001.jpg").write_bytes(b"x")
    doc = _doc(DocObject(type="Picture",
                         props={"cdn_url": "https://cdn.mathpix.com/x.jpg"}))
    out = _md(doc, crops_dir=str(tmp_path))
    assert "report-crops/doc_PIC_0001.jpg" in out
    assert "cdn.mathpix.com" not in out


def test_the_cdn_url_is_used_when_there_is_no_crop(tmp_path):
    """A link that might work beats no link."""
    doc = _doc(DocObject(type="Picture",
                         props={"cdn_url": "https://cdn.mathpix.com/x.jpg"}))
    out = _md(doc, crops_dir=str(tmp_path))
    assert "![" in out and "https://cdn.mathpix.com/x.jpg" in out


def test_no_crops_dir_means_no_crop_link(tmp_path):
    """A link to a file that is not there is the failure this replaces, so the
    existence check is the point — never assumed."""
    doc = _doc(DocObject(type="Picture", props={}))
    assert "![" not in _md(doc)


def test_a_figure_with_no_image_keeps_its_caption():
    doc = _doc(DocObject(type="Picture", props={"caption": "Fig 1. A thing"}))
    out = _md(doc)
    assert "Fig 1. A thing" in out


# ── tables ───────────────────────────────────────────────────────────────────

def _table(cells, n_rows, n_cols, **extra):
    props = {"cells": cells, "n_rows": n_rows, "n_cols": n_cols}
    props.update(extra)
    return DocObject(type="Table", props=props)


def test_a_table_becomes_a_pipe_table():
    """From `props["cells"]`, NOT from `TableRow.children` — the model hangs
    every row AND every cell off the Table itself, so rows have no children and
    walking the tree yields nothing. Measured: a 4x2 table with 12 children and
    0 row-children produced 0 pipe rows on the first run."""
    cells = [{"row": 0, "col": 0, "text": "Functions"},
             {"row": 0, "col": 1, "text": "Description"},
             {"row": 1, "col": 0, "text": "forward()"},
             {"row": 1, "col": 1, "text": "sends a delta"}]
    out = _md(_doc(_table(cells, 2, 2)))
    assert "| Functions | Description |" in out
    assert "| --- | --- |" in out
    assert "| forward() | sends a delta |" in out


def test_a_pipe_inside_a_cell_is_escaped():
    cells = [{"row": 0, "col": 0, "text": "a|b"}, {"row": 0, "col": 1, "text": "c"}]
    out = _md(_doc(_table(cells, 1, 2)))
    assert r"a\|b" in out


def test_a_spanned_cell_is_written_once_not_repeated():
    """Markdown pipe tables have no spans; repeating the text would state a
    value the document does not have."""
    cells = [{"row": 0, "col": 0, "text": "Both", "col_span": 2},
             {"row": 1, "col": 0, "text": "x"}, {"row": 1, "col": 1, "text": "y"}]
    out = _md(_doc(_table(cells, 2, 2)))
    assert out.count("Both") == 1


def test_a_table_with_no_cells_falls_back_to_its_crop(tmp_path):
    """A lane that measured only the rectangle has no cells, and for those the
    crop IS the table."""
    (tmp_path / "doc_TAB_001.jpg").write_bytes(b"x")
    doc = _doc(DocObject(type="Table", props={"caption": "Table 1. Results"}))
    out = _md(doc, crops_dir=str(tmp_path))
    assert "report-crops/doc_TAB_001.jpg" in out
    assert "Table 1. Results" in out


# ── transclusion is NEVER in Markdown ────────────────────────────────────────

def test_a_transclusion_marker_never_survives():
    doc = _doc(DocObject(type="Paragraph",
                         props={"text": "before {{doc_FO0001||FO}} after"}))
    out = _md(doc)
    assert not TRANSCLUSION.findall(out)
    assert "before" in out and "after" in out


def test_a_latex_widget_becomes_latex_not_a_widget():
    doc = _doc(DocObject(type="Paragraph", props={
        "text": 'x is <$latex text="a^{2}" displayMode="false"/> here'}))
    out = _md(doc)
    assert "<$latex" not in out
    assert r"\(a^{2}\)" in out


def test_a_display_widget_becomes_display_math():
    doc = _doc(DocObject(type="Paragraph", props={
        "text": '<$latex text="E=mc^{2}" displayMode="true"/>'}))
    assert r"\[E=mc^{2}\]" in _md(doc)


def test_there_is_no_formula_appendix():
    """The complaint that started this: the body must not refer into a table of
    formulas at the end. That form is llm_compact's, and it belongs to llmtext."""
    doc = _doc(DocObject(type="Paragraph", props={"text": "Some prose."}),
               DocObject(type="Formula", props={"latex": "x^2"}))
    out = _md(doc)
    assert "### Inline formulas" not in out
    assert "### Display equations" not in out
    assert not re.search(r"\*\*F\d+\*\*", out)


# ── LaTeX scaffolding that leaks in from MathPix's text_display ──────────────

def test_a_title_wrapper_is_unwrapped_brace_balanced():
    r"""Stripping only the opening `\title{` strands the closing brace: the first
    run emitted a paragraph whose last line was a lone `}`. Same class as 811's
    caption truncation, from the other side."""
    assert _unwrap_latex_wrapper(r"\title{A \emph{good} name}") == r"A \emph{good} name"
    assert "}" not in _unwrap_latex_wrapper(r"\author{X}")


def test_a_line_of_only_closing_braces_is_dropped():
    doc = _doc(DocObject(type="Paragraph",
                         props={"text": "A footnote body\n}\nmore text"}))
    out = _md(doc)
    assert not [ln for ln in out.split("\n") if ln.strip() and not ln.strip().strip("}")]


def test_a_list_environment_is_dropped_because_its_items_are_objects():
    doc = _doc(DocObject(type="Paragraph",
                         props={"text": r"\begin{itemize} intro \end{itemize}"}),
               DocObject(type="ListItem", props={"content": "an item",
                                                 "marker": "-"}))
    out = _md(doc)
    assert "itemize" not in out
    assert "- an item" in out


def test_a_tex_line_break_becomes_a_markdown_one():
    doc = _doc(DocObject(type="Paragraph", props={"text": r"one \\ two"}))
    out = _md(doc)
    assert "\\\\" not in out
    assert "one" in out and "two" in out


# ── structure ────────────────────────────────────────────────────────────────

def test_headings_use_the_sections_level():
    doc = _doc(DocObject(type="Section", props={"caption": "Intro", "level": 1}),
               DocObject(type="Section", props={"caption": "Detail", "level": 3}))
    out = _md(doc)
    assert "# Intro" in out and "### Detail" in out


def test_a_numbered_list_marker_survives_and_others_become_bullets():
    doc = _doc(DocObject(type="ListItem", props={"content": "first", "marker": "1."}),
               DocObject(type="ListItem", props={"content": "next", "marker": "•"}))
    out = _md(doc)
    assert "1. first" in out and "- next" in out


def test_an_equation_with_latex_is_display_math_not_an_image(tmp_path):
    (tmp_path / "doc_EQ0001.jpg").write_bytes(b"x")
    doc = _doc(DocObject(type="Equation", props={"latex": "a+b=c"}))
    out = _md(doc, crops_dir=str(tmp_path))
    assert r"\[a+b=c\]" in out
    assert "![" not in out


def test_an_equation_without_latex_falls_back_to_its_crop(tmp_path):
    (tmp_path / "doc_EQ0001.jpg").write_bytes(b"x")
    doc = _doc(DocObject(type="Equation", props={}))
    assert "report-crops/doc_EQ0001.jpg" in _md(doc, crops_dir=str(tmp_path))


def test_an_equation_with_neither_emits_nothing_not_an_empty_bracket():
    r"""`\[\]` renders as a stray bracket in every renderer."""
    out = _md(_doc(DocObject(type="Equation", props={})))
    assert "\\[" not in out


def test_front_matter_title_is_one_line():
    doc = _doc(DocObject(type="Paragraph", props={"text": "x"}),
               meta={"title": "A Title\nand authors\nand more"})
    out = MarkdownProjector(OperatorConfig(
        op="projector", classname="MarkdownProjector")).project(doc)
    assert 'title: "A Title"' in out


def test_a_code_listing_is_fenced():
    doc = _doc(DocObject(type="CodeListing",
                         props={"content": "print(1)", "language": "python"}))
    out = _md(doc)
    assert "```python" in out and "print(1)" in out


# ── the whole document, on a real model ──────────────────────────────────────

_REAL = (Path.home() / "pdfdrill-library" / "1-s2.0-S2590118425000565-main"
         / "model.docmodel.json")


@pytest.mark.skipif(not _REAL.is_file(), reason="corpus document not present")
def test_a_real_document_gets_images_tables_and_no_transclusions():
    from pdfdrill.model_io import load_model
    doc = load_model(_REAL)
    out = _md(doc, crops_dir=str(_REAL.parent / "report-crops"),
              crops_base="report-crops", front_matter=True)
    assert len(re.findall(r"!\[[^\]]*\]\(report-crops/", out)) >= 10
    assert len(re.findall(r"^\s*\|.*\|\s*$", out, re.M)) >= 10
    assert not TRANSCLUSION.findall(out)
    assert "<$latex" not in out
    assert not [ln for ln in out.split("\n")
                if ln.strip() and not ln.strip().strip("}")]
