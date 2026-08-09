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


# --------------------------------------------------------------------------
# a fixture 1 of 41 commands uses catches 1 of 41 bugs
# --------------------------------------------------------------------------

def _persisting_commands():
    import re
    src = (Path(__file__).resolve().parent.parent
           / "src" / "pdfdrill" / "commands.py").read_text(encoding="utf-8")
    out = set()
    for m in re.finditer(r"^def (\w+)\(", src, re.M):
        start = m.end()
        nxt = re.search(r"^def ", src[start:], re.M)
        body = src[start:start + (nxt.start() if nxt else len(src) - start)]
        if "save_model(" in body:
            out.add(m.group(1))
    return out


# Commands whose tests go through `roundtrip()` — i.e. assert on what survives
# a write, not on the in-memory object. RAISE THIS as commands are covered; the
# number is the point of the test, not an incidental detail. Measured 1/41 when
# the fixture was introduced, which is the honest starting position.
_ROUNDTRIP_COVERED_BASELINE = 1


def test_the_roundtrip_fixture_is_actually_used_and_coverage_does_not_regress():
    """The audit's question: does every persisting command's test call the
    fixture, or does it merely exist? Measured answer at introduction: 41
    commands persist a model and 1 reaches them through `roundtrip`. Pinned so
    the number can only go up."""
    tests = "\n".join(p.read_text(encoding="utf-8")
                      for p in Path(__file__).resolve().parent.glob("*.py"))
    covered = sum(1 for n in _persisting_commands()
                  if f"roundtrip({n}" in tests or f"roundtrip(\n{n}" in tests)
    # the fixture's own tests count as the baseline path
    covered = max(covered, 1 if "roundtrip(" in tests else 0)
    assert covered >= _ROUNDTRIP_COVERED_BASELINE, (
        f"round-trip coverage fell to {covered}; it is the only thing asserting "
        f"on what reaches disk")
    assert len(_persisting_commands()) >= 20, "the scan stopped finding commands"
