from pathlib import Path

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


def test_findings_does_not_flag_a_display_environment_as_unresolved(tmp_path):
    r"""661 finding 2 — `findings()` is a SECOND, independent
    classification of "does this row render" (this module's own docstring:
    ported over row objects, not delegating to report_tex.findings_rows),
    so fixing the latter alone leaves residuals.pdf disagreeing with it on
    the exact population this task targets. RULE 17: a genuine display
    environment, never already `aligned`."""
    raw = r"\begin{split} a &= b \\ c &= d \end{split}"
    rows = {"equation": [EquationRow(identifier="D_EQ0100", latex=raw,
                                     confidence=0.9)],
           "formula": [], "table": [], "image": []}
    found = R.findings(rows, tmp_path)
    assert found["unresolved"] == []


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


def test_build_html_is_one_shell_around_every_section(tmp_path):
    s = R.select(_rows(), _found(), conf=0.1)
    r = R.build(s, "html", doc_dir=tmp_path, pdf=tmp_path / "D.pdf", bibkey="D",
                history=None, px2mm=None, paper="a3", landscape=True,
                pages=10, compile_pdf=False)
    body = r["out"].read_text()
    assert body.startswith("<!DOCTYPE html>")
    assert body.count("<!DOCTYPE") == 1
    assert body.count("<head>") == 1
    assert body.count("</body></html>") == 1
    header = R.header_lines(tmp_path)[0]
    assert body.index(header) < body.index("<h2>")


def test_build_html_when_only_corrected_is_open(tmp_path):
    found = {"corrected": [{"identifier": "D_EQ0009", "before": "a", "after": "b"}],
            "unresolved": [], "flagged": [], "doubted": []}
    s = R.select({}, found, conf=0.1)
    r = R.build(s, "html", doc_dir=tmp_path, pdf=tmp_path / "D.pdf", bibkey="D",
                history=None, px2mm=None, paper="a3", landscape=True,
                pages=10, compile_pdf=False)
    body = r["out"].read_text()
    assert body.startswith("<!DOCTYPE html>")
    assert R.header_lines(tmp_path)[0] in body
    assert "<h2>Corrected (1)</h2>" in body


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


# ---------------------------------------------------------------------- #
# 655 review round 1, finding 4 -- a corrected pair must route its crop
# through the SAME (possibly budget-scaled) row object every other section
# already uses, not a fresh full-size lookup keyed on identifier alone.
# ---------------------------------------------------------------------- #

def _real_jpg(path, w, h, color):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (w, h), color=color).save(path, "JPEG", quality=90)


def test_select_stamps_the_rows_own_crop_onto_a_corrected_pair(tmp_path):
    scaled = tmp_path / "report-crops-b" / "D_EQ0009.jpg"
    rows = {"equation": [EquationRow(identifier="D_EQ0009", latex="x",
                                     crop=scaled, px_width="999")],
            "formula": [], "table": [], "image": []}
    found = {"corrected": [{"identifier": "D_EQ0009", "before": "a", "after": "b"}],
            "unresolved": [], "flagged": [], "doubted": []}
    s = R.select(rows, found, conf=0.1)
    pair = s["corrected"][0]
    assert pair["_crop"] == scaled
    assert pair["_px_width"] == "999"


def test_select_leaves_no_crop_when_the_identifier_has_no_row(tmp_path):
    found = {"corrected": [{"identifier": "D_EQ0009", "before": "a", "after": "b"}],
            "unresolved": [], "flagged": [], "doubted": []}
    s = R.select({}, found, conf=0.1)
    assert s["corrected"][0]["_crop"] is None
    assert s["corrected"][0]["_px_width"] == ""


def test_build_pdf_routes_the_corrected_crop_through_the_budgeted_copy(tmp_path):
    """The decisive case the original corpus spot-check missed (it had zero
    corrected pairs): a REAL full-size crop and a REAL, DIFFERENT scaled
    crop both exist on disk; the row's `.crop` points at the scaled one, so
    the compiled .tex must reference `report-crops-b/`, not `report-crops/`,
    and the emitted width must come from the row's `px_width` (the
    ORIGINAL pixel width), not the scaled file's own."""
    full = tmp_path / "report-crops" / "D_EQ0009.jpg"
    scaled = tmp_path / "report-crops-b" / "D_EQ0009.jpg"
    _real_jpg(full, 1000, 800, (10, 10, 10))       # full size -- must NOT be read
    _real_jpg(scaled, 420, 336, (200, 200, 200))   # what the row actually points at

    rows = {"equation": [EquationRow(identifier="D_EQ0009", latex="x=y",
                                     crop=scaled, px_width="1000")],
            "formula": [], "table": [], "image": []}
    found = {"corrected": [{"identifier": "D_EQ0009", "before": "x=z", "after": "x=y"}],
            "unresolved": [], "flagged": [], "doubted": []}
    s = R.select(rows, found, conf=0.1)
    r = R.build(s, "pdf", doc_dir=tmp_path, pdf=tmp_path / "D.pdf", bibkey="D",
               history=None, px2mm=0.1, paper="a3", landscape=True,
               pages=10, compile_pdf=False)
    tex = (tmp_path / "residuals.tex").read_text()
    assert "report-crops-b/D_EQ0009.jpg" in tex
    assert "report-crops/D_EQ0009.jpg" not in tex
    assert tex.count("report-crops-b/D_EQ0009.jpg") == 2   # "(was)" and "(now)" rows
    # width computed from px_width=1000 (the ORIGINAL), not the scaled
    # file's own 420px -- 1000 * 0.1 = 100.0mm.
    import re
    width_m = re.search(r"width=([\d.]+)mm\]\{report-crops-b/D_EQ0009\.jpg\}", tex)
    assert width_m is not None and float(width_m.group(1)) == 100.0


def test_build_reports_over_budget_against_the_compiled_artefact(tmp_path, monkeypatch):
    def fake_compile(tex_path):
        tex_path.with_suffix(".pdf").write_bytes(b"0" * 21_000_000)
        return (1, 0, 0)
    monkeypatch.setattr(R.rt, "compile_fixpoint", fake_compile)
    s = R.select(_rows(), _found(), conf=0.1)
    r = R.build(s, "pdf", doc_dir=tmp_path, pdf=tmp_path / "D.pdf", bibkey="D",
               history=None, px2mm=None, paper="a3", landscape=True,
               pages=10, compile_pdf=True, budget_mb=20.0)
    assert r["over_budget"] is True and r["bytes"] == 21_000_000


def test_build_names_only_the_rungs_of_kinds_actually_present(tmp_path, monkeypatch):
    """655 review round 2 -- residuals.pdf can mix equation and formula
    rows, so there is no single "the rung"; `res["rungs"]` must name
    exactly the kinds THIS build drew from (both, here -- `_rows()` has
    both), each with its own REAL rung, and nothing for a kind (table,
    image) that never appears."""
    monkeypatch.setattr(R.rt, "compile_fixpoint", lambda p: (1, 0, 0))
    s = R.select(_rows(), _found(), conf=0.1)
    r = R.build(s, "pdf", doc_dir=tmp_path, pdf=tmp_path / "D.pdf", bibkey="D",
               history=None, px2mm=None, paper="a3", landscape=True,
               pages=10, compile_pdf=True, budget_mb=20.0,
               rungs={"equation": (0.85, 75), "formula": (0.60, 72),
                     "table": None, "image": None})
    assert r["rungs"] == {"equation": (0.85, 75), "formula": (0.60, 72)}


def test_build_without_rungs_arg_still_names_the_kinds_present(tmp_path, monkeypatch):
    """`rungs=None` (a caller that never scaled anything) must not crash --
    every kind present is reported as `None` (full size), truthfully."""
    monkeypatch.setattr(R.rt, "compile_fixpoint", lambda p: (1, 0, 0))
    s = R.select(_rows(), _found(), conf=0.1)
    r = R.build(s, "pdf", doc_dir=tmp_path, pdf=tmp_path / "D.pdf", bibkey="D",
               history=None, px2mm=None, paper="a3", landscape=True,
               pages=10, compile_pdf=True, budget_mb=20.0)
    assert r["rungs"] == {"equation": None, "formula": None}


