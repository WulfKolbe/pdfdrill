"""
BeamerProjector — project the docmodel to a LaTeX beamer slide deck: one frame
per Section (`allowframebreaks` so long content auto-continues), a title frame,
a TOC/outline frame, and a References frame. Reuses the LaTeX projector's
transclusion / citation / list machinery.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from docops.base import OperatorConfig
from docops.projectors.beamer import BeamerProjector


def _proj():
    return BeamerProjector(OperatorConfig(op="projector", classname="BeamerProjector"))


def _doc():
    d = Document()
    d.meta["bibkey"] = "demo"
    d.meta["title"] = "A Talk"
    d.meta["authors"] = ["Ada Lovelace"]
    d.add(DocObject(type="Section", props={"level": 1, "caption": "Introduction",
                                           "flow_index": 0}))
    d.add(DocObject(type="Paragraph", props={"text": "We study $x^2$.", "flow_index": 1}))
    d.add(DocObject(type="ListItem", props={"marker": "-", "content": "point one",
                                            "flow_index": 2}))
    d.add(DocObject(type="Section", props={"level": 1, "caption": "Method",
                                           "flow_index": 3}))
    d.add(DocObject(type="Paragraph", props={"text": "The method.", "flow_index": 4}))
    return d


def test_is_a_beamer_document():
    tex = _proj().project(_doc())
    assert "\\documentclass{beamer}" in tex
    assert "\\begin{document}" in tex and "\\end{document}" in tex


def test_title_and_outline_frames():
    tex = _proj().project(_doc())
    assert "\\title{A Talk}" in tex and "Ada Lovelace" in tex
    assert "\\titlepage" in tex                     # title frame
    assert "\\tableofcontents" in tex               # outline frame


def test_one_frame_per_section_with_allowframebreaks():
    tex = _proj().project(_doc())
    # two sections → two content frames (+ title + outline)
    assert tex.count("\\begin{frame}") == tex.count("\\end{frame}")
    assert tex.count("allowframebreaks") == 2       # one per section
    assert "{Introduction}" in tex and "{Method}" in tex
    assert "\\section{Introduction}" in tex          # drives the TOC


def test_section_content_inside_its_frame():
    tex = _proj().project(_doc())
    # the paragraph + list of Introduction sit between its frame begin/end
    fb = tex.index("{Introduction}")
    fe = tex.index("\\end{frame}", fb)
    frame = tex[fb:fe]
    assert "We study $x^2$." in frame
    assert "\\begin{itemize}" in frame and "point one" in frame


def test_output_extension():
    assert _proj().output_extension() == ".tex"


def test_content_before_first_section_gets_a_frame():
    d = Document(); d.meta["bibkey"] = "x"
    d.add(DocObject(type="Paragraph", props={"text": "orphan intro", "flow_index": 0}))
    d.add(DocObject(type="Section", props={"level": 1, "caption": "S", "flow_index": 1}))
    tex = _proj().project(d)
    assert "orphan intro" in tex
    # it is inside a frame (not loose in the document body)
    assert tex.index("orphan intro") > tex.index("\\begin{frame}")
