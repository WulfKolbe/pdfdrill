# tests/test_reports_tex.py
from pathlib import Path

from pdfdrill.reports import COLUMNS
from pdfdrill.reports.rows import EquationRow, FormulaRow, HostLine
from pdfdrill.reports import tex as T


def _jpg(d: Path, name: str):
    d.mkdir(exist_ok=True)
    p = d / name
    p.write_bytes(b"\xff\xd8" + b"0" * 600)
    return p


def test_six_columns_for_every_kind(tmp_path):
    w = T.widths_for("a3", True, with_image=True)
    assert len(w) == 6
    body = T.render_table([EquationRow(identifier="D_EQ0001", latex="a=b",
                                       page="2", confidence=0.9)],
                          "equation", widths=w, out_dir=tmp_path, px2mm=None,
                          bibkey="D")
    for h in COLUMNS[:-1]:
        assert "\\textbf{%s}" % h in body
    assert "\\textbf{Image}" in body
    assert body.count(" & ") >= 5


def test_formula_row_shows_host_line_values_and_the_sentence(tmp_path):
    crop = _jpg(tmp_path / "report-crops", "D_FO0001.jpg")
    h = HostLine(page=4, confidence=0.98, region={"width": 800})
    r = FormulaRow(identifier="D_FO0001", latex="P", host_line=h, crop=crop)
    w = T.widths_for("a3", True, with_image=True)
    body = T.render_table([r], "formula", widths=w, out_dir=tmp_path,
                          px2mm=None, bibkey="D")
    assert T.HOST_LINE_SENTENCE in body
    assert "& 4 &" in body
    assert "\\confcell{confgreen}{0.980}" in body
    assert "report-crops/D_FO0001.jpg" in body


def test_formula_without_host_line_is_dashes(tmp_path):
    r = FormulaRow(identifier="D_FO0002", latex="\\square")
    body = T.render_table([r], "formula",
                          widths=T.widths_for("a3", True, True),
                          out_dir=tmp_path, px2mm=None, bibkey="D")
    assert "& --- & --- &" in body
    assert body.rstrip().endswith("\\end{longtable}")


def test_document_wraps_a_body_with_the_report_preamble():
    doc = T.document("BODY", paper="a3", landscape=True, pages=None,
                     title="Evidence")
    assert doc.startswith("%") and "\\begin{document}" in doc
    assert "BODY" in doc and doc.rstrip().endswith("\\end{document}")
    assert "pagesel" not in doc
    assert "\\usepackage[1-3]{pagesel}" in T.document(
        "x", paper="a3", landscape=True, pages=3)
    assert "\\newcommand{\\inkbullet}" in T.document(
        "x", paper="a3", landscape=True, form=True)


def test_standalone_math_gets_the_real_out_dir(tmp_path, monkeypatch):
    """The refused-for-align-only branch used to hardcode Path(".") as
    standalone_math's out_dir, so the PNG landed relative to the process
    cwd rather than the report's own directory and \\includegraphics broke
    when the compile ran elsewhere."""
    captured = {}
    monkeypatch.setattr(T.rt, "refused_for_align_only", lambda latex: True)

    def fake_standalone_math(latex, ident, out_dir, col_mm=100.0):
        captured["out_dir"] = out_dir
        return "SA"

    monkeypatch.setattr(T.rt, "standalone_math", fake_standalone_math)
    r = EquationRow(identifier="D_EQ0009", latex="a & b")
    widths = T.widths_for("a3", True, True)
    body = T.render_row(r, widths, out_dir=tmp_path, px2mm=None, bibkey="D")
    assert captured["out_dir"] == Path(tmp_path)
    assert "SA" in body


def test_no_legend_and_no_bullets_by_default(tmp_path):
    body = T.render_table([EquationRow(identifier="D_EQ0001", latex="x")],
                          "equation", widths=T.widths_for("a3", True, True),
                          out_dir=tmp_path, px2mm=None, bibkey="D")
    assert "\\endfoot" not in body and "\\inkbullet" not in body
