import json

from pdfdrill.reports.from_tiddlers import build_rows
from pdfdrill.reports.rows import EquationRow, FormulaRow, TableRow, ImageRow

BK = "DOC"


def _tiddlers():
    return [
        {"title": "DOC_EQ0001", "latex": "a=b", "page": "2",
         "equation_number": "(1)", "width": "300", "confidence": "0.91",
         "trailing_punct": "."},
        {"title": "DOC_FO0001", "latex": "P"},
        {"title": "DOC_FO0002", "latex": "\\square"},
        {"title": "DOC_TAB0001", "mathpix_text": "\\begin{tabular}{c}1\\end{tabular}",
         "page": "5", "width": "400", "height": "80", "top_left_x": "1",
         "top_left_y": "2", "confidence": "0.7"},
        {"title": "DOC_DIA0001", "latex": "", "page": "6", "width": "100",
         "height": "50", "top_left_x": "3", "top_left_y": "4"},
        {"title": "prose", "page": "1", "text": "see {{DOC_FO0001||formula}}"},
    ]


def _lines(tmp_path):
    p = tmp_path / "DOC.lines.json"
    p.write_text(json.dumps({"pages": [
        {"lines": [{"type": "text", "text": "distribution \\(P\\) of",
                    "confidence": 0.98,
                    "region": {"top_left_x": 10, "top_left_y": 20,
                               "width": 800, "height": 40}}]}]}))
    return p


def test_every_kind_is_typed():
    rows = build_rows(_tiddlers(), BK)
    assert [type(r) for r in rows["equation"]] == [EquationRow]
    assert [type(r) for r in rows["formula"]] == [FormulaRow, FormulaRow]
    assert [type(r) for r in rows["table"]] == [TableRow]
    assert [type(r) for r in rows["image"]] == [ImageRow]


def test_equation_fields():
    (r,) = build_rows(_tiddlers(), BK)["equation"]
    assert (r.identifier, r.latex, r.page, r.eqnum, r.px_width,
            r.trailing_punct, r.confidence) == (
        "DOC_EQ0001", "a=b", "2", "(1)", "300", ".", 0.91)


def test_equation_carries_ink_when_given():
    ink = {"DOC_EQ0001": {"flag": "weak", "code": "W|+1"}}
    (r,) = build_rows(_tiddlers(), BK, ink=ink)["equation"]
    assert r.ink_code == "W|+1"


def test_formula_takes_its_host_line_from_lines_json(tmp_path):
    rows = build_rows(_tiddlers(), BK, lines_path=_lines(tmp_path))
    p, sq = rows["formula"]
    assert p.host_line.page == 1 and p.host_line.confidence == 0.98
    assert p.host_line.region == {"top_left_x": 10, "top_left_y": 20,
                                  "width": 800, "height": 40}
    assert sq.host_line is None          # \square has no span: reported, not defaulted


def test_formula_page_falls_back_to_first_transcluding_page():
    p, _ = build_rows(_tiddlers(), BK)["formula"]
    assert p.page == "1" and p.shown_page == "1"


def test_table_latex_is_mathpix_text():
    (t,) = build_rows(_tiddlers(), BK)["table"]
    assert t.latex.startswith("\\begin{tabular}")
    assert t.dims == ("400", "80") and t.confidence == 0.7


def test_missing_lines_json_is_not_an_error(tmp_path):
    rows = build_rows(_tiddlers(), BK, lines_path=tmp_path / "nope.json")
    assert all(r.host_line is None for r in rows["formula"])
