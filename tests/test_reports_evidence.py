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
