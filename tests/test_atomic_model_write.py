"""A failed save must not destroy the model that was already there.

`cmd_eqnums` wrote with a raw `open(model_path, "w")`, which truncates the file
before a single byte is serialised. A failure anywhere in `to_dict()` or the
dump therefore left a ZERO-BYTE model and no previous version — observed on
2605.12061v1, whose 239-equation model became 0 bytes when an exception was
raised during the run. `save_model` beside it was already atomic.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.model_io import save_model


class _Boom:
    def to_dict(self):
        raise RuntimeError("serialisation failed")


def test_a_failing_save_leaves_the_previous_model_intact(tmp_path):
    p = tmp_path / "model.docmodel.json"
    p.write_text(json.dumps({"meta": {"bibkey": "k"}, "objects": []}))
    before = p.read_text()
    with pytest.raises(RuntimeError):
        save_model(p, _Boom())
    assert p.read_text() == before, "the previous model was destroyed"


def test_eqnums_persists_through_the_atomic_writer():
    import inspect
    from pdfdrill import commands
    body = inspect.getsource(commands.cmd_eqnums)
    assert 'open(model_path, "w"' not in body
    assert "save_model" in body
