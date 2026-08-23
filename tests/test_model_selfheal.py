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
from pdfdrill.commands import (_stale_or_absent, _model_path, _lines_json_path,
                               _source_model_trap, MODEL_BUILT)


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


# --- the gap the first two tests could not see -------------------------------
# Both cases above SET model_caps. A source model built by `add` never writes it,
# so `caps.get("geometry")` was None, `None is False` was False, and the trap
# stayed open — on 2604.11744 for seventeen days, with a MathPix lines.json and
# its 28 regions, confidences and CDN crops sitting unread beside the model.
# A test that only ever supplies the evidence cannot catch a missing-evidence bug.

def _setup_no_caps(tmp, lines_body, model_source="latex"):
    """A LaTeX-source model with NO model_caps evidence — what `add` leaves."""
    pdf = Path(tmp) / "2604.11744.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    sc = Sidecar(pdf)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)
    model_path = _model_path(sc)
    lines_path = _lines_json_path(pdf)
    lines_path.write_text(lines_body)
    model_path.write_text("{}")
    t = time.time()                       # model NEWER: mtime staleness is False
    os.utime(lines_path, (t - 10, t - 10))
    os.utime(model_path, (t, t))
    sc.add_fact(MODEL_BUILT)
    sc.set_evidence("model_source", model_source)   # and deliberately NO model_caps
    sc.save()
    return sc, model_path, lines_path


#: a lines.json carrying the fields only MathPix writes
_MATHPIX = ('{"pages":[{"lines":[{"type":"math","confidence":1,"font_size":36,'
            '"region":{"top_left_x":725,"top_left_y":1541,"width":674,"height":114}}]}]}')
#: the same shape from the keyless pdfminer route — geometry, but no confidence
_PDFMINER = '{"pages":[{"lines":[{"type":"text","text":"x"}]}]}'


def test_latex_model_with_mathpix_lines_is_stale_without_caps():
    """The real 2604.11744 state: model_source='latex', a MathPix lines.json,
    and no model_caps at all. Must rebuild."""
    with tempfile.TemporaryDirectory() as tmp:
        sc, mp, lp = _setup_no_caps(tmp, _MATHPIX)
        assert sc.get_evidence("model_caps") is None      # the gap, made explicit
        assert _source_model_trap(sc, lp) is True
        assert _stale_or_absent(sc, mp, lp) is True


def test_latex_model_with_pdfminer_lines_is_not_stale():
    """The converse, so the fix cannot pass by returning True. A LaTeX model over
    a keyless pdfminer lines.json is the MERGED route (113 of the library) — it
    holds gold math the lines.json cannot supply and must NOT be discarded."""
    with tempfile.TemporaryDirectory() as tmp:
        sc, mp, lp = _setup_no_caps(tmp, _PDFMINER)
        assert _source_model_trap(sc, lp) is False
        assert _stale_or_absent(sc, mp, lp) is False


def test_mathpix_model_with_mathpix_lines_is_not_stale():
    """A model already built FROM the MathPix lines.json is not re-built."""
    with tempfile.TemporaryDirectory() as tmp:
        sc, mp, lp = _setup_no_caps(tmp, _MATHPIX, model_source="mathpix")
        assert _source_model_trap(sc, lp) is False


def test_trap_is_false_without_a_lines_json():
    """No lines.json ⇒ nothing better to upgrade to; keep the source model."""
    with tempfile.TemporaryDirectory() as tmp:
        sc, mp, lp = _setup_no_caps(tmp, _MATHPIX)
        lp.unlink()
        assert _source_model_trap(sc, lp) is False


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
