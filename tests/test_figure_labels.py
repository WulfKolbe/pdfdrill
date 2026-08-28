"""253 — `figure_label` children are in-figure text, never a caption.

The corpus holds 49 `figure_label` lines parented to a diagram/chart; every one
reads as axis-label / legend / listing-title text. Attaching one as a caption
would assert an association MathPix never stated, so DiagramProcessor records
them as `labels` and leaves `caption` to the line's own `\\caption{}`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.base_module import ModuleConfig
from docmodel.core import Document
from docmodel.modules.page import ingest_lines_json
from docmodel.modules.diagram import DiagramProcessor
from docmodel.modules.picture import PictureProcessor, _NO_PRODUCER


def _mod(cls):
    return cls(ModuleConfig(title=cls.__name__, classname=cls.__name__, proc_order=0), "T")


def _doc(lines):
    doc = Document()
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "abc-01", "lines": lines}]})
    return doc


def _run(doc):
    return _mod(DiagramProcessor).find_items(doc)


def test_figure_label_child_is_not_a_caption():
    doc = _doc([
        {"id": "d1", "type": "diagram", "text": "![](http://cdn/x.jpg)",
         "children_ids": ["c1"]},
        {"id": "c1", "type": "figure_label", "text": "GATE VOLTAGE (V)"},
    ])
    item = _run(doc)[0]
    assert item["caption"] == ""
    assert item["labels"] == ["GATE VOLTAGE (V)"]


def test_own_caption_still_wins_and_labels_coexist():
    doc = _doc([
        {"id": "d1", "type": "diagram",
         "text": "\\begin{figure}\\caption{Figure 3: the lattice}\\end{figure}",
         "children_ids": ["c1"]},
        {"id": "c1", "type": "figure_label", "text": "Step Trace"},
    ])
    item = _run(doc)[0]
    assert item["caption"] == "Figure 3: the lattice"
    assert item["labels"] == ["Step Trace"]


def test_empty_label_children_are_dropped():
    # 3 of the corpus's 49 children carry empty text.
    doc = _doc([
        {"id": "d1", "type": "diagram", "text": "x", "children_ids": ["c1", "c2"]},
        {"id": "c1", "type": "figure_label", "text": "   "},
        {"id": "c2", "type": "figure_label", "text": "Am7"},
    ])
    assert _run(doc)[0]["labels"] == ["Am7"]


def test_non_label_children_are_not_labels():
    doc = _doc([
        {"id": "d1", "type": "diagram", "text": "x", "children_ids": ["c1"]},
        {"id": "c1", "type": "text", "text": "body prose"},
    ])
    assert _run(doc)[0]["labels"] == []


def test_labels_reach_the_object_props():
    doc = _doc([
        {"id": "d1", "type": "diagram", "text": "![](http://cdn/x.jpg)",
         "children_ids": ["c1"]},
        {"id": "c1", "type": "figure_label", "text": "Am AS"},
    ])
    m = _mod(DiagramProcessor)
    obj = m.create_object(m.find_items(doc)[0], doc)
    assert obj.props["labels"] == ["Am AS"]
    assert obj.props["caption"] == ""


def test_no_producer_literals_are_recorded():
    # Kept deliberately: no producer emits them, so the guard is fixture-only.
    assert _NO_PRODUCER == ("figure", "caption")


def test_picture_skips_diagram_but_reads_chart_caption_inline():
    # All 1,807 captioned charts carry \caption{} inside \begin{figure}, which
    # the inline path already reads — chart needs no branch of its own.
    doc = _doc([
        {"id": "p1", "type": "chart",
         "text": "\\begin{figure}![](http://cdn/c.jpg)\\caption{Figure 1: bars}\\end{figure}"},
    ])
    items = _mod(PictureProcessor).find_items(doc)
    assert len(items) == 1
    assert items[0]["caption"] == "Figure 1: bars"
    assert items[0]["from_line_type"] == "chart"
