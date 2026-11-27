r"""
T-0171, the pdfdrill side: `glyphscan --self-taught` (and `drill
--self-taught` on a scan) reads with gd3 and NO reader at read time.

Interface agreed with glyphdrill3-f3 (2026-11-27): `gd3-learn self PDF -o
OUT.trees`, exit 0 written, 3 refused ("refused: labels N, LOO X"), nothing
written then. What these tests hold: the model lane is never called on this
path; a teacher reading already on disk still teaches; a refusal is
remembered; the exit codes map as agreed.
"""
import json
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import gd3 as GD3
from pdfdrill import commands as C
from pdfdrill import probes as PROBES


def _tool(tmp_path, code, stderr, writes):
    tool = tmp_path / "gd3-learn"
    body = ["#!/usr/bin/env python3", "import sys",
            "a = sys.argv; out = a[a.index('-o') + 1]"]
    if writes:
        body.append("open(out, 'w').write('S self-taught\\n')")
    body += [f"sys.stderr.write({stderr!r} + '\\n')", f"sys.exit({code})"]
    tool.write_text("\n".join(body) + "\n")
    tool.chmod(tool.stat().st_mode | stat.S_IEXEC)
    return tool


@pytest.mark.parametrize("code,writes,state", [(0, True, "learned"), (3, False, "rejected"),
                                               (2, False, "failed")])
def test_the_exit_codes_map_as_agreed(monkeypatch, tmp_path, code, writes, state):
    tool = _tool(tmp_path, code, "refused: labels 51, LOO 0.66" if code == 3 else "ok", writes)
    monkeypatch.setattr(GD3, "learn_tool", lambda: tool)
    out = tmp_path / "d.trees"
    got, msg = GD3.learn_self(tmp_path / "x.pdf", out)
    assert got == state
    assert out.is_file() == (state == "learned")
    assert not out.with_suffix(".part").exists()
    if code == 3:
        assert msg == "refused: labels 51, LOO 0.66"


def _scan(tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(GD3, "available", lambda: True)
    monkeypatch.setattr(PROBES, "ensure", lambda p, sc: None)
    sc = C.Sidecar(pdf)
    sc.set_evidence("text_layer", False)
    sc.set_evidence("pages", 3)
    sc.save()
    from pdfdrill import gemma_reader as GR

    def no_reader(*a, **k):
        raise AssertionError("the model lane was called")
    monkeypatch.setattr(GR, "fetch_gemma", no_reader)
    monkeypatch.setattr(GD3, "pick_pages", lambda *a, **k: [1, 2, 3])
    reading = {"pages": [{"page": 1, "lines": [{"text": "a word", "source": "self-taught"}]}]}
    seen = {}

    def fake_lines(p, refs=None, **k):
        seen["refs"] = refs
        return json.loads(json.dumps(reading))
    monkeypatch.setattr(GD3, "lines", fake_lines)
    return pdf, sc, seen


def test_an_accepted_self_taught_dictionary_reads_the_scan(monkeypatch, tmp_path):
    pdf, sc, seen = _scan(tmp_path, monkeypatch)

    def learned(p, out):
        out.write_text("S self-taught\n")
        return "learned", "gd3-learn self: 912 labels, LOO 0.94"
    monkeypatch.setattr(GD3, "learn_self", learned)
    out = C.cmd_glyphscan(pdf, self_taught=True)
    assert "taught by the document itself" in out, out
    assert seen["refs"] is not None and seen["refs"].is_file()
    assert json.loads(Path(C._gr_lines_target(pdf)).read_text())["pages"][0]["lines"][0]["text"] == "a word"


def test_a_refusal_is_remembered_and_not_retried(monkeypatch, tmp_path):
    pdf, sc, seen = _scan(tmp_path, monkeypatch)
    calls = {"n": 0}

    def refused(p, out):
        calls["n"] += 1
        return "rejected", "refused: labels 51, LOO 0.66"
    monkeypatch.setattr(GD3, "learn_self", refused)
    out = C.cmd_glyphscan(pdf, self_taught=True)
    assert "refused by gd3-learn" in out and seen["refs"] is None, out
    assert GD3.self_refused_path(sc.blob_dir, pdf).is_file()
    out2 = C.cmd_glyphscan(pdf, self_taught=True)
    assert calls["n"] == 1 and "refused before" in out2


def test_a_teacher_on_disk_still_teaches_and_nothing_is_read(monkeypatch, tmp_path):
    pdf, sc, seen = _scan(tmp_path, monkeypatch)
    teacher = GD3.reading_path(sc.blob_dir, pdf)
    teacher.parent.mkdir(parents=True, exist_ok=True)
    teacher.write_text(json.dumps({"source": "gemma", "pages": [{"page": 1, "page_width": 2125, "lines": [{"text": "x"}]}]}))

    def learn(p, reading, out):
        out.write_text("dict\n")
        return "learned", "ok"
    monkeypatch.setattr(GD3, "learn", learn)
    monkeypatch.setattr(GD3, "learn_self", lambda *a: pytest.fail("self-taught not needed"))
    out = C.cmd_glyphscan(pdf, self_taught=True)
    assert "teacher:" in out and seen["refs"] is not None, out


def test_without_the_flag_nothing_changes(monkeypatch, tmp_path):
    pdf, sc, seen = _scan(tmp_path, monkeypatch)
    monkeypatch.setattr(GD3, "learn_self", lambda *a: pytest.fail("self-taught without the flag"))
    from pdfdrill import vision_router as VR
    monkeypatch.setattr(VR, "cost_of", lambda task: ("makora", "metered"))
    out = C.cmd_glyphscan(pdf)
    assert "NO FREE READER" in out


def test_status_does_not_advise_boxes_over_a_gd3_reading(monkeypatch, tmp_path):
    """`drill --self-taught` on US6100897A p18 read 210 lines with text and
    then ended with `Lane [free]: ... gemmaocr --geometry-only`, advice that
    would write boxes without words over that reading."""
    pdf, sc, seen = _scan(tmp_path, monkeypatch)
    sc = C.Sidecar(pdf)
    sc.set_evidence("glyphscan_lines", 210)
    sc.set_evidence("glyphscan_dictionary", True)
    sc.add_fact(C.SIZE_KNOWN)
    sc.save()
    Path(C._gr_lines_target(pdf)).write_text('{"pages": [{"page": 1, "lines": [{"text": "x"}]}]}')
    out = C.cmd_status(pdf)
    assert "read by gd3" in out and "geometry-only" not in out, out
