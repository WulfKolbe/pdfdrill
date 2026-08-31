"""435 — a report must state which model state it describes, and publishready
must refuse one whose model has moved."""
import hashlib
import json
from pathlib import Path

from pdfdrill import report_tex as rt


def _model(d: Path, payload="a"):
    d.mkdir(parents=True, exist_ok=True)
    p = d / rt.MODEL_NAME
    p.write_text(json.dumps({"meta": {}, "objects": [{"id": payload}]}))
    return p


def test_model_state_is_a_content_hash_not_a_timestamp(tmp_path):
    r"""mtime moves on a no-op rewrite and can move BACKWARDS on a restore
    from backup. A sha256 changes if and only if the bytes change, which is
    the question a report is answering when it says what it describes.
    """
    import os
    p = _model(tmp_path)
    a = rt.model_state(tmp_path)
    assert a["model_sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()
    os.utime(p, (10 ** 9, 10 ** 9))                 # mtime moves, bytes do not
    b = rt.model_state(tmp_path)
    assert b["model_sha256"] == a["model_sha256"]
    assert b["model_mtime"] != a["model_mtime"]
    p.write_text(p.read_text() + " ")               # bytes move
    assert rt.model_state(tmp_path)["model_sha256"] != a["model_sha256"]


def test_an_absent_model_yields_no_state_rather_than_a_false_one(tmp_path):
    """A check that cannot see its input must fail, not pass quietly."""
    assert rt.model_state(tmp_path) == {}


def test_the_stamp_records_it(tmp_path):
    _model(tmp_path)
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"%PDF-1.4 x")
    st = rt.write_build_stamp(pdf, legend=True, ink_adopted=False,
                              prefer_refined=False, filters={})
    assert st["model_sha256"] == rt.model_state(tmp_path)["model_sha256"]
    assert st["model_bytes"] > 0


def test_a_rebuild_always_moves_the_hash_and_that_is_correct():
    r"""Object ids are `uuid4().hex[:12]` (docmodel/core.py), so no two builds
    of the same input agree — 430 measured 1 id in common out of 2,196. A
    report built against the previous model describes objects that no longer
    exist, and the hash moving is what says so.
    """
    import inspect
    from docmodel import core
    assert "uuid4" in inspect.getsource(core._new_id)
