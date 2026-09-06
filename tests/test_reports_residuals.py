from pdfdrill.reports import residuals as R
from pdfdrill.reports.rows import EquationRow, FormulaRow, HostLine


def _rows():
    return {"equation": [
                EquationRow(identifier="D_EQ0001", latex="x", confidence=0.02,
                            ink={"flag": "clean", "code": "K|0"}),      # doubted
                EquationRow(identifier="D_EQ0002", latex="y", confidence=0.95,
                            ink={"flag": "component", "code": "C|+40"}),  # flagged
                EquationRow(identifier="D_EQ0003", latex="z", confidence=0.05),  # lowconf
                EquationRow(identifier="D_EQ0004", latex="w", confidence=0.99),
                EquationRow(identifier="D_EQ0005", latex="\\bad{", confidence=0.5)],  # unresolved
            "formula": [FormulaRow(identifier="D_FO0001", latex="\\bad{",
                                   host_line=HostLine(page=1, confidence=0.01))],
            "table": [], "image": []}


def _found():
    return {"corrected": [{"identifier": "D_EQ0009", "before": "a", "after": "b"}],
            "unresolved": [{"identifier": "D_EQ0005", "page": "1", "latex": "\\bad{",
                            "why": "does not render"},
                           {"identifier": "D_FO0001", "page": "1", "latex": "\\bad{",
                            "why": "does not render"}],
            "flagged": [{"identifier": "D_EQ0002", "page": "1", "latex": "y",
                         "conf": 0.95, "code": "C|+40"}],
            "doubted": [{"identifier": "D_EQ0001", "page": "1", "latex": "x",
                         "conf": 0.02, "code": "K|0"}]}


def test_sections_in_order_and_membership():
    s = R.select(_rows(), _found(), conf=0.1)
    assert R.SECTIONS == ("corrected", "unresolved", "flagged", "lowconf", "doubted")
    assert [p["identifier"] for p in s["corrected"]] == ["D_EQ0009"]
    assert [r.identifier for r in s["unresolved"]] == ["D_FO0001", "D_EQ0005"]  # conf asc
    assert [r.identifier for r in s["flagged"]] == ["D_EQ0002"]
    assert [r.identifier for r in s["lowconf"]] == ["D_EQ0003"]
    assert [r.identifier for r in s["doubted"]] == ["D_EQ0001"]


def test_a_row_appears_in_one_section_only():
    s = R.select(_rows(), _found(), conf=0.1)
    seen = [r.identifier for k in R.SECTIONS[1:] for r in s[k]]
    assert len(seen) == len(set(seen))
    assert "D_EQ0001" not in [r.identifier for r in s["lowconf"]]   # doubted wins


def test_a_host_line_confidence_never_flags_a_formula():
    s = R.select(_rows(), _found(), conf=0.1)
    assert all(r.identifier != "D_FO0001" for r in s["lowconf"])
    assert all(r.identifier != "D_FO0001" for r in s["flagged"])


def test_unresolved_rows_keep_their_row_objects():
    s = R.select(_rows(), _found(), conf=0.1)
    fo = [r for r in s["unresolved"] if r.identifier == "D_FO0001"][0]
    assert fo.host_line.page == 1


def test_the_flagged_band_is_stated_not_listed():
    found = _found()
    found["flagged"].append({"identifier": "D_EQ0004", "page": "1", "latex": "w",
                             "conf": 0.99, "code": "W|+1"})
    s = R.select(_rows(), found, conf=0.1)
    assert [r.identifier for r in s["flagged"]] == ["D_EQ0002"]
    assert s["flagged_rest"]["n"] == 1


def test_findings_classifies_from_row_objects(tmp_path):
    found = R.findings(_rows(), tmp_path)
    assert [r["identifier"] for r in found["unresolved"]] == ["D_EQ0005", "D_FO0001"]
    assert [r["identifier"] for r in found["flagged"]] == ["D_EQ0002"]
    assert [r["identifier"] for r in found["doubted"]] == ["D_EQ0001"]


import json


def test_header_names_the_measurement_time_and_the_model(tmp_path):
    (tmp_path / "report.ink.json").write_text(json.dumps({
        "rows": [], "measured_against": {"built_at": "2026-09-05T10:57:49Z",
                                         "model_mtime": 1788385038,
                                         "model_sha256": "abc"}}))
    lines = R.header_lines(tmp_path)
    assert any("measured 2026-09-05T10:57:49Z" in l for l in lines)
    assert any("model of 2026-09-02" in l for l in lines)


def test_header_says_so_when_nothing_was_measured(tmp_path):
    assert any("no ink measurement" in l for l in R.header_lines(tmp_path))


def test_build_html_lists_sections_worst_first(tmp_path):
    found = _found()
    found["flagged"].append({"identifier": "D_EQ0004", "page": "1", "latex": "w",
                             "conf": 0.99, "code": "W|+1"})
    s = R.select(_rows(), found, conf=0.1)
    r = R.build(s, "html", doc_dir=tmp_path, pdf=tmp_path / "D.pdf", bibkey="D",
                history=None, px2mm=None, paper="a3", landscape=True,
                pages=10, compile_pdf=False)
    body = r["out"].read_text()
    assert r["out"].name == "residuals.html"
    order = [body.index(R.CAPTIONS[k]) for k in R.SECTIONS if s[k]]
    assert order == sorted(order)
    assert "1 more flagged" in body or "stated as a count" in body


def test_build_pdf_has_legend_bullets_and_a_page_bound(tmp_path, monkeypatch):
    monkeypatch.setattr(R.rt, "compile_fixpoint", lambda p: (1, 0, 0))
    monkeypatch.setattr(R.rt, "findings_tex", lambda *a, **k: "%% pairs\n")
    s = R.select(_rows(), _found(), conf=0.1)
    R.build(s, "pdf", doc_dir=tmp_path, pdf=tmp_path / "D.pdf", bibkey="D",
            history=None, px2mm=None, paper="a3", landscape=True,
            pages=10, compile_pdf=True)
    tex = (tmp_path / "residuals.tex").read_text()
    assert "\\usepackage[1-10]{pagesel}" in tex
    assert "\\endfoot" in tex and "\\inkbullet{" in tex
    assert "Low confidence" in tex


def test_cli_and_lock():
    import ast, inspect
    from pdfdrill import commands
    from pdfdrill.cli import HANDLERS
    assert "residuals" in HANDLERS
    fn = ast.parse(inspect.getsource(commands.cmd_residuals)).body[0]
    assert any(getattr(d.func, "id", "") == "_writes" for d in fn.decorator_list
               if isinstance(d, ast.Call))
