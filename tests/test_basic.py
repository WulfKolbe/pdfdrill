"""
Unit tests for the docmodel package.

These tests don't depend on the large MathPix sample. They construct small
synthetic lines.json fragments and verify each layer.
"""
import json
import sys
from pathlib import Path

# Make the package importable when running from this directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import (
    Anchor, Stream, Range, Realization, DocObject, Alignment, Document,
)
from docmodel.modules.page import ingest_lines_json, PageProcessor
from docmodel.modules.equation import EquationProcessor
from docmodel.modules.paragraph import ParagraphProcessor
from docmodel.modules.header import HeaderProcessor
from docmodel.modules.document_flow import DocumentFlowProcessor
from docmodel.modules.document_structure import DocumentStructureProcessor
from docmodel.base_module import ModuleConfig


def _make_module(cls, bibkey="T", proc_order=0):
    cfg = ModuleConfig(title=cls.__name__, classname=cls.__name__, proc_order=proc_order)
    return cls(cfg, bibkey)


def test_anchor_identity_survives_payload_mutation():
    """Two streams sharing references to the same Anchor should remain in sync
    even after one of them appends new anchors."""
    s = Stream("x")
    a = s.append(codepoint="a")
    b = s.append(codepoint="b")
    # An object that holds a reference to 'a'
    obj = DocObject(type="Mark", realizations=[Realization("x", a, a)])
    # Append more anchors after — the reference is still valid
    s.append(codepoint="c")
    s.append(codepoint="d")
    assert s.index_of(a) == 0
    assert s.index_of(b) == 1
    assert obj.realizations[0].start is a


def test_ingest_creates_lines_stream():
    doc = Document()
    sample = {
        "pages": [
            {"page": 1, "image_id": "i1", "lines": [
                {"id": "l1", "type": "text", "text": "Hello"},
                {"id": "l2", "type": "text", "text": "World"},
            ]},
            {"page": 2, "image_id": "i2", "lines": [
                {"id": "l3", "type": "section_header",
                 "children_ids": ["l4"]},
                {"id": "l4", "type": "text",
                 "text": "Chapter One",
                 "text_display": "\\section*{Chapter One}"},
            ]},
        ]
    }
    ingest_lines_json(doc, sample)
    stream = doc.stream("mathpix_lines")
    assert len(stream) == 4
    # The synthetic _page key was added
    assert stream.payload[stream.anchors[0]]["_page"] == 1
    assert stream.payload[stream.anchors[3]]["_page"] == 2


def test_page_processor_creates_one_object_per_page():
    doc = Document()
    sample = {
        "pages": [
            {"page": 1, "image_id": "i1", "lines": [{"id": "a", "type": "text", "text": "x"}]},
            {"page": 2, "image_id": "i2", "lines": [{"id": "b", "type": "text", "text": "y"}]},
        ]
    }
    ingest_lines_json(doc, sample)
    pp = _make_module(PageProcessor)
    pp.process_document(doc)
    pages = doc.objects_of_type("Page")
    assert len(pages) == 2
    assert pages[0].props["page_number"] == 1
    assert pages[1].props["page_number"] == 2


def test_equation_has_three_realizations_and_render_alignment():
    doc = Document()
    sample = {
        "pages": [{"page": 1, "image_id": "img1", "lines": [
            {"id": "eq1", "type": "math",
             "text": r"\[ x^2 + y^2 = z^2 \]",
             "text_display": r"\[ x^2 + y^2 = z^2 \]",
             "region": {"top_left_x": 10, "top_left_y": 20, "width": 100, "height": 50}},
        ]}]
    }
    ingest_lines_json(doc, sample)
    ep = _make_module(EquationProcessor)
    ep.process_document(doc)
    eqs = doc.objects_of_type("Equation")
    assert len(eqs) == 1
    e = eqs[0]
    role_to_realization = {r.role: r for r in e.realizations}
    assert "surface" in role_to_realization
    assert "latex_source" in role_to_realization
    assert "image" in role_to_realization
    # The char-level latex stream has one anchor per codepoint of normalized latex.
    latex_stream = doc.stream(role_to_realization["latex_source"].stream)
    reconstructed = "".join(
        latex_stream.payload[a]["codepoint"] for a in latex_stream.anchors
    )
    assert reconstructed == e.props["latex"]
    # And there is a render alignment between the latex stream and the cdn stream.
    renders = [a for a in doc.alignments if a.kind == "render"]
    assert len(renders) == 1
    assert renders[0].left.stream == role_to_realization["latex_source"].stream
    assert renders[0].right.stream == "cdn"


def test_paragraph_grouping_breaks_on_non_text_lines():
    doc = Document()
    sample = {"pages": [{"page": 1, "image_id": "i", "lines": [
        {"id": "a", "type": "text", "text": "A1", "text_display": "A1"},
        {"id": "b", "type": "text", "text": "A2", "text_display": "A2"},
        {"id": "c", "type": "math", "text_display": r"\[ 1+1=2 \]"},
        {"id": "d", "type": "text", "text": "B1", "text_display": "B1"},
    ]}]}
    ingest_lines_json(doc, sample)
    _make_module(ParagraphProcessor).process_document(doc)
    paras = doc.objects_of_type("Paragraph")
    assert len(paras) == 2
    assert paras[0].props["text"] == "A1 A2"
    assert paras[1].props["text"] == "B1"


def test_section_hierarchy_and_flow_indexing():
    doc = Document()
    sample = {"pages": [{"page": 1, "image_id": "i", "lines": [
        # section 1
        {"id": "h1c", "type": "text", "text": "Intro",
         "text_display": r"\section*{Intro}"},
        {"id": "h1",  "type": "section_header", "children_ids": ["h1c"]},
        {"id": "p1",  "type": "text", "text": "para under intro", "text_display": "para under intro"},
        # subsection 1.1
        {"id": "h2c", "type": "text", "text": "Background",
         "text_display": r"\subsection*{Background}"},
        {"id": "h2",  "type": "section_header", "children_ids": ["h2c"]},
        {"id": "p2",  "type": "text", "text": "para under 1.1", "text_display": "para under 1.1"},
        # section 2
        {"id": "h3c", "type": "text", "text": "Method",
         "text_display": r"\section*{Method}"},
        {"id": "h3",  "type": "section_header", "children_ids": ["h3c"]},
    ]}]}
    ingest_lines_json(doc, sample)
    for cls in (PageProcessor, HeaderProcessor, ParagraphProcessor,
                DocumentFlowProcessor, DocumentStructureProcessor):
        m = _make_module(cls)
        m.process_document(doc)
    for cls in (DocumentFlowProcessor, DocumentStructureProcessor):
        _make_module(cls).process_objects(doc)

    sections = doc.objects_of_type("Section")
    assert len(sections) == 3
    # Order by flow_index
    sections.sort(key=lambda s: s.props["flow_index"])
    assert sections[0].props["section_number"] == "1"
    assert sections[1].props["section_number"] == "1.1"
    assert sections[2].props["section_number"] == "2"
    # Subsection's parent is Section "1"
    assert sections[1].parent == sections[0].id
    # Section "2"'s parent is the document root, not Section "1"
    root = doc.objects[doc.meta["root_id"]]
    assert sections[0].parent == root.id
    assert sections[2].parent == root.id


def test_round_trip_serialization():
    """A Document.to_dict() must be JSON-serializable and structurally complete."""
    doc = Document()
    sample = {"pages": [{"page": 1, "image_id": "i", "lines": [
        {"id": "a", "type": "text", "text": "hi", "text_display": "hi"},
    ]}]}
    ingest_lines_json(doc, sample)
    _make_module(PageProcessor).process_document(doc)
    out = doc.to_dict()
    s = json.dumps(out)             # must not raise
    reloaded = json.loads(s)
    assert "streams" in reloaded
    assert "objects" in reloaded
    assert "alignments" in reloaded
    assert "meta" in reloaded


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__)
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__)
            print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} failed out of {len(tests)}")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
