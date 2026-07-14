"""
Phase B of the capability-planner plan: proof objects. A capability records the
content-hashes of the inputs it was built from; validity = every input hash still
matches the file on disk (the Nix/Bazel move, replacing the mtime `stale` trigger
that caused the silent-clobber bug).

See docs/superpowers/plans/2026-07-14-capability-planner.md (Phase B).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import proofs as P


def test_make_proof_then_verify_true(tmp_path):
    a = tmp_path / "lines.json"; a.write_text('{"x":1}')
    b = tmp_path / "config.json"; b.write_text("cfg")
    pr = P.make_proof("model", [a, b], params={"bibkey": "K"})
    assert pr["produced_by"] == "model"
    assert set(pr["inputs"]) == {str(a), str(b)}
    assert pr["params_hash"].startswith(("sha256:", "blake3:"))
    assert P.verify(pr) is True


def test_verify_false_after_input_mutates(tmp_path):
    a = tmp_path / "lines.json"; a.write_text("orig")
    pr = P.make_proof("model", [a])
    a.write_text("CHANGED")                     # an input changed on disk
    assert P.verify(pr) is False


def test_verify_false_when_input_missing(tmp_path):
    a = tmp_path / "lines.json"; a.write_text("x")
    pr = P.make_proof("model", [a])
    a.unlink()
    assert P.verify(pr) is False


def test_params_hash_is_deterministic_and_order_independent(tmp_path):
    a = tmp_path / "f"; a.write_text("x")
    p1 = P.make_proof("m", [a], params={"b": 2, "a": 1})
    p2 = P.make_proof("m", [a], params={"a": 1, "b": 2})
    assert p1["params_hash"] == p2["params_hash"]


def test_sidecar_mark_writes_fact_and_proof(tmp_path):
    from pdfdrill.sidecar import Sidecar
    pdf = tmp_path / "2502.20855v2.pdf"; pdf.write_bytes(b"%PDF-1.4")
    lines = tmp_path / "2502.20855v2.lines.json"; lines.write_text("{}")
    sc = Sidecar(pdf)
    sc.mark("MODEL_BUILT", produced_by="model", inputs=[lines], params={"bibkey": "K"})
    assert sc.has("MODEL_BUILT")                        # fact set as before
    caps = sc.capabilities
    assert "MODEL_BUILT" in caps
    assert caps["MODEL_BUILT"]["produced_by"] == "model"
    assert P.verify(caps["MODEL_BUILT"]) is True        # proof valid on fresh inputs
    sc.save()
    assert Sidecar(pdf).capabilities["MODEL_BUILT"]["produced_by"] == "model"  # persists


def test_proof_coverage_census_key_producers_migrated():
    """Census (visible, not hidden): the highest-value producers emit proofs.
    `model` and `latex` are migrated in Phase B; the set grows as more follow."""
    from pdfdrill import capgraph as CG
    emitting = CG.proof_emitting()
    assert {"model", "latex"} <= emitting, (
        f"key producers not proof-backed; proof-emitting = {sorted(emitting)}")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
