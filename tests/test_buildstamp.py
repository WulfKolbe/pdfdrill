"""575 — the build stamp and the cross-generation guard."""
import json

import pytest

from pdfdrill import buildstamp as B


def test_stamp_has_the_four_fields():
    s = B.stamp(refresh=True)
    assert set(s) == {"sha", "dirty", "version", "at"}
    assert s["sha"] is None or len(s["sha"]) == 40
    assert s["dirty"] in (True, False, None)


def test_git_returns_none_on_failure_never_a_wrong_sha():
    # 574's lesson: an unchecked return code is how a wrong number gets born.
    assert B._git("rev-parse", "definitely-not-a-ref") is None


def test_one_generation_reports_a_single_number():
    s = {"sha": "a" * 40, "dirty": False, "version": "0.1.0", "at": "x"}
    sp = B.spread([("a", s), ("b", s), ("c", s)])
    assert sp["one"] and sp["n"] == 1
    assert len(B.guard_lines(sp)) == 1
    assert "3 documents" in B.guard_lines(sp)[0]


def test_two_shas_report_the_spread_not_a_number():
    a = {"sha": "a" * 40, "dirty": False, "version": "0.1.0", "at": "x"}
    b = {"sha": "b" * 40, "dirty": False, "version": "0.1.0", "at": "x"}
    sp = B.spread([("one", a), ("two", b)])
    assert sp["n"] == 2 and not sp["one"]
    text = "\n".join(B.guard_lines(sp, "The section total"))
    assert "SPANS 2 BUILD GENERATIONS" in text
    assert "aaaaaaa" in text and "bbbbbbb" in text
    with pytest.raises(ValueError):
        B.require_one(sp)


def test_unstamped_is_its_own_generation_not_folded_into_the_majority():
    a = {"sha": "a" * 40, "dirty": False, "version": "0.1.0", "at": "x"}
    sp = B.spread([("one", a), ("two", a), ("old", None)])
    assert sp["n"] == 2
    assert sp["unstamped"] == ["old"]
    assert not sp["one"]


def test_dirty_is_a_generation_of_its_own():
    clean = {"sha": "a" * 40, "dirty": False, "version": "0.1.0", "at": "x"}
    dirty = {"sha": "a" * 40, "dirty": True, "version": "0.1.0", "at": "x"}
    sp = B.spread([("clean", clean), ("dirty", dirty)])
    assert sp["n"] == 2, "same commit, different code — not one generation"
    assert sp["dirty"] == ["dirty"]


def test_read_stamp_from_a_model_file(tmp_path):
    m = tmp_path / "model.docmodel.json"
    st = {"sha": "c" * 40, "dirty": False, "version": "0.1.0", "at": "x"}
    m.write_text(json.dumps({"meta": {"build": st}, "objects": {}}))
    assert B.read_stamp(m) == st
    assert B.read_stamp(m, "written") is None
    assert B.read_stamp(tmp_path / "absent.json") is None


def test_save_model_stamps_the_writer_without_mutating_the_document(tmp_path):
    from docmodel.core import Document
    from pdfdrill import model_io
    doc = Document()
    doc.meta["bibkey"] = "x"
    p = tmp_path / "model.docmodel.json"
    model_io.save_model(p, doc)
    assert "written" not in doc.meta, "saving must not mutate the caller's doc"
    on_disk = json.loads(p.read_text())["meta"]
    assert set(on_disk["written"]) == {"sha", "dirty", "version", "at"}


def test_save_model_leaves_an_existing_build_stamp_alone(tmp_path):
    from docmodel.core import Document
    from pdfdrill import model_io
    doc = Document()
    doc.meta["build"] = {"sha": "d" * 40, "dirty": False, "version": "0.0.1",
                         "at": "then"}
    p = tmp_path / "model.docmodel.json"
    model_io.save_model(p, doc)
    assert json.loads(p.read_text())["meta"]["build"]["sha"] == "d" * 40
