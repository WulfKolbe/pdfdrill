"""Objects text matching cannot reach must still get a rectangle.

`merge_page_geometry` places an object by matching its TEXT against the page's
lines, which works for prose and structurally cannot work for anything else: a
Formula's source is `\\frac{a}{b}` and never matches the rendered glyphs, a
Picture has no text at all. So the objects a reader most wants boxed were
exactly the ones the merge missed — on 2609.24972, 0 of 81 Formulas, 0 of 6
Tables and 0 of 4 Pictures, which is an `inspect` page showing a frame around
the text and nothing inside it.

Reading order supplies the constraint matching lacks: an unmatched object
between two MATCHED neighbours lies between their lines on the page, so the
unclaimed lines of that gap are its own. Bounded, never invented — the tests
below pin both halves of that: the gap is filled, and nothing is placed when
there is no verified neighbour to measure from.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmodel.core import Document, DocObject
from pdfdrill.commands import merge_page_geometry, prefers_merged_route


def _line(text, y):
    return {"text": text, "type": "text",
            "region": {"top_left_x": 72, "top_left_y": y,
                       "width": 400, "height": 12}}


def _lines_json(tmp_path):
    """One page: prose, a rendered formula line, prose. The middle line is the
    one no source text can match."""
    data = {"source": "pdfminer-chars", "pages": [
        {"page": 1, "page_width": 612, "page_height": 792, "lines": [
            _line("Introduction to the problem of scaling", 100),
            _line("We propose a method that learns a metric", 120),
            _line("f x y frac a b gamma delta", 140),
            _line("where the metric is defined over points", 160),
        ]},
    ]}
    p = tmp_path / "d.lines.json"
    p.write_text(json.dumps(data))
    return p


def _doc_with_formula_between_two_paragraphs():
    doc = Document()
    doc.add(DocObject(type="Paragraph", props={
        "text": "We propose a method that learns a metric", "flow_index": 0}))
    doc.add(DocObject(type="Formula", props={
        "latex": r"\frac{a}{b}", "flow_index": 1}))
    doc.add(DocObject(type="Paragraph", props={
        "text": "where the metric is defined over points", "flow_index": 2}))
    return doc


def test_unmatchable_object_takes_the_gap_between_its_neighbours(tmp_path):
    doc = _doc_with_formula_between_two_paragraphs()
    stats = merge_page_geometry(doc, _lines_json(tmp_path))

    f = next(o for o in doc.objects.values() if o.type == "Formula")
    r = f.props.get("region")
    assert r, "the formula is invisible in the inspector"
    # exactly the one unclaimed line between the two matched paragraphs
    assert r["top_left_y"] == 140 and r["height"] == 12
    assert f.props.get("page") == 1
    assert stats.get("interpolated", 0) == 1


def test_an_interpolated_rectangle_says_so(tmp_path):
    """A reader must be able to tell a measured box from a positioned one."""
    doc = _doc_with_formula_between_two_paragraphs()
    merge_page_geometry(doc, _lines_json(tmp_path))

    f = next(o for o in doc.objects.values() if o.type == "Formula")
    p = next(o for o in doc.objects.values()
             if o.type == "Paragraph" and o.props["flow_index"] == 0)
    assert f.props.get("region_via") == "interpolated"
    assert "region_via" not in p.props, "a matched box must not be labelled one"


def test_running_the_merge_twice_changes_nothing(tmp_path):
    lines = _lines_json(tmp_path)
    doc = _doc_with_formula_between_two_paragraphs()
    merge_page_geometry(doc, lines)
    first = dict(next(o for o in doc.objects.values()
                      if o.type == "Formula").props["region"])

    stats = merge_page_geometry(doc, lines)
    again = next(o for o in doc.objects.values() if o.type == "Formula")
    assert again.props["region"] == first
    assert stats.get("interpolated", 0) == 0


def test_nothing_is_placed_without_a_verified_neighbour(tmp_path):
    """With no match anywhere, the gap is the whole document — which would
    stretch one formula over 24 pages. Place nothing instead."""
    doc = Document()
    doc.add(DocObject(type="Formula", props={
        "latex": r"\frac{a}{b}", "flow_index": 0}))
    doc.add(DocObject(type="Formula", props={
        "latex": r"\sum_{i}", "flow_index": 1}))
    stats = merge_page_geometry(doc, _lines_json(tmp_path))

    assert stats.get("interpolated", 0) == 0
    assert all(not o.props.get("region")
               for o in doc.objects.values() if o.type == "Formula")


def test_an_inline_marker_never_eats_the_gap(tmp_path):
    """A Citation sits INSIDE a paragraph's line. If it could claim a gap line,
    it would take the rectangle that belongs to the formula beside it."""
    doc = _doc_with_formula_between_two_paragraphs()
    doc.add(DocObject(type="Citation", props={"text": "[3]", "flow_index": 1}))
    doc.add(DocObject(type="LtxCommand", props={"text": r"\label{eq:1}",
                                                "flow_index": 1}))
    merge_page_geometry(doc, _lines_json(tmp_path))

    f = next(o for o in doc.objects.values() if o.type == "Formula")
    assert f.props["region"]["top_left_y"] == 140
    for t in ("Citation", "LtxCommand"):
        o = next(x for x in doc.objects.values() if x.type == t)
        assert not o.props.get("region"), f"{t} consumed a line of the page"


def test_visionocr_lines_still_take_the_merged_route():
    """`visionocr` restamps the lines.json it enriches. Leaving that name out of
    the mergeable set switched the LaTeX-source route off permanently — no
    --force could bring it back, and 2609.24972 fell from 463 objects to 147,
    losing every Section, Table and Picture."""
    assert prefers_merged_route(lines_exists=True, lines_source="visionocr",
                                is_arxiv=True, mathpix=False)
    # and the rule it must not break: MathPix contributes everything already
    assert not prefers_merged_route(lines_exists=True, lines_source="visionocr",
                                    is_arxiv=True, mathpix=True)


# --------------------------------------------------------------------------
# The rectangles have to reach the SCREEN, not just the model.
# --------------------------------------------------------------------------

def test_a_merged_model_still_knows_its_page_size():
    """The overlay places a box at `100 * x / pt_w` percent.

    A LaTeX-source model has no `meta["pages"]`, so `pages_meta` used to fall
    back to `pt_w: None` — and `100 * x / null` is `"Infinity%"`, which CSS
    silently discards. Every rectangle in the model was correct and not one of
    them was drawn: a full model looked exactly like an empty one. The merged
    route adds a Page OBJECT per page carrying the real dimensions; read those.
    """
    from pdfdrill.docinspect import build_stream_index, collect_elements

    model = {
        "meta": {},                                   # no meta["pages"]
        "streams": {},
        "objects": [
            {"id": "p1", "type": "Page", "props": {
                "page_number": 1, "page_width": 595.28, "page_height": 841.89},
             "realizations": [], "children": []},
            {"id": "o1", "type": "Paragraph", "props": {
                "page": 1, "text": "body",
                "region": {"top_left_x": 72, "top_left_y": 100,
                           "width": 400, "height": 12}},
             "realizations": [], "children": []},
        ],
    }
    _elements, pages_meta = collect_elements(model, build_stream_index(model))
    page1 = next(m for m in pages_meta if m["page"] == 1)
    assert page1["pt_w"] == 595 and page1["pt_h"] == 842, \
        "no page size means no scale, and the overlay draws nothing at all"


def test_a_page_object_is_addressed_by_its_own_page_number():
    """A Page numbers itself `page_number`; everything else carries `page`.

    Reading only the latter gave every merged Page `page: None`, and the
    overlay filters boxes with `e.page === curPage` — so the frame was never
    drawn, on exactly the models where the Page was the best-measured object
    on the sheet.
    """
    from pdfdrill.docinspect import build_stream_index, collect_elements

    model = {
        "meta": {}, "streams": {},
        "objects": [
            {"id": "p1", "type": "Page", "props": {
                "page_number": 7, "page_width": 595, "page_height": 842,
                "region": {"top_left_x": 60, "top_left_y": 50,
                           "width": 470, "height": 740}},
             "realizations": [], "children": []},
        ],
    }
    elements, _pm = collect_elements(model, build_stream_index(model))
    page_el = next(e for e in elements if e["type"] == "Page")
    assert page_el["page"] == 7, "an unaddressable box is never drawn"
    assert page_el["bbox"], "the page frame lost its rectangle"
