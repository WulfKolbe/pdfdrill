import json

from docmodel.core import Document, DocObject
from pdfdrill.reports.from_document import build_rows
from pdfdrill.reports.rows import EquationRow, FormulaRow, TableRow, ImageRow

BK = "DOC"


def _doc():
    doc = Document(meta={"bibkey": BK})
    doc.add(DocObject(id="e1", type="Equation", props={
        "flow_index": 3, "latex": "a=b", "page": 2, "equation_number": "(1)",
        "confidence": 0.91, "trailing_punct": ".", "cdn_url": "https://cdn/x.jpg",
        "region": {"top_left_x": 1, "top_left_y": 2, "width": 300, "height": 40}}))
    doc.add(DocObject(id="f1", type="Formula", props={"flow_index": 1, "latex": "P"}))
    doc.add(DocObject(id="f2", type="Formula", props={"flow_index": 2, "latex": "\\square"}))
    doc.add(DocObject(id="t1", type="Table", props={
        "flow_index": 4, "mathpix_text": "\\begin{tabular}{c}1\\end{tabular}",
        "page": 5, "confidence": 0.7,
        "region": {"top_left_x": 1, "top_left_y": 2, "width": 400, "height": 80}}))
    doc.add(DocObject(id="d1", type="Diagram", props={
        "flow_index": 5, "page": 6,
        "region": {"top_left_x": 3, "top_left_y": 4, "width": 100, "height": 50}}))
    doc.add(DocObject(id="p1", type="Picture", props={"flow_index": 6, "page": 7,
                                                        "url": "https://cdn/p.jpg"}))
    return doc


def _lines(tmp_path):
    p = tmp_path / "DOC.lines.json"
    p.write_text(json.dumps({"pages": [
        {"lines": [{"type": "text", "text": "distribution \\(P\\) of",
                    "confidence": 0.98,
                    "region": {"top_left_x": 10, "top_left_y": 20,
                               "width": 800, "height": 40}}]}]}))
    return p


def test_every_kind_is_typed_and_named_by_the_projector_authority():
    rows = build_rows(_doc(), BK)
    assert [(type(r), r.identifier) for r in rows["equation"]] == [(EquationRow, "DOC_EQ0001")]
    assert [r.identifier for r in rows["formula"]] == ["DOC_FO0001", "DOC_FO0002"]
    assert [(type(r), r.identifier) for r in rows["table"]] == [(TableRow, "DOC_TAB_001")]
    assert [(type(r), r.identifier) for r in rows["image"]] == [
        (ImageRow, "DOC_DIA_0001"), (ImageRow, "DOC_PIC_0001")]


def test_equation_fields():
    (r,) = build_rows(_doc(), BK)["equation"]
    assert (r.latex, r.page, r.eqnum, r.px_width, r.trailing_punct, r.confidence,
            r.cdn_url) == ("a=b", "2", "(1)", "300", ".", 0.91, "https://cdn/x.jpg")
    assert r.region == {"top_left_x": 1, "top_left_y": 2, "width": 300, "height": 40}


def test_equation_carries_ink_when_given():
    ink = {"DOC_EQ0001": {"flag": "weak", "code": "W|+1"}}
    (r,) = build_rows(_doc(), BK, ink=ink)["equation"]
    assert r.ink_code == "W|+1"


def test_formula_takes_its_host_line_from_lines_json(tmp_path):
    rows = build_rows(_doc(), BK, lines_path=_lines(tmp_path))
    p, sq = rows["formula"]
    assert p.host_line.page == 1 and p.host_line.confidence == 0.98
    assert p.host_line.region["width"] == 800
    assert sq.host_line is None


def test_lines_path_defaults_to_the_models_source_path(tmp_path):
    doc = _doc()
    doc.meta["source_path"] = str(_lines(tmp_path))
    p, _ = build_rows(doc, BK)["formula"]
    assert p.host_line is not None


def test_table_latex_is_mathpix_text_and_picture_url_is_its_cdn():
    rows = build_rows(_doc(), BK)
    (t,) = rows["table"]
    assert t.latex.startswith("\\begin{tabular}") and t.dims == ("400", "80")
    dia, pic = rows["image"]
    assert pic.cdn_url == "https://cdn/p.jpg" and dia.cdn_url == ""


def test_missing_lines_json_is_not_an_error(tmp_path):
    rows = build_rows(_doc(), BK, lines_path=tmp_path / "nope.json")
    assert all(r.host_line is None for r in rows["formula"])
