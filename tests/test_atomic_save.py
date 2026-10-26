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


def test_save_model_writes_a_document_whose_path_is_not_utf8(tmp_path):
    r"""A FILENAME IS BYTES. 18 of this library's PDFs have a path that is not
    valid UTF-8; it reaches the model through `meta.source_path`, the bibkey,
    stream names and props as a lone surrogate, and `save_model` dumped with
    `ensure_ascii=False`, which passes that surrogate through RAW. The strict
    UTF-8 encode in `_atomic_write` then raised `UnicodeEncodeError: 'utf-8'
    codec can't encode character '\udce4'` and the model was not written at
    all — the document became unbuildable by every route.

    `pdfdrill.jsonio` has existed for this since 18 such folders each failed
    their whole rebuild, and `docmodel.main` has used it all along;
    `save_model` was the writer that did not.
    """
    import os
    from docmodel.core import Document
    raw = b"/home/wkolbe/pdfdrill-library/Alg\xe8bre 1 [Lecture notes]/x.lines.json"
    doc = Document()
    doc.meta["bibkey"] = "x"
    doc.meta["source_path"] = os.fsdecode(raw)
    mp = tmp_path / "model.docmodel.json"
    model_io.save_model(mp, doc)

    mp.read_bytes().decode("utf-8")                      # the file is valid UTF-8
    got = json.loads(mp.read_text(encoding="utf-8"))["meta"]["source_path"]
    assert os.fsencode(got) == raw                       # and the bytes survive
    assert not list(tmp_path.glob("*.tmp*"))
    # the sidecar must be written too, not silently dropped by save_model's
    # except branch — a missing `.docpack.json` costs every read-only command
    # the fast DocGraph path, forever, with nothing said
    assert model_io.packed_path(mp).exists()


def test_the_utf8_fallback_did_not_cost_the_refusal_of_an_opaque_prop(tmp_path):
    r"""Both properties at once, because the first fix traded one for the other.

    Routing `save_model` through `jsonio.dumps` fixed the Latin-1 path and
    silently re-introduced the `refnum_anchor` defect: `jsonio` does
    `kw.setdefault("default", str)`, so a prop holding a live object was
    written as its repr again. `default=None` keeps the refusal. This test
    holds the two together so neither can be restored by removing the other.
    """
    import os
    from docmodel.core import Document

    class _Opaque:
        def __repr__(self): return "Anchor(a_abcd)"

    doc = Document()
    doc.meta["bibkey"] = "x"
    doc.meta["source_path"] = os.fsdecode(b"/lib/Alg\xe8bre 1/x.lines.json")
    doc.meta["anchor"] = _Opaque()
    try:
        model_io.save_model(tmp_path / "model.docmodel.json", doc)
    except TypeError:
        pass                      # the refusal, with an undecodable path present
    else:
        raise AssertionError("an unserialisable prop was written, not refused")


def test_an_ordinary_model_is_not_re_encoded(tmp_path):
    """The fallback must touch nothing else. Every model on disk carries raw
    Unicode mathematics, and a writer that escaped it would rewrite the whole
    corpus to repair 18 filenames."""
    from docmodel.core import Document
    doc = Document()
    doc.meta["bibkey"] = "x"
    doc.meta["title"] = "Algèbre 1 — α β 中文"
    mp = tmp_path / "model.docmodel.json"
    model_io.save_model(mp, doc)
    assert "Algèbre 1 — α β 中文" in mp.read_text(encoding="utf-8")


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
