"""
Phase D of the capability-planner plan: validity from content-hashes replaces the
mtime trigger. `_stale_or_absent` is proof-aware — a model with a valid proof is
NOT stale merely because its (unchanged) lines.json was re-touched, and IS stale
when the input content actually changed. And the sidecar's proof-invalidity feeds
the planner, so a stale model makes rebuild an explicit, clobber-checked step.

See docs/superpowers/plans/2026-07-14-capability-planner.md (Phase D).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands as C
from pdfdrill.sidecar import Sidecar


def _built_doc(tmp_path):
    pdf = tmp_path / "paper.pdf"; pdf.write_bytes(b"%PDF-1.4")
    lines = tmp_path / "paper.lines.json"; lines.write_text("{}")
    model = tmp_path / "paper.pdf.drill" / "model.docmodel.json"
    model.parent.mkdir(parents=True)
    model.write_text("{}")
    sc = Sidecar(pdf)
    sc.mark("MODEL_BUILT", produced_by="model", inputs=[lines])
    sc.save()
    return pdf, lines, model, sc


def test_valid_proof_ignores_mtime_touch(tmp_path):
    pdf, lines, model, sc = _built_doc(tmp_path)
    # re-touch the (unchanged) lines.json so its mtime is NEWER than the model —
    # the old mtime trigger would rebuild; the proof is still valid, so we don't.
    os.utime(lines, (model.stat().st_mtime + 100, model.stat().st_mtime + 100))
    assert C._stale_or_absent(Sidecar(pdf), model, lines) is False


def test_changed_input_content_is_stale(tmp_path):
    pdf, lines, model, sc = _built_doc(tmp_path)
    lines.write_text('{"changed": 1}')          # content actually differs → proof invalid
    assert C._stale_or_absent(Sidecar(pdf), model, lines) is True


def test_legacy_stale_env_restores_mtime_behavior(tmp_path, monkeypatch):
    pdf, lines, model, sc = _built_doc(tmp_path)
    os.utime(lines, (model.stat().st_mtime + 100, model.stat().st_mtime + 100))
    monkeypatch.setenv("PDFDRILL_LEGACY_STALE", "1")
    assert C._stale_or_absent(Sidecar(pdf), model, lines) is True   # mtime wins again


def test_sidecar_invalid_model_feeds_planner_clobber(tmp_path):
    """The Phase C↔D bond: a sidecar whose MODEL_BUILT proof is invalid makes the
    planner treat the model as absent, so reaching an absent goal inserts `model`
    — and with LATEX_INGESTED held, the clobber check refuses."""
    from pdfdrill import capability_planner as CP
    pdf, lines, model, sc = _built_doc(tmp_path)
    sc.add_fact("LATEX_INGESTED")
    sc.save()
    lines.write_text("CHANGED")                 # invalidate the model proof
    sc2 = Sidecar(pdf)
    held = frozenset(sc2.facts)
    invalid = frozenset(f for f in held if not sc2.capability_valid(f))
    assert "MODEL_BUILT" in invalid
    result = CP.plan("SEMANTIC_BUILT", held=held, invalid=invalid)
    assert isinstance(result, CP.ClobberRefused)
    assert result.destroyed == "LATEX_INGESTED"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
