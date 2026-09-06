from pathlib import Path

from pdfdrill.reports import COLUMNS
from pdfdrill.reports.rows import EquationRow, FormulaRow, HostLine
from pdfdrill.reports import html as H
from pdfdrill.reports.tex import HOST_LINE_SENTENCE


def test_six_columns_and_katex(tmp_path):
    page = H.render_page([EquationRow(identifier="D_EQ0001", latex="a<b",
                                      page="2", confidence=0.95)],
                         "equation", title="D", doc_dir=tmp_path)
    for h in COLUMNS:
        assert "<th>%s</th>" % h in page
    assert 'data-latex="a&lt;b"' in page and "katex.min.js" in page
    assert "KaTeX" in page                        # the caveat banner


def test_formula_row_links_the_host_line_crop_relative(tmp_path):
    crop = tmp_path / "report-crops" / "D_FO0001.jpg"
    crop.parent.mkdir()
    crop.write_bytes(b"x")
    h = HostLine(page=4, confidence=0.5, region={})
    page = H.render_page([FormulaRow(identifier="D_FO0001", latex="P",
                                     host_line=h, crop=crop)],
                         "formula", title="D", doc_dir=tmp_path)
    assert HOST_LINE_SENTENCE.replace("---", "—") in page or \
        HOST_LINE_SENTENCE in page
    assert '<img src="report-crops/D_FO0001.jpg"' in page
    assert "<td>4</td>" in page and "0.500" in page


def test_missing_values_are_dashes(tmp_path):
    page = H.render_page([FormulaRow(identifier="D_FO0002", latex="")],
                         "formula", title="D", doc_dir=tmp_path)
    assert page.count("<td>---</td>") >= 3


def test_ink_codes_off_by_default_on_for_residuals(tmp_path):
    row = EquationRow(identifier="D_EQ0001", latex="a", confidence=0.5,
                      ink={"flag": "weak", "code": "W|+1"})
    default_page = H.render_page([row], "equation", title="D", doc_dir=tmp_path)
    assert "W|+1" not in default_page

    ink_page = H.render_page([row], "equation", title="D", doc_dir=tmp_path,
                             ink_codes=True)
    assert "<code>W|+1</code>" in ink_page


def test_page_shell_wraps_a_section_once(tmp_path):
    page = H.page_shell("T", "<p>x</p>")
    assert page.startswith("<!DOCTYPE html>")
    assert page.count("<!DOCTYPE") == 1 and page.count("<head>") == 1
    assert "<p>x</p>" in page and page.rstrip().endswith("</body></html>")


def test_render_section_has_no_doctype(tmp_path):
    section = H.render_section(
        [EquationRow(identifier="D_EQ0001", latex="a", confidence=0.5)],
        "equation", doc_dir=tmp_path)
    assert "<!DOCTYPE" not in section and "<head>" not in section
    assert section.startswith("<h2>") and "<table>" in section
