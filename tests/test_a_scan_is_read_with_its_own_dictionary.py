"""`glyphscan` — a scan's words from its pixels, with the document's own
dictionary (T-0157 / B8).

A scan with no text layer and no author's source had, on a keyless install,
only the geometry lane: a box and a type per line and NO WORDS. GLYPHDRILL3
reads the words from the pixels with no key and no GPU, at about one page per
second — which is the loop's own budget — but its compiled-in fonts read no
scan, so the document is read with a dictionary learned once from five of its
pages. Measured on one page of a board scan: 0 of 44 lines carry text without
it, 42 of 44 with it.

What these tests hold is the four things that go wrong when a tool is wired in:
a guessed path, a provenance string from the wrong repository, a reading of
five pages written over the document's own, and a command that spends money
because it did not look first.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import gd3 as GD3
from pdfdrill import commands as C
from pdfdrill import ocr_router as OR
from pdfdrill import probes as PROBES
from pdfdrill.gemma_reader import expected_outputs


def test_there_is_no_default_path(monkeypatch):
    """THE OLLAMA LESSON (6c41432d), applied before it could cost anything: a
    tool found at a guessed location makes a lane's availability — and every
    measurement that depends on it — an accident of the machine. `~/GLYPHDRILL3`
    exists on the owner's machine and is still not consulted."""
    monkeypatch.delenv("PDFDRILL_GLYPHDRILL3", raising=False)
    monkeypatch.setattr(GD3.shutil, "which", lambda name: None)
    monkeypatch.setattr(GD3.config, "get", lambda k, d=None: "")
    assert GD3.home() is None
    assert GD3.available() is False
    why = GD3.why_unavailable()
    assert "not declared" in why and "no default path" in why


def test_a_declared_tree_is_used(monkeypatch, tmp_path):
    (tmp_path / "build").mkdir()
    (tmp_path / "tools").mkdir()
    b = tmp_path / "build" / "gd3"
    b.write_text("#!/bin/sh\n", encoding="utf-8")
    b.chmod(0o755)
    (tmp_path / "tools" / "gd3-learn").write_text("#!/usr/bin/env python3\n",
                                                  encoding="utf-8")
    monkeypatch.setenv("PDFDRILL_GLYPHDRILL3", str(tmp_path))
    assert GD3.home() == tmp_path
    assert GD3.available() is True
    assert GD3.why_unavailable() == ""


def test_the_version_is_that_trees_commit_and_nobody_elses(monkeypatch, tmp_path):
    """MEASURED: a `git archive` export of GLYPHDRILL3 unpacked under
    pdfdrill's own `work/run-files` reported `ddb6c448` — PDFDRILL's HEAD,
    because git walked up out of the export and found this repository. A
    provenance string naming the wrong repository is worse than none: it would
    be written into readings and reports as the version that read the page."""
    inside = Path(__file__).resolve().parents[1] / "work" / "run-files"
    if not inside.is_dir():
        pytest.skip("no work/run-files in this checkout")
    monkeypatch.setenv("PDFDRILL_GLYPHDRILL3", str(inside))
    assert GD3.version() == "", \
        "a directory inside pdfdrill's repo must not report pdfdrill's commit"


def test_the_dictionary_and_its_teacher_live_in_the_sidecar(tmp_path):
    """A dictionary is a fact about ONE document — `gd3` refuses any other PDF
    with exit 4 — so it belongs in that document's folder, keyed by the PDF's
    sha256, beside the reading it was learned from."""
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    blob = tmp_path / "scan.pdf.drill"
    blob.mkdir()
    sha = GD3.sha256(pdf)
    assert len(sha) == 64
    for p in (GD3.trees_path(blob, pdf), GD3.rejected_path(blob, pdf),
              GD3.reading_path(blob, pdf)):
        assert blob in p.parents, f"{p} is outside the sidecar"
    assert GD3.trees_path(blob, pdf).name == f"{sha}.trees"
    # the teacher's name is the READER's, so there is one naming authority
    assert GD3.reading_path(blob, pdf) == Path(
        expected_outputs(pdf, GD3.doc_dir(blob))["lines.json"])


def test_five_pages_never_land_on_the_documents_own_reading(tmp_path):
    """A reading of five pages written over `<base>.lines.json` would be the
    worst possible cache hit: every later command would serve five pages as
    the document."""
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    own = expected_outputs(pdf)["lines.json"]
    teacher = expected_outputs(pdf, tmp_path / "scan.pdf.drill" / "gd3")["lines.json"]
    assert own != teacher
    assert Path(own).parent == tmp_path
    assert Path(teacher).name == Path(own).name      # same name, other folder


def test_any_readers_lines_json_can_teach(tmp_path):
    """`gd3-learn` takes any reader's reading of (some of) those pages. That is
    how a MathPix reading bought under the owner's budget gets used: drop it in
    beside the dictionary and run again."""
    good = tmp_path / "a.lines.json"
    good.write_text(json.dumps({"pages": [
        {"page": 1, "page_width": 1733, "lines": [{"type": "text", "text": "x"}]}]}),
        encoding="utf-8")
    assert C._is_a_reading(good) is True
    for bad_text in ("", "{}", '{"pages": []}',
                     '{"pages": [{"page": 1, "lines": []}]}',
                     '{"pages": [{"page": 1, "page_width": 10}]}'):
        bad = tmp_path / "b.lines.json"
        bad.write_text(bad_text, encoding="utf-8")
        assert C._is_a_reading(bad) is False, bad_text
    assert C._is_a_reading(tmp_path / "missing.json") is False


def test_the_tools_own_line_is_tidied_for_the_report(tmp_path):
    trees = tmp_path / "abc.trees"
    msg = (f"gd3-learn: 3 pages [1, 2, 3], 2507 labelled units of 4646 "
           f"(label rate 0.540) -> {trees.with_suffix('.part')}")
    got = GD3.tidy(msg, trees)
    assert got.startswith("3 pages")          # its own name is not repeated
    assert ".part" not in got                 # nor an internal path
    assert got.endswith("abc.trees")


def test_an_undeclared_tool_is_a_grounded_refusal(monkeypatch, tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(GD3, "available", lambda: False)
    monkeypatch.setattr(GD3, "why_unavailable", lambda: "GLYPHDRILL3 is not declared: …")
    out = C.cmd_glyphscan(pdf)
    assert "NOT run" in out and "not declared" in out


def test_a_born_digital_document_is_sent_to_its_own_glyphs(monkeypatch, tmp_path):
    """This reader CAN read a born-digital page from its pixels, and that is a
    worse reading of it than the glyphs the page already carries."""
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(GD3, "available", lambda: True)
    monkeypatch.setattr(PROBES, "ensure", lambda p, sc: None)
    sc = C.Sidecar(pdf)
    sc.set_evidence("text_layer", True)
    sc.set_evidence("pages", 3)
    sc.save()
    monkeypatch.setattr(OR, "scanned_images_for", lambda p, n: False)
    out = C.cmd_glyphscan(pdf)
    assert "NOT run" in out and "glyphlines" in out


def test_it_does_not_buy_a_reading_to_learn_from(monkeypatch, tmp_path):
    """No command buys a reading unasked. With no free reader and no teacher on
    disk it names the pages, the paid command that would read them, and the
    free way to get a host."""
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(GD3, "available", lambda: True)
    monkeypatch.setattr(GD3, "pick_pages", lambda p, n=5: [1, 7, 13])
    monkeypatch.setattr(PROBES, "ensure", lambda p, sc: None)
    sc = C.Sidecar(pdf)
    sc.set_evidence("text_layer", False)
    sc.set_evidence("pages", 20)
    sc.save()
    from pdfdrill import vision_router as VR
    monkeypatch.setattr(VR, "cost_of", lambda task: ("makora", "metered"))
    out = C.cmd_glyphscan(pdf)
    assert "1,7,13" in out
    assert "PAID" in out and "pdfdrill mathpix" in out
    assert "local host" in out


def test_boxes_without_words_are_not_written_as_the_reading(monkeypatch, tmp_path):
    """B8 gate, lib:17bb8765932c p30: gd3-learn rejected the dictionary
    (label rate 0.117), the compiled-in fonts returned 126 line boxes with no
    text, and that was written as the page's lines.json -- judged 1.000 as
    "ours" while the teacher beside it held the text. Nothing is written now,
    and the reading that was there stays."""
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(GD3, "available", lambda: True)
    monkeypatch.setattr(PROBES, "ensure", lambda p, sc: None)
    sc = C.Sidecar(pdf)
    sc.set_evidence("text_layer", False)
    sc.set_evidence("pages", 3)
    sc.save()
    empty = {"pages": [{"page": 1, "lines": [{"text": "", "type": "text"}] * 3}]}
    monkeypatch.setattr(GD3, "lines", lambda *a, **k: json.loads(json.dumps(empty)))
    target = Path(C._gr_lines_target(pdf))
    target.write_text('{"pages": [{"page": 1, "lines": [{"text": "a reading"}]}]}')
    before = target.read_text()
    out = C.cmd_glyphscan(pdf, no_dict=True)
    assert "NO LINE CARRIES TEXT" in out and "Nothing was written" in out, out
    assert target.read_text() == before
