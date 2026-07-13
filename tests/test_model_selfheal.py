"""
The source→mathpix ordering trap: on arXiv, `add` builds a geometry-less
LaTeX-SOURCE model when no lines.json exists yet; then `mathpix` writes a
lines.json WITH page geometry. The model must upgrade to it — else `inspect` /
`locate` stay box-less on the source model even though a geometry-bearing
lines.json is right there. `_stale_or_absent` (the gate every projector uses to
auto-rebuild) must return True in exactly that state.
"""
import sys, tempfile, os, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.sidecar import Sidecar
from pdfdrill.commands import _stale_or_absent, _model_path, _lines_json_path, MODEL_BUILT


def _setup(tmp, geometry):
    pdf = Path(tmp) / "2502.20855v2.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    sc = Sidecar(pdf)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    model_path = _model_path(sc)
    lines_path = _lines_json_path(pdf)
    lines_path.write_text("{}")                 # a lines.json is present
    model_path.write_text("{}")
    # make the model NEWER than the lines.json (so mtime-staleness alone is False)
    t = time.time()
    os.utime(lines_path, (t - 10, t - 10))
    os.utime(model_path, (t, t))
    sc.add_fact(MODEL_BUILT)
    sc.set_evidence("model_caps", {"geometry": geometry, "math": True, "source": ""})
    sc.save()
    return sc, pdf, model_path, lines_path


def test_geometryless_model_with_lines_json_is_stale():
    """A model reporting no geometry + a lines.json present ⇒ rebuild (self-heal),
    even though the model file is NEWER than the lines.json."""
    with tempfile.TemporaryDirectory() as tmp:
        sc, pdf, mp, lp = _setup(tmp, geometry=False)
        assert _stale_or_absent(sc, mp, lp) is True


def test_geometry_model_not_stale():
    """A model that already HAS geometry is not rebuilt (lines.json not newer)."""
    with tempfile.TemporaryDirectory() as tmp:
        sc, pdf, mp, lp = _setup(tmp, geometry=True)
        assert _stale_or_absent(sc, mp, lp) is False


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
