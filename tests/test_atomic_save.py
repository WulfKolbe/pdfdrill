"""
Harness finding: a huge born-digital model (C++ 49MB, Model-Checking 38MB) written
non-atomically and killed mid-write (400s timeout) left a TRUNCATED JSON, which
the next command failed to parse ("Expecting ',' delimiter" at char 686M). Model
writes must be atomic (temp + os.replace) so a killed write never leaves a partial
file, and an existing valid model survives a failed rewrite.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import model_io


def test_atomic_write_leaves_no_tmp_and_valid(tmp_path):
    p = tmp_path / "model.docmodel.json"
    model_io._atomic_write(p, '{"a": 1}')
    assert json.loads(p.read_text()) == {"a": 1}
    # no leftover temp files
    assert not list(tmp_path.glob("*.tmp*"))


def test_failed_rewrite_preserves_existing(tmp_path, monkeypatch):
    p = tmp_path / "model.docmodel.json"
    model_io._atomic_write(p, '{"good": true}')          # a valid existing file
    # a rewrite that blows up mid-serialization must NOT corrupt the good file
    import os
    real_replace = os.replace
    def boom(src, dst): raise OSError("simulated crash before rename")
    monkeypatch.setattr(model_io.os, "replace", boom)
    try:
        model_io._atomic_write(p, '{"new": 1}')
    except OSError:
        pass
    monkeypatch.setattr(model_io.os, "replace", real_replace)
    assert json.loads(p.read_text()) == {"good": True}   # original intact
    assert not list(tmp_path.glob("*.tmp*"))              # temp cleaned up


def test_save_model_is_atomic(tmp_path):
    from docmodel.core import Document
    doc = Document()
    doc.meta["bibkey"] = "x"
    mp = tmp_path / "model.docmodel.json"
    model_io.save_model(mp, doc)
    assert json.loads(mp.read_text())["meta"]["bibkey"] == "x"
    assert not list(tmp_path.glob("*.tmp*"))


if __name__ == "__main__":
    import inspect, tempfile as tf
    class MP:
        def __init__(self): self._u=[]
        def setattr(self,o,n,v): self._u.append((o,n,getattr(o,n))); setattr(o,n,v)
        def undo(self):
            for o,n,v in reversed(self._u): setattr(o,n,v)
    tests=[(k,v) for k,v in list(globals().items()) if k.startswith("test_")]
    failed=[]
    for name,t in tests:
        mp=MP(); d=Path(tf.mkdtemp())
        try:
            params=inspect.signature(t).parameters
            args=[]
            if "tmp_path" in params: args.append(d)
            if "monkeypatch" in params: args.append(mp)
            t(*args); print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
        finally: mp.undo()
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")
