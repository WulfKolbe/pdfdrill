import json
from pathlib import Path

import pytest

from pdfdrill.reports import evidence as E
from pdfdrill.reports.rows import EquationRow, FormulaRow, HostLine


def _rows():
    return {"equation": [EquationRow(identifier="D_EQ0002", latex="b", confidence=0.3),
                         EquationRow(identifier="D_EQ0001", latex="a", confidence=0.9),
                         EquationRow(identifier="D_EQ0003", latex="c")],
            "formula": [FormulaRow(identifier="D_FO0001", latex="P",
                                   host_line=HostLine(page=1, confidence=0.9))],
            "table": [], "image": []}


def test_html_output_name_and_content(tmp_path):
    r = E.build(_rows(), "formula", "html", doc_dir=tmp_path,
                pdf=tmp_path / "D.pdf", bibkey="D", history=None,
                px2mm=None, paper="a3", landscape=True, compile_pdf=False)
    assert r["out"] == tmp_path / "evidence-formula.html"
    assert "D_FO0001" in r["out"].read_text()
    assert r["rows"] == 1


def test_equations_sort_by_confidence_ascending_absent_last(tmp_path):
    r = E.build(_rows(), "equation", "html", doc_dir=tmp_path,
                pdf=tmp_path / "D.pdf", bibkey="D", history=None,
                px2mm=None, paper="a3", landscape=True, compile_pdf=False)
    body = r["out"].read_text()
    assert body.index("D_EQ0002") < body.index("D_EQ0001") < body.index("D_EQ0003")


def test_pdf_format_writes_tex_without_a_page_bound(tmp_path, monkeypatch):
    import pdfdrill.reports.evidence as mod
    monkeypatch.setattr(mod.rt, "compile_fixpoint", lambda p: (2, 0, 0))
    r = E.build(_rows(), "equation", "pdf", doc_dir=tmp_path,
                pdf=tmp_path / "D.pdf", bibkey="D", history=None,
                px2mm=None, paper="a3", landscape=True, compile_pdf=True)
    tex = (tmp_path / "evidence-equation.tex").read_text()
    assert "pagesel" not in tex and "\\inkbullet" not in tex
    assert r["pages"] == 2


def test_unknown_kind_or_format_is_refused(tmp_path):
    with pytest.raises(ValueError):
        E.build(_rows(), "prose", "html", doc_dir=tmp_path, pdf=tmp_path / "D.pdf",
                bibkey="D", history=None, px2mm=None, paper="a3",
                landscape=True, compile_pdf=False)
    with pytest.raises(ValueError):
        E.build(_rows(), "equation", "docx", doc_dir=tmp_path, pdf=tmp_path / "D.pdf",
                bibkey="D", history=None, px2mm=None, paper="a3",
                landscape=True, compile_pdf=False)


def test_cmd_evidence_is_a_locked_handler():
    import ast, inspect
    from pdfdrill import commands
    src = inspect.getsource(commands.cmd_evidence)
    fn = ast.parse(src).body[0]
    assert any(getattr(d.func, "id", "") == "_writes" for d in fn.decorator_list
               if isinstance(d, ast.Call))


def test_cli_knows_evidence():
    from pdfdrill.cli import HANDLERS
    assert "evidence" in HANDLERS


def test_evidence_line_html_has_no_pdf_parenthetical():
    from pdfdrill.commands import _evidence_line
    r = {"out": Path("evidence-formula.html"), "rows": 3, "pages": None,
        "errors": 0, "demoted": 0}
    assert _evidence_line(r, pdf_out=False, compile_pdf=True) == \
        "Wrote evidence-formula.html: 3 rows"


def test_evidence_line_pdf_compiled_reports_pages():
    from pdfdrill.commands import _evidence_line
    r = {"out": Path("evidence-equation.pdf"), "rows": 5, "pages": 2,
        "errors": 0, "demoted": 1}
    assert _evidence_line(r, pdf_out=True, compile_pdf=True) == \
        "Wrote evidence-equation.pdf: 5 rows (2 pages, 0 errors, 1 demoted)"


def test_evidence_line_no_compile_says_not_compiled_not_xelatex_missing():
    from pdfdrill.commands import _evidence_line
    r = {"out": Path("evidence-equation.pdf"), "rows": 5, "pages": None,
        "errors": 0, "demoted": 0}
    assert _evidence_line(r, pdf_out=True, compile_pdf=False) == \
        "Wrote evidence-equation.pdf: 5 rows (not compiled; .tex written)"


def test_evidence_line_compile_requested_but_xelatex_missing():
    from pdfdrill.commands import _evidence_line
    r = {"out": Path("evidence-equation.pdf"), "rows": 5, "pages": None,
        "errors": 0, "demoted": 0}
    assert _evidence_line(r, pdf_out=True, compile_pdf=True) == \
        "Wrote evidence-equation.pdf: 5 rows (xelatex not installed; .tex written)"


def test_cmd_evidence_produces_report_built():
    """task 10 fix round — REPORT_BUILT's producer moved from the old
    `cmd_report` body to `cmd_evidence` (`report` is now a thin alias of it).
    `capgraph._MODEL_DERIVED` still claims a model rebuild destroys
    REPORT_BUILT, so something must still produce it."""
    import ast, inspect
    from pdfdrill import commands
    src = inspect.getsource(commands.cmd_evidence)
    tree = ast.parse(src)
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "REPORT_BUILT" in names, "cmd_evidence no longer names REPORT_BUILT"
    assert "add_fact" in src, "cmd_evidence must call add_fact(REPORT_BUILT)"


def test_cmd_evidence_steers_to_recovery_when_math_bearing_and_keyless():
    """task 10 fix round — the keyless-math steering message (arXiv gold ->
    visionocr -> mathpix), ported verbatim from the pre-alias `cmd_report`
    (bfcc0d0), must still exist once `report` no longer builds it itself."""
    import inspect
    from pdfdrill import commands
    src = inspect.getsource(commands.cmd_evidence)
    assert "NEEDS_VISION_OCR" in src
    assert "visionocr" in src
    assert "injectlatex" in src and "mathpix" in src
