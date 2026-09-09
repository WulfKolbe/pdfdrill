"""656 — `cmd_conserve(..., gate=True)` is the CLI's half of the ratchet:
`docops.conserve.gate`/`format_gate_report` are the pure logic (tested in
`tests/test_conserve_gate.py`); this file is the thin wrapper's contract —
prints the report and raises `SystemExit(1)` on a FAIL, returns the report
text on a PASS, the same convention `skill_cmd.run`'s `--check` uses.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from docmodel.core import Document, DocObject, Realization
import docops.conserve as conserve_mod
from pdfdrill import commands as C


def _one_unreachable_citation_doc() -> Document:
    doc = Document()
    doc.meta["bibkey"] = "CONSDOC"
    mp = doc.ensure_stream("mathpix_lines")
    head = mp.append(text="1 Intro", _page=1, _line_index=0,
                     type="section_header")
    body = mp.append(text="Hello [X1].", _page=1, _line_index=1, type="text")
    sec = DocObject(type="Section", props={
        "caption": "Intro", "level": 1, "flow_index": 0, "page": 1})
    sec.add_realization(Realization(stream="mathpix_lines", start=head,
                                    end=head, role="surface"))
    doc.add(sec)
    par = DocObject(type="Paragraph", props={
        "text": "Hello [X1].", "page": 1, "flow_index": 1})
    par.add_realization(Realization(stream="mathpix_lines", start=body,
                                    end=body, role="surface"))
    doc.add_child(sec, par)
    cit = DocObject(type="Citation", props={"citekey": "X1", "flow_index": 2})
    cit.add_realization(Realization(stream="mathpix_lines", start=body,
                                    end=body, role="surface",
                                    props={"offset": 6, "length": 2}))
    doc.add(cit)
    return doc


def _wire(tmp_path, monkeypatch, doc):
    pdf = tmp_path / "CONSDOC.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    model_path = tmp_path / "model.docmodel.json"
    model_path.write_text(json.dumps(doc.to_dict()), encoding="utf-8")
    monkeypatch.setattr(C, "_model_path", lambda sc: model_path)
    monkeypatch.setattr(C, "_stale_or_absent", lambda *a, **k: False)
    return pdf


def test_gate_passes_and_returns_text(tmp_path, monkeypatch):
    doc = _one_unreachable_citation_doc()
    pdf = _wire(tmp_path, monkeypatch, doc)
    monkeypatch.setattr(conserve_mod, "load_baseline",
                        lambda: {"CONSDOC": {"Citation": 1}})
    out = C.cmd_conserve(pdf, gate=True)
    assert "PASS" in out
    assert "at baseline: Citation=1" in out


def test_gate_fails_and_raises_systemexit(tmp_path, monkeypatch, capsys):
    doc = _one_unreachable_citation_doc()
    pdf = _wire(tmp_path, monkeypatch, doc)
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})
    with pytest.raises(SystemExit) as ei:
        C.cmd_conserve(pdf, gate=True)
    assert ei.value.code == 1
    printed = capsys.readouterr().out
    assert "FAIL" in printed
    assert "NEW unreachable type: Citation" in printed


def test_gate_json_mode_still_raises_on_fail(tmp_path, monkeypatch, capsys):
    doc = _one_unreachable_citation_doc()
    pdf = _wire(tmp_path, monkeypatch, doc)
    monkeypatch.setattr(conserve_mod, "load_baseline", lambda: {})
    with pytest.raises(SystemExit):
        C.cmd_conserve(pdf, gate=True, json_out=True)
    printed = capsys.readouterr().out
    parsed = json.loads(printed)
    assert parsed["passed"] is False
    assert parsed["new_types"] == {"Citation": 1}


# --------------------------------------------------------- (review finding 9)
# `_do_conserve` (cli.py) does its own flag stripping BEFORE cmd_conserve
# ever sees the args -- `--limit N` consumed by `_opt`, `--gate` detected
# then stripped, `--json` stripped, whatever remains is the file. The review
# verified this manually end to end; this is the cheap automated version:
# stub `cmd_conserve` itself and assert exactly what `_do_conserve` passed
# it, for every flag combination, without touching a real Sidecar/model.

def test_do_conserve_parses_gate_json_and_limit_flags(monkeypatch, tmp_path):
    from pdfdrill import cli, commands

    calls = []

    def fake_cmd_conserve(pdf, json_out=False, limit=10, gate=False):
        calls.append({"pdf": pdf, "json_out": json_out, "limit": limit,
                      "gate": gate})
        return "ok"

    monkeypatch.setattr(commands, "cmd_conserve", fake_cmd_conserve)
    fake_pdf = tmp_path / "x.pdf"
    monkeypatch.setattr(cli, "_drilled", lambda args: fake_pdf)

    cli._do_conserve(["x.pdf"])
    cli._do_conserve(["x.pdf", "--gate"])
    cli._do_conserve(["x.pdf", "--json"])
    cli._do_conserve(["x.pdf", "--limit", "3"])
    cli._do_conserve(["x.pdf", "--gate", "--json", "--limit", "7"])

    assert [c["gate"] for c in calls] == [False, True, False, False, True]
    assert [c["json_out"] for c in calls] == [False, False, True, False, True]
    assert [c["limit"] for c in calls] == [10, 10, 10, 3, 7]
    assert all(c["pdf"] == fake_pdf for c in calls)


def test_do_conserve_requires_a_file_argument():
    from pdfdrill import cli
    with pytest.raises(ValueError):
        cli._do_conserve(["--gate"])          # a flag alone is not a file
