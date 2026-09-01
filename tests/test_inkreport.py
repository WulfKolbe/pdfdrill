"""404/405 — the one-command ink chain, and the preflight that spends nothing."""
import json
from pathlib import Path

import pytest

from pdfdrill import inkreport as ir


def _doc(tmp_path, *, model=True, lines=True, crops=0, bibkey="doc"):
    d = tmp_path / "doc"
    d.mkdir()
    pdf = d / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    if model:
        (d / "model.docmodel.json").write_text(json.dumps(
            {"meta": {"bibkey": bibkey, "pages": [{"page": 1}]}, "objects": []}))
    if lines:
        (d / "doc.lines.json").write_text("{}")
    if crops:
        c = d / "report-crops"
        c.mkdir()
        for i in range(crops):
            (c / ("%s_EQ%04d.jpg" % (bibkey, i))).write_bytes(b"x")
    return pdf, d


def test_preflight_spends_nothing_and_makes_no_request_when_crops_are_on_disk(
        tmp_path, monkeypatch):
    """The whole point of the guard: it decides from disk. With crops already
    there, not even the single probe fires."""
    pdf, d = _doc(tmp_path, crops=3)
    called = []
    monkeypatch.setattr(ir, "_probe", lambda *a, **k: called.append(a) or 200)
    ir.preflight(pdf, d)
    assert called == [], "preflight made a network request it did not need"


def test_a_paid_step_refuses_rather_than_running(tmp_path, monkeypatch):
    r"""Never spend without being asked.

    No lines.json means `mathpix` would have to run. That is the paid step,
    and the preflight's job is to say so and stop — not to run it, and not to
    run the four free steps that would be wasted without it.
    """
    pdf, d = _doc(tmp_path, lines=False, crops=3)
    monkeypatch.setattr(ir, "_probe", lambda *a, **k: 200)
    r = ir.preflight(pdf, d)
    assert not r["ok"]
    paid = dict((n, why) for n, ok, why in r["checks"] if not ok)
    assert "no paid step required" in paid
    assert "mathpix" in paid["no paid step required"]


def test_lines_json_must_be_THIS_document_s(tmp_path, monkeypatch):
    """404 — a flat folder holds many. The first version globbed
    `*.lines.json` and passed on a completely different document's file,
    which is worse than failing: a check that accepts someone else's evidence
    reports a readiness nobody has.
    """
    pdf, d = _doc(tmp_path, lines=False, crops=1)
    (d / "someone-else.lines.json").write_text("{}")
    monkeypatch.setattr(ir, "_probe", lambda *a, **k: 200)
    r = ir.preflight(pdf, d)
    got = dict((n, ok) for n, ok, _ in r["checks"])
    assert got["lines.json"] is False


def test_one_probe_decides_the_scan_column_and_a_pyramid_rescues_a_dead_cdn(
        tmp_path, monkeypatch):
    """401 measured that expiry is per pdf_id, not per crop — 22 published
    documents alive on one probe each, and the one dead document failing 107
    of 107. So one probe is the right cost. A 500 is only fatal when there is
    no local pyramid to serve the same regions from the PDF (396)."""
    pdf, d = _doc(tmp_path, crops=0)
    (d / "model.docmodel.json").write_text(json.dumps(
        {"meta": {"bibkey": "doc", "pages": [{"page": 1}]},
         "objects": [{"props": {"cdn_url": "https://cdn.example/x.jpg"}}]}))
    monkeypatch.setattr(ir, "_probe", lambda *a, **k: 500)
    r = ir.preflight(pdf, d)
    assert dict((n, ok) for n, ok, _ in r["checks"])["scan column"] is False

    (d / "viewer").mkdir()
    (d / "viewer" / "manifest.json").write_text("{}")
    r2 = ir.preflight(pdf, d)
    scan = [(ok, why) for n, ok, why in r2["checks"] if n == "scan column"][0]
    assert scan[0] is True and "pyramid" in scan[1]


def _resumable(d, *, sha="abc123", rule=""):
    """An ink + measure stamp that agree, dated in the resumable order."""
    import json, os
    (d / "report.build.measure.json").write_text(json.dumps(
        {"sha256": sha, "pages": 20, "phase": "measure", "formula_rule": rule}))
    ink = d / "report.ink.json"
    ink.write_text(json.dumps(
        {"rows": [{"id": "x_EQ0001"}], "measured_against": {"sha256": sha}}))
    os.utime(ink, (10 ** 9, 10 ** 9))
    os.utime(d / "report.build.measure.json", (10 ** 9 - 100, 10 ** 9 - 100))
    return ink


def test_resume_compares_against_the_measure_stamp_not_the_latest_build(tmp_path):
    """The reading build overwrites report.build.json, so comparing against it
    would make every finished document look resumable. The surviving
    phase=measure stamp is the one that dates the measurement."""
    import os
    pdf, d = _doc(tmp_path)
    assert ir.fresh_ink(d) is False
    ink = _resumable(d)
    assert ir.fresh_ink(d) is True
    os.utime(ink, (10 ** 9 - 200, 10 ** 9 - 200))
    assert ir.fresh_ink(d) is False


def test_resume_refuses_when_the_ink_measured_a_DIFFERENT_report(tmp_path):
    """463 — the defect. An ink and a stamp in the right mtime order are not
    evidence about each other; `measured_against` says which build was
    measured, and if it is not this one the residual describes another
    document."""
    pdf, d = _doc(tmp_path)
    import os
    _resumable(d, sha="aaa")
    (d / "report.build.measure.json").write_text(json.dumps(
        {"sha256": "bbb", "pages": 11, "formula_rule": ""}))
    os.utime(d / "report.build.measure.json", (10 ** 9 - 100, 10 ** 9 - 100))
    why = []
    assert ir.fresh_ink(d, why=why) is False
    assert "measured report aaa" in why[0]


def test_resume_refuses_across_a_change_of_formula_rule(tmp_path):
    """--profile published drops a whole section, so the page geometry the
    measurement was taken on no longer exists. This is what 463 hit."""
    pdf, d = _doc(tmp_path)
    _resumable(d, rule="")
    why = []
    assert ir.fresh_ink(d, formula_rule="none", why=why) is False
    assert "formula rule" in why[0]
    assert ir.fresh_ink(d, formula_rule="") is True


def test_resume_refuses_when_the_model_has_been_rebuilt(tmp_path):
    """430: object ids are uuid4, so a rebuild leaves 1 id in common out of
    2,196. A measurement joined by identifier then names objects that are
    gone."""
    pdf, d = _doc(tmp_path)
    _resumable(d)
    (d / "model.docmodel.json").write_text('{"objects": []}')
    from pdfdrill.report_tex import model_state
    st = json.loads((d / "report.build.measure.json").read_text())
    st["model_sha256"] = "0" * 64
    (d / "report.build.measure.json").write_text(json.dumps(st))
    import os
    os.utime(d / "report.build.measure.json", (10 ** 9 - 100, 10 ** 9 - 100))
    why = []
    assert ir.fresh_ink(d, why=why) is False
    assert "model changed" in why[0]
    # and it resumes again once the stamp names the model that is there
    st["model_sha256"] = model_state(d)["model_sha256"]
    (d / "report.build.measure.json").write_text(json.dumps(st))
    os.utime(d / "report.build.measure.json", (10 ** 9 - 100, 10 ** 9 - 100))
    assert ir.fresh_ink(d) is True


def test_resume_refuses_when_the_ink_does_not_say_what_it_measured(tmp_path):
    pdf, d = _doc(tmp_path)
    _resumable(d)
    (d / "report.ink.json").write_text(json.dumps({"rows": []}))
    import os
    os.utime(d / "report.ink.json", (10 ** 9, 10 ** 9))
    why = []
    assert ir.fresh_ink(d, why=why) is False
    assert "does not say which report" in why[0]


def test_the_bibkey_comes_from_the_model_not_the_directory_name(tmp_path):
    r"""404 — the defect this command found on its first real run.

    `publish_ready` inferred the bibkey from `blob_dir.name`. Under the
    self-contained layout the folder IS the bibkey, so it worked; under the
    legacy layout it is "<name>.pdf.drill", which matches no identifier. The
    residual check then reported a join failure and the index check reported
    "cannot read equations" — on a document whose 99 identifiers matched
    perfectly. Both are the false alarm those checks exist to raise.
    """
    from pdfdrill.commands import _bibkey_of
    d = tmp_path / "230209-algebraic_similarity.pdf.drill"
    d.mkdir()
    assert _bibkey_of(d) == d.name          # no model: the name is all there is
    (d / "model.docmodel.json").write_text(json.dumps(
        {"meta": {"bibkey": "230209-algebraic_similarity"}}))
    assert _bibkey_of(d) == "230209-algebraic_similarity"


def test_the_output_block_lists_only_files_that_exist(tmp_path):
    """408 — a command that produces files must present them, and must not
    name one it did not produce. Naming an absent artefact is the same defect
    as a check that passes on absent evidence.

    Asserted on the SOURCE because the block is the last thing cmd_inkreport
    does and reaching it needs a full chain; what matters is the rule, which
    is `if f.is_file()`.
    """
    import inspect
    from pdfdrill import commands
    src = inspect.getsource(commands.cmd_inkreport)
    assert "OUTPUT" in src
    assert "if f.is_file():" in src
    assert "not produced" in src


def test_no_resume_still_reaches_the_measure_step(monkeypatch, tmp_path):
    """463 — the note about not resuming must not BE the branch.

    Written as `elif ink.is_file():`, the `else` holding steps 2-4 bound to
    it, so every document with an existing ink.json printed "NO RESUME.
    Re-measuring." and then measured nothing. The message caused the failure
    it exists to report.
    """
    import ast
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[1]
           / "src" / "pdfdrill" / "commands.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.FunctionDef) and n.name == "cmd_inkreport")
    # the `if resumed:` statement, and the branch that is NOT the resume
    node = next(n for n in ast.walk(fn)
                if isinstance(n, ast.If) and isinstance(n.test, ast.Name)
                and n.test.id == "resumed")
    assert node.orelse, "there must be a non-resume path"
    # that path must contain the measure build, not hand off to another elif
    body = ast.dump(ast.Module(body=node.orelse, type_ignores=[]))
    assert "cmd_reporttex" in body, "steps 2-4 are not on the no-resume path"
    assert "im.measure" in body or "measure" in body
