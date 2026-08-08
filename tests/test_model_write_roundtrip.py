"""Assert on what survives a round trip, not on the object in memory.

Both bugs I introduced while fixing the audit's findings were the same class:
the in-memory state was right and the written file was wrong. 1745 tests caught
neither, because they assert on objects.

  * `refnum_anchor` held an Anchor OBJECT, which serialises as its repr
    (`Anchor(a_abfd…)`) and matches no anchor on reload.
  * `cmd_eqnums` wrote with a raw `open(..., "w")`, which truncates before
    serialising, so a failure left a zero-byte model and no previous version.

The rule these encode: a persisting command's test must write, re-read FROM
DISK, and assert the property again.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import DocObject, Document
from pdfdrill.model_io import load_model, save_model


def roundtrip(doc, tmp_path):
    """Persist and reload through the real writer/reader. The helper the audit
    asked for: every persisting command's test should go through this."""
    p = Path(tmp_path) / "model.docmodel.json"
    save_model(p, doc)
    return load_model(p), p


def _doc():
    d = Document(meta={"bibkey": "k"})
    d.add(DocObject(type="Equation", props={"latex": "x=y", "refnum": "2.5"}))
    return d


def test_a_prop_survives_the_round_trip(tmp_path):
    d = _doc()
    back, _ = roundtrip(d, tmp_path)
    eq = [o for o in back.objects.values() if o.type == "Equation"][0]
    assert eq.props["refnum"] == "2.5"


def test_a_prop_holding_a_live_object_is_REFUSED_not_silently_stringified(tmp_path):
    """The `refnum_anchor` bug: an Anchor object in props reached the file as
    `"Anchor(a_abfd…)"` — its repr — because the old writer passed
    `default=str`, so an unserialisable value was quietly turned into a string
    that matches nothing on reload. The atomic writer raises instead, which is
    the behaviour that would have caught it at the moment it was introduced."""
    class _Opaque:
        def __repr__(self): return "Anchor(a_abcd)"
    d = _doc()
    eq = [o for o in d.objects.values() if o.type == "Equation"][0]
    eq.props["anchor"] = _Opaque()
    with pytest.raises(TypeError):
        roundtrip(d, tmp_path)


def test_the_file_on_disk_is_valid_json_with_objects(tmp_path):
    _back, p = roundtrip(_doc(), tmp_path)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["objects"] and p.stat().st_size > 0


def test_no_command_writes_the_model_with_a_truncating_open():
    """20 sites bypassed the atomic writer that ships beside them. One of them
    destroyed a 239-equation model during this work."""
    src = (Path(__file__).resolve().parent.parent
           / "src" / "pdfdrill" / "commands.py").read_text(encoding="utf-8")
    assert 'open(model_path, "w"' not in src


def test_a_failed_write_leaves_the_previous_model(tmp_path):
    class _Boom:
        def to_dict(self): raise RuntimeError("nope")
    p = Path(tmp_path) / "model.docmodel.json"
    save_model(p, _doc())
    before = p.read_text()
    with pytest.raises(RuntimeError):
        save_model(p, _Boom())
    assert p.read_text() == before
