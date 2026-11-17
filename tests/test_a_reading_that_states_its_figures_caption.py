r"""A reading that states a figure's caption on the line is believed.

After the drift fix, the Gemma reader stopped writing figure captions as
`![Figure 1: ...](...)` body text lines and started stating them on the diagram
line itself, in a `description` field. pdfdrill read neither, so on 0864 v13 all
7 Diagrams came out `caption=''`, `kind=None` — the caption was in the reading
and nowhere in the model, and the caption rows below the figure became body
paragraphs.

The caption chain was `\caption{}` in the line's own text, then
`adjacent_label_caption`, which guesses from a neighbouring `figure_label` line.
`description` belongs between them: it is STATED, so it beats a neighbour guess,
and it is less specific than an explicit `\caption{}` the line carries, so an
explicit caption still wins.

MathPix emits no `description`, so nothing in the existing corpus changes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.base_module import ModuleConfig
from docmodel.core import Document
from docmodel.modules.page import ingest_lines_json, PageProcessor
from docmodel.modules.diagram import DiagramProcessor

REGION = {"top_left_x": 100, "top_left_y": 200, "width": 800, "height": 600}


def _mod(cls):
    return cls(ModuleConfig(title=cls.__name__, classname=cls.__name__, proc_order=0), "T")


def _doc(lines):
    doc = Document()
    doc.meta["bibkey"] = "T"
    for i, ln in enumerate(lines):
        ln.setdefault("id", "l%d" % i)
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "im-01",
                                       "page_width": 2125, "page_height": 2750,
                                       "lines": lines}]})
    _mod(PageProcessor).process_document(doc)
    return doc


def _diagram(doc):
    mod = _mod(DiagramProcessor)
    mod.process_document(doc)
    return doc.objects_of_type("Diagram")[0]


def test_a_stated_description_becomes_the_caption():
    obj = _diagram(_doc([
        {"type": "diagram", "text": "", "region": REGION,
         "description": "Figure 1: Dependency-by-chance. Estimated fraction."},
    ]))
    assert obj.props["caption"] == "Dependency-by-chance. Estimated fraction."
    assert obj.props["kind"] == "Figure"
    assert str(obj.props["refnum"]) == "1"


def test_an_explicit_caption_in_the_line_still_wins():
    obj = _diagram(_doc([
        {"type": "diagram", "text": "\\caption{The explicit one}", "region": REGION,
         "description": "Figure 9: the stated one"},
    ]))
    assert obj.props["caption"] == "The explicit one"


def test_a_stated_description_beats_a_neighbour_guess():
    """`adjacent_label_caption` infers from a nearby line; `description` is
    stated on this line, so it is the better evidence."""
    obj = _diagram(_doc([
        {"type": "diagram", "text": "", "region": REGION,
         "description": "Figure 2: stated here"},
        {"type": "figure_label", "text": "Figure 3: the neighbour"},
    ]))
    assert obj.props["caption"] == "stated here"
    assert str(obj.props["refnum"]) == "2"


def test_a_description_that_is_not_a_label_is_still_the_caption():
    obj = _diagram(_doc([
        {"type": "diagram", "text": "", "region": REGION,
         "description": "A plain sentence with no label."},
    ]))
    assert obj.props["caption"] == "A plain sentence with no label."
    assert obj.props["kind"] is None


def test_no_description_changes_nothing():
    obj = _diagram(_doc([{"type": "diagram", "text": "", "region": REGION}]))
    assert obj.props["caption"] == ""


def test_an_empty_description_is_not_a_caption():
    obj = _diagram(_doc([
        {"type": "diagram", "text": "", "region": REGION, "description": "   "},
    ]))
    assert obj.props["caption"] == ""
