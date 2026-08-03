"""The geometry merge must attach a REGION, not only a page number.

`inspect` draws every DocObject as a box on the rendered page, so an object with
no `region` is invisible in the inspector — on 2209.00445v3 that was all 287 of
them, and the view came up with no rectangles at all.

The information was already there. The merge located each object by matching its
text against the page's lines, then kept only the page number and threw the
matched LINES away — and those lines carry the pdfminer regions. Taking the
union of the matched lines' boxes costs nothing extra and is exactly the
object's rectangle.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmodel.core import Document, DocObject
from pdfdrill.commands import merge_page_geometry


def _line(text, x, y, w, h):
    return {"text": text, "type": "text",
            "region": {"top_left_x": x, "top_left_y": y, "width": w, "height": h}}


def _lines_json(tmp_path):
    data = {"pages": [
        {"page": 1, "page_width": 612, "page_height": 792, "lines": [
            _line("Introduction to the problem of scaling", 72, 100, 400, 12),
            _line("We propose a method that learns a metric", 72, 120, 420, 12),
            _line("over the manifold and evaluates it", 72, 140, 380, 12),
        ]},
        {"page": 2, "page_width": 612, "page_height": 792, "lines": [
            _line("Results on the benchmark suite are strong", 72, 100, 410, 12),
        ]},
    ]}
    p = tmp_path / "d.lines.json"
    p.write_text(__import__("json").dumps(data))
    return p


def test_object_gets_page_and_region(tmp_path):
    doc = Document()
    doc.add(DocObject(type="Paragraph", props={
        "text": "We propose a method that learns a metric over the manifold"}))
    stats = merge_page_geometry(doc, _lines_json(tmp_path))

    para = next(o for o in doc.objects.values() if o.type == "Paragraph")
    assert para.props.get("page") == 1
    r = para.props.get("region")
    assert r, "no rectangle — the inspector has nothing to draw"
    # spans the two matched lines: y 120 → 140+12
    assert r["top_left_y"] == 120 and r["height"] == 32
    assert r["top_left_x"] == 72 and r["width"] == 420
    assert stats.get("regions", 0) >= 1


def test_single_line_object_gets_that_lines_box(tmp_path):
    doc = Document()
    doc.add(DocObject(type="Section", props={
        "caption": "Results on the benchmark suite are strong"}))
    merge_page_geometry(doc, _lines_json(tmp_path))
    sec = next(o for o in doc.objects.values() if o.type == "Section")
    assert sec.props["page"] == 2
    assert sec.props["region"] == {"top_left_x": 72, "top_left_y": 100,
                                   "width": 410, "height": 12}


def test_unplaceable_object_gets_no_invented_region(tmp_path):
    """An object that cannot be located must stay without geometry — a guessed
    box puts a real element in the wrong place, which is worse than no box."""
    doc = Document()
    doc.add(DocObject(type="Paragraph", props={"text": "text that appears nowhere at all"}))
    merge_page_geometry(doc, _lines_json(tmp_path))
    para = next(o for o in doc.objects.values() if o.type == "Paragraph")
    assert "region" not in para.props and "page" not in para.props
