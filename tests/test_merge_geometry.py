"""
Build BOTH routes and merge — structure from the LaTeX source, page geometry
from the born-digital text layer.

The two were mutually exclusive, and picking one always discarded the other's
contribution. An audit of 2209.00445v3 built via `model` saw the pdfminer side
only: 0 Formula, 0 Section, 16 Paragraph for 7045 words, no transclusions —
while the same PDF via the LaTeX source gives 73 Formula / 24 Section / 16 Table
but has no page at all.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from pdfdrill.commands import merge_page_geometry


def _lines(tmp_path):
    p = tmp_path / "x.lines.json"
    p.write_text(json.dumps({"source": "pdfminer-chars", "pages": [
        {"page": 1, "page_width": 612, "page_height": 792,
         "lines": [{"text": "We present a method for mapping text into vectors"}]},
        {"page": 2, "page_width": 612, "page_height": 792,
         "lines": [{"text": "The second section discusses related work in depth"}]},
    ]}), encoding="utf-8")
    return p


def _doc():
    d = Document(); d.meta["bibkey"] = "K"
    d.add(DocObject(type="Paragraph", props={
        "text": "We present a method for mapping text into vectors", "flow_index": 1}))
    d.add(DocObject(type="Paragraph", props={
        "text": "The second section discusses related work in depth", "flow_index": 2}))
    d.add(DocObject(type="Formula", props={"latex": "f(x)", "flow_index": 3}))
    return d


def test_merge_adds_pages_and_places_objects(tmp_path):
    d = _doc()
    stats = merge_page_geometry(d, _lines(tmp_path))
    assert stats["pages"] == 2 and stats["placed"] == 2
    # `regions` was added when the merge started keeping the matched lines'
    # boxes; assert the fields that matter, not the exact dict shape.
    assert "regions" in stats
    pages = [o for o in d.objects.values() if o.type == "Page"]
    assert len(pages) == 2
    assert {p.props["page_number"] for p in pages} == {1, 2}
    assert pages[0].props["page_width"] == 612
    placed = {o.props.get("text", "")[:12]: o.props.get("page")
              for o in d.objects.values() if o.type == "Paragraph"}
    assert placed["We present a"] == 1 and placed["The second s"] == 2


def test_structure_is_preserved_by_the_merge(tmp_path):
    """The whole point: the source model's objects must survive intact."""
    d = _doc()
    before = sorted(o.type for o in d.objects.values())
    merge_page_geometry(d, _lines(tmp_path))
    after = sorted(o.type for o in d.objects.values() if o.type != "Page")
    assert after == before


def test_unplaceable_object_is_left_without_a_page(tmp_path):
    """Matching is textual and therefore approximate. An object that cannot be
    located must be left alone, never guessed onto a page."""
    d = Document(); d.meta["bibkey"] = "K"
    d.add(DocObject(type="Paragraph", props={
        "text": "Text that appears on no page of this document at all",
        "flow_index": 1}))
    stats = merge_page_geometry(d, _lines(tmp_path))
    assert stats["placed"] == 0
    para = [o for o in d.objects.values() if o.type == "Paragraph"][0]
    assert "page" not in para.props


def test_missing_lines_json_degrades_quietly(tmp_path):
    d = _doc()
    stats = merge_page_geometry(d, tmp_path / "nope.json")
    assert stats == {"pages": 0, "placed": 0}
    assert not [o for o in d.objects.values() if o.type == "Page"]
