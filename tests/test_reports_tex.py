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


def test_rendered_maps_a_display_environment_but_source_keeps_it_raw(tmp_path):
    r"""661 finding 1 — `_rendered()` backs evidence-equation.pdf/report.pdf,
    the artifact `docs/HANDOVER.md:25-42` names as the PUBLISHED surface;
    the bare gate here left a `split`/`align`/etc.-carrying row demoted to
    "(not rendered)" even after report_tex.row() was fixed, because this is
    a SEPARATE call site. RULE 17: this fixture is a genuine display
    environment (`\begin{split}` with a bare `&`/`\\` inside), never
    already `aligned`."""
    raw = r"\begin{split} a &= b \\ c &= d \end{split}"
    r = EquationRow(identifier="D_EQ0099", latex=raw, page="3")
    w = T.widths_for("a3", True, with_image=False)
    body = T.render_row(r, w, out_dir=tmp_path, px2mm=None, bibkey="D")
    assert "(not rendered)" not in body
    assert r"\begin{aligned}" in body        # the RENDERED cell: mapped
    # the SOURCE cell: the raw environment name, unmapped, escaped verbatim
    from pdfdrill import report_tex as rt
    assert rt.esc_text(raw) in body
    # the raw name must not survive inside \FitMath's own argument
    start = body.index(r"\FitMath{$\displaystyle ")
    arg = body[start:body.index("$}", start)]
    assert r"\begin{split}" not in arg


def test_a_refined_row_is_marked_in_the_identifier_column_not_the_source_one(tmp_path):
    """669 -- `refined_flag` (233, reused not rebuilt) goes beside `conf_flag`
    in the Identifier cell, matching 064's own reason for putting confidence
    there: the LaTeX-source/Rendered/Scan cells stay whatever they would be
    for any other row (HANDOVER-RULES rule 16's free control), so the mark
    has to live somewhere else."""
    r = EquationRow(identifier="D_EQ0001", latex="c=d", page="3",
                    refined_info={"basis": "measured", "verified_by": "ink"})
    w = T.widths_for("a3", True, with_image=False)
    body = T.render_row(r, w, out_dir=tmp_path, px2mm=None, bibkey="D")
    assert "[refined: measured]" in body
    ident_cell = body.split(" & ")[0]
    assert "[refined" in ident_cell
    src_cell = body.split(" & ")[3]
    assert "[refined" not in src_cell


def test_an_unrefined_row_carries_no_mark(tmp_path):
    r = EquationRow(identifier="D_EQ0002", latex="a=b", page="3")
    w = T.widths_for("a3", True, with_image=False)
    body = T.render_row(r, w, out_dir=tmp_path, px2mm=None, bibkey="D")
    assert "refined" not in body


def test_no_legend_and_no_bullets_by_default(tmp_path):
    body = T.render_table([EquationRow(identifier="D_EQ0001", latex="x")],
                          "equation", widths=T.widths_for("a3", True, True),
                          out_dir=tmp_path, px2mm=None, bibkey="D")
    assert "\\endfoot" not in body and "\\inkbullet" not in body
