"""
Tests for image handling: PictureProcessor / DiagramProcessor and the shared
caption parser.

MathPix encodes one image two equivalent ways in a line's text fields:
  - LaTeX form:    \\begin{figure}\\includegraphics{<cdn>}\\caption{...}\\end{figure}
  - Markdown form: ![](<cdn>)

We verify both forms are captured, captions (incl. nested-brace math) are
extracted and parsed (kind/refnum), and a `type='diagram'` line yields exactly
one object (a Diagram, owned by DiagramProcessor) — NOT also a duplicate
Picture.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document
from docmodel.modules.page import ingest_lines_json
from docmodel.modules.diagram import DiagramProcessor
from docmodel.modules.picture import PictureProcessor
from docmodel.modules._captions import extract_figure_caption, parse_caption
from docmodel.base_module import ModuleConfig


def _mod(cls, bibkey="T"):
    return cls(ModuleConfig(title=cls.__name__, classname=cls.__name__, proc_order=0), bibkey)


# Per-page image_id already carries the `-<page>` suffix in real lines.json;
# crop_url(image_id, region) reproduces the Markdown link exactly.
_IMAGE_ID = "abc-09"
_REGION = {"height": 100, "width": 200, "top_left_y": 5, "top_left_x": 7}
_CDN = ("https://cdn.mathpix.com/cropped/abc-09.jpg"
        "?height=100&width=200&top_left_y=5&top_left_x=7")


def _doc(lines, image_id=_IMAGE_ID):
    doc = Document()
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": image_id, "lines": lines}]})
    return doc


# ---- caption helper -------------------------------------------------------

def test_extract_caption_balanced_braces_with_math():
    text = (
        "\\begin{figure}\\includegraphics{" + _CDN + "}"
        "\\caption{Picture 7: meeting Gerta Ital ( \\(2^{\\text {nd }}\\) from right)}"
        "\\end{figure}"
    )
    cap = extract_figure_caption(text)
    assert cap == "Picture 7: meeting Gerta Ital ( \\(2^{\\text {nd }}\\) from right)"


def test_parse_caption_widened_kinds_and_refnum():
    assert parse_caption("Picture 1: hello") == ("Picture", "1", "hello")
    assert parse_caption("Sketch 2: a structure") == ("Sketch", "2", "a structure")
    assert parse_caption("Table 1: masses") == ("Table", "1", "masses")
    # trailing-letter refnum (e.g. 5b) and dotted (1.2)
    assert parse_caption("Picture 5b: colloquium")[1] == "5b"
    assert parse_caption("Figure 1.2: x")[1] == "1.2"
    # no recognizable label -> body only
    assert parse_caption("just some text") == (None, None, "just some text")


# ---- DiagramProcessor: owns diagram lines, extracts captions --------------

def test_diagram_latex_form_extracts_caption():
    text = "\\begin{figure}\\includegraphics{%s}\\caption{Sketch 2: in \\(\\mathrm{R}_{6}\\)}\\end{figure}" % _CDN
    doc = _doc([{"id": "l1", "type": "diagram", "text": "", "text_display": text,
                 "region": {"height": 100, "width": 200, "top_left_y": 5, "top_left_x": 7}}])
    _mod(DiagramProcessor).process_document(doc)
    dias = [o for o in doc.objects.values() if o.type == "Diagram"]
    assert len(dias) == 1
    d = dias[0]
    assert d.props["kind"] == "Sketch"
    assert d.props["refnum"] == "2"
    assert "\\(\\mathrm{R}_{6}\\)" in d.props["caption"]


def test_diagram_markdown_form_has_no_caption():
    doc = _doc([{"id": "l1", "type": "diagram", "text": "", "text_display": "\n![](%s)" % _CDN,
                 "region": {"height": 100, "width": 200, "top_left_y": 5, "top_left_x": 7}}])
    _mod(DiagramProcessor).process_document(doc)
    dias = [o for o in doc.objects.values() if o.type == "Diagram"]
    assert len(dias) == 1
    assert (dias[0].props.get("caption") or "") == ""


# ---- PictureProcessor: skips diagram lines (no duplication) ---------------

def test_picture_skips_diagram_lines():
    """A diagram line must NOT also become a Picture (DiagramProcessor owns it)."""
    doc = _doc([{"id": "l1", "type": "diagram", "text": "", "text_display": "\n![](%s)" % _CDN}])
    _mod(PictureProcessor).process_document(doc)
    pics = [o for o in doc.objects.values() if o.type == "Picture"]
    assert pics == []


def test_picture_handles_chart_markdown_form():
    doc = _doc([{"id": "l1", "type": "chart", "text": "", "text_display": "\n![](%s)" % _CDN}])
    _mod(PictureProcessor).process_document(doc)
    pics = [o for o in doc.objects.values() if o.type == "Picture"]
    assert len(pics) == 1
    assert pics[0].props["url"] == _CDN
    assert pics[0].props["from_line_type"] == "chart"


def test_picture_figure_type_uses_markdown_link_not_includegraphics():
    """A figure line's URL comes from crop_url(image_id, region) — the Markdown
    link — NOT from the \\includegraphics target (which here is a tex.zip-style
    local per-picture file)."""
    text = ("\\begin{figure}\\includegraphics[alt={},max width=\\textwidth]{images/abc-09-1.jpg}"
            "\\caption{Figure 3: the diagram}\\end{figure}")
    doc = _doc([{"id": "l1", "type": "figure", "text": "", "text_display": text,
                 "region": dict(_REGION)}])
    _mod(PictureProcessor).process_document(doc)
    pics = [o for o in doc.objects.values() if o.type == "Picture"]
    assert len(pics) == 1
    assert pics[0].props["kind"] == "Figure"
    assert pics[0].props["refnum"] == "3"
    assert pics[0].props["caption"] == "the diagram"
    # Markdown page+rectangle link, not the local includegraphics file.
    assert pics[0].props["url"] == _CDN
    assert "images/abc-09-1.jpg" not in pics[0].props["url"]


def test_picture_inline_figure_env_in_text_line():
    """A figure-env embedded in a normal text line is still captured."""
    text = "Some prose. \\begin{figure}\\includegraphics{%s}\\caption{Picture 9: x}\\end{figure}" % _CDN
    doc = _doc([{"id": "l1", "type": "text", "text": "", "text_display": text}])
    _mod(PictureProcessor).process_document(doc)
    pics = [o for o in doc.objects.values() if o.type == "Picture"]
    assert len(pics) == 1
    assert pics[0].props["url"] == _CDN
    assert pics[0].props["kind"] == "Picture"
    assert pics[0].props["refnum"] == "9"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nAll {len(fns)} tests passed.")
