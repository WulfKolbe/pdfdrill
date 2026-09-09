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


def _fake_compile(size_bytes):
    """A `compile_fixpoint` stand-in that writes a REAL file of a chosen
    size at the expected `.pdf` path, so `budget.check_artifact` (which
    reads `stat().st_size`) has something real to measure -- 655 review
    round 1, finding 3."""
    def compile_fixpoint(tex_path):
        tex_path.with_suffix(".pdf").write_bytes(b"0" * size_bytes)
        return (1, 0, 0)
    return compile_fixpoint


def test_build_reports_over_budget_against_the_compiled_artefact(tmp_path, monkeypatch):
    """The `over_budget` verdict is checked against the FILE `compile_
    fixpoint` actually produced, not the crop-byte prediction from
    `ensure_crops` (which `build` never even sees)."""
    import pdfdrill.reports.evidence as mod
    monkeypatch.setattr(mod.rt, "compile_fixpoint", _fake_compile(21_000_000))
    r = E.build(_rows(), "equation", "pdf", doc_dir=tmp_path,
                pdf=tmp_path / "D.pdf", bibkey="D", history=None,
                px2mm=None, paper="a3", landscape=True, compile_pdf=True,
                budget_mb=20.0)
    assert r["bytes"] == 21_000_000
    assert r["over_budget"] is True
    assert r["budget_mb"] == 20.0


def test_build_under_budget_is_not_flagged(tmp_path, monkeypatch):
    import pdfdrill.reports.evidence as mod
    monkeypatch.setattr(mod.rt, "compile_fixpoint", _fake_compile(19_000_000))
    r = E.build(_rows(), "equation", "pdf", doc_dir=tmp_path,
                pdf=tmp_path / "D.pdf", bibkey="D", history=None,
                px2mm=None, paper="a3", landscape=True, compile_pdf=True,
                budget_mb=20.0)
    assert r["over_budget"] is False


def test_build_without_budget_mb_carries_no_verdict_at_all(tmp_path, monkeypatch):
    """A caller that never asks (`budget_mb=None`, e.g. an HTML build) gets
    no `over_budget`/`bytes` keys rather than a silently-false verdict --
    `_evidence_line`'s `.get("over_budget")` treats absence the same as
    False, but the DATA should not claim to have checked when it did not."""
    import pdfdrill.reports.evidence as mod
    monkeypatch.setattr(mod.rt, "compile_fixpoint", _fake_compile(99_000_000))
    r = E.build(_rows(), "equation", "pdf", doc_dir=tmp_path,
                pdf=tmp_path / "D.pdf", bibkey="D", history=None,
                px2mm=None, paper="a3", landscape=True, compile_pdf=True)
    assert "over_budget" not in r and "bytes" not in r


def test_evidence_line_shows_the_real_compiled_size_when_over_budget():
    from pdfdrill.commands import _evidence_line
    r = {"out": Path("evidence-formula.pdf"), "rows": 4594, "pages": 900,
        "errors": 0, "demoted": 0, "bytes": 20_400_000, "over_budget": True,
        "budget_mb": 20.0}
    line = _evidence_line(r, pdf_out=True, compile_pdf=True)
    assert "OVER BUDGET" in line
    assert "20.4MB" in line and "20.0MB" in line


def test_evidence_line_says_nothing_extra_when_under_budget():
    from pdfdrill.commands import _evidence_line
    r = {"out": Path("evidence-formula.pdf"), "rows": 4, "pages": 1,
        "errors": 0, "demoted": 0, "bytes": 1_000_000, "over_budget": False,
        "budget_mb": 20.0}
    assert "OVER BUDGET" not in _evidence_line(r, pdf_out=True, compile_pdf=True)


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


def test_cmd_evidence_wires_up_keyless_math_steering():
    """task 10 fix round 1 — `cmd_evidence` must still reach for
    `_keyless_math_steering` (extracted so the GATE is unit-testable without
    stubbing Sidecar/mathqc; see the behavioural tests below) and still gate
    computing it on the equation kind having been asked for."""
    import inspect
    from pdfdrill import commands
    src = inspect.getsource(commands.cmd_evidence)
    assert "_keyless_math_steering" in src
    assert "NEEDS_VISION_OCR" in src


def test_keyless_math_steering_fires_when_nothing_rendered_at_all():
    """task 10 fix round 1 — the old `cmd_report` gate was `inline == 0 and eqs
    == 0`; the ported version briefly regressed to `eqs == 0` alone, which
    fired spuriously on a document with inline formulas but no display
    equations. Both counts must be zero."""
    from pdfdrill.commands import _keyless_math_steering
    msg = _keyless_math_steering("D.pdf", inline=0, eqs=0, bearing=True,
                                 why="math-bearing")
    assert "visionocr" in msg
    assert "injectlatex" not in msg          # no arxiv id passed
    assert "then re-run `evidence`." in msg
    assert "then re-run `report`." not in msg


def test_keyless_math_steering_silent_when_inline_formulas_exist():
    """The exact regression this fix round addresses: inline formulas present,
    zero equations — must NOT print the keyless-tesseract warning."""
    from pdfdrill.commands import _keyless_math_steering
    assert _keyless_math_steering("D.pdf", inline=3, eqs=0, bearing=True,
                                  why="math-bearing") == ""


def test_keyless_math_steering_silent_when_equations_exist():
    from pdfdrill.commands import _keyless_math_steering
    assert _keyless_math_steering("D.pdf", inline=0, eqs=2, bearing=True,
                                  why="math-bearing") == ""


def test_keyless_math_steering_silent_when_not_math_bearing():
    from pdfdrill.commands import _keyless_math_steering
    assert _keyless_math_steering("D.pdf", inline=0, eqs=0, bearing=False,
                                  why="") == ""


def test_keyless_math_steering_names_injectlatex_only_with_an_arxiv_id():
    from pdfdrill.commands import _keyless_math_steering
    msg = _keyless_math_steering("D.pdf", inline=0, eqs=0, bearing=True,
                                 why="math-bearing", aid="2010.14265")
    assert "injectlatex D.pdf" in msg
    assert "mathpix" in msg
