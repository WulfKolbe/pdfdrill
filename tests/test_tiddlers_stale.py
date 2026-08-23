"""Tiddlers are a PROJECTION of the model, so they go stale the moment the model
moves under them — `model` rebuilding from a richer lines.json, `injectlatex`
attaching a competing provenance, `clean` materialising.

Every consumer (`reporttex`, `crossref`, `cdncrops`, `standalone`) tested only
`is_file()`. On 20c-cation that meant `reporttex --compile` read a tiddlers.json
from 3 August against a model rebuilt on 23 August and printed "0 display
equations" for a document whose model held 4 — confident, plausible, and wrong,
with no warning. Presence is not adequacy.
"""
import sys, os, time, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.sidecar import Sidecar
from pdfdrill.commands import (_tiddlers_path, _tiddlers_stale, _model_path,
                               _lines_json_path, MODEL_BUILT)


def _setup(tmp, tid_older: bool, with_tiddlers: bool = True):
    """A built model plus a tiddler array on either side of it in time."""
    pdf = Path(tmp) / "20c-cation.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    sc = Sidecar(pdf)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    model_path = _model_path(sc)
    lines_path = _lines_json_path(pdf)
    lines_path.write_text('{"pages":[]}')
    model_path.write_text("{}")
    tid = pdf.parent / f"{pdf.stem}.tiddlers.json"
    if with_tiddlers:
        tid.write_text("[]")
    now = time.time()
    # model NEWER than lines.json, so model-staleness is False and the ONLY
    # question left is the tiddlers-vs-model one this guard exists to answer
    os.utime(lines_path, (now - 100, now - 100))
    os.utime(model_path, (now - 50, now - 50))
    if with_tiddlers:
        os.utime(tid, (now - 90, now - 90) if tid_older else (now - 10, now - 10))
    sc.add_fact(MODEL_BUILT)
    sc.set_evidence("model_caps", {"geometry": True, "math": True, "source": "mathpix"})
    sc.set_evidence("model_source", "mathpix")
    sc.save()
    return sc, pdf, tid


def test_tiddlers_older_than_model_are_stale():
    """The 20c-cation state: a real tiddler array, three weeks behind the model."""
    with tempfile.TemporaryDirectory() as tmp:
        sc, pdf, tid = _setup(tmp, tid_older=True)
        assert tid.is_file()                     # present — the only old test
        assert _tiddlers_stale(pdf, sc, tid) is True


def test_tiddlers_newer_than_model_are_fresh():
    """The converse, so the guard cannot pass by always returning True: an
    up-to-date array must NOT be rebuilt (rebuilding re-runs the projector and,
    for `reporttex`, re-downloads crops)."""
    with tempfile.TemporaryDirectory() as tmp:
        sc, pdf, tid = _setup(tmp, tid_older=False)
        assert _tiddlers_stale(pdf, sc, tid) is False


def test_absent_tiddlers_are_stale():
    with tempfile.TemporaryDirectory() as tmp:
        sc, pdf, tid = _setup(tmp, tid_older=False, with_tiddlers=False)
        assert _tiddlers_path(pdf, sc) is None
        assert _tiddlers_stale(pdf, sc, None) is True


def test_stale_model_makes_fresh_tiddlers_stale():
    """Order matters: a tiddler array NEWER than the model is still wrong when
    the MODEL itself must rebuild (a newer lines.json). Testing only
    tiddlers-vs-model would call this pair fresh."""
    with tempfile.TemporaryDirectory() as tmp:
        sc, pdf, tid = _setup(tmp, tid_older=False)
        lines = _lines_json_path(pdf)
        now = time.time()
        os.utime(lines, (now, now))          # lines.json now NEWER than the model
        assert _tiddlers_stale(pdf, sc, tid) is True


def test_resolve_returns_path_and_note_without_rebuild():
    """`rebuild=False` reports staleness instead of silently regenerating."""
    from pdfdrill.commands import _resolve_tiddlers
    with tempfile.TemporaryDirectory() as tmp:
        sc, pdf, tid = _setup(tmp, tid_older=True)
        got, sc2, note = _resolve_tiddlers(pdf, sc, rebuild=False)
        assert got == tid and note != ""


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_tiddlers_without_any_model_are_not_stale():
    """A tiddler array with NO model beside it is not "behind" anything. The
    first version of this guard called it stale, tried to build a model from a
    stub PDF with no lines.json, and reached tesseract OCR — test_standalone
    caught it. `standalone`/`crossref` accept an externally-supplied array."""
    with tempfile.TemporaryDirectory() as tmp:
        sc, pdf, tid = _setup(tmp, tid_older=True)
        _model_path(sc).unlink()
        assert _tiddlers_stale(pdf, sc, tid) is False
