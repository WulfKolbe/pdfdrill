"""
Phase C of the capability-planner plan: the read-only backward planner over the
capability graph. Ordered actions toward a goal, or a typed ClobberRefused when a
plan would rebuild the docmodel and silently destroy a still-held enrichment.

The clobber-refusal test is the WHOLE design's acceptance gate — the encoded form
of the mathpix-destroyed-latex incident found by hand.

See docs/superpowers/plans/2026-07-14-capability-planner.md (Phase C).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import capability_planner as CP


def test_model_self_chains_from_empty():
    plan = CP.plan("MODEL_BUILT", held=frozenset())
    assert plan == ["model"]                      # model bootstraps mathpix/ocr itself


def test_semantic_needs_model_when_absent():
    plan = CP.plan("SEMANTIC_BUILT", held=frozenset())
    assert plan == ["model", "semantic"]          # model prereq inserted, ordered first


def test_semantic_reuses_held_model():
    # model already held → do NOT re-run it; just the goal
    plan = CP.plan("SEMANTIC_BUILT", held=frozenset({"MODEL_BUILT"}))
    assert plan == ["semantic"]


def test_goal_already_satisfied_is_empty_plan():
    assert CP.plan("MODEL_BUILT", held=frozenset({"MODEL_BUILT"})) == []


def test_clobber_refused_when_rebuild_destroys_held_latex():
    """THE acceptance test. The user ran `latex` (LATEX_INGESTED held) but the
    model must be rebuilt (invalid/absent) to reach the semantic goal. A model
    rebuild DESTROYS LATEX_INGESTED — the planner must REFUSE, not silently
    automate the data-loss bug."""
    result = CP.plan("SEMANTIC_BUILT",
                     held=frozenset({"MODEL_BUILT", "LATEX_INGESTED"}),
                     invalid=frozenset({"MODEL_BUILT"}))     # model stale → must rebuild
    assert isinstance(result, CP.ClobberRefused)
    assert result.action == "model"
    assert result.destroyed == "LATEX_INGESTED"


def test_no_refusal_when_no_held_enrichment_is_clobbered():
    # model rebuild with nothing invested that it would destroy → a normal plan
    result = CP.plan("SEMANTIC_BUILT",
                     held=frozenset({"MODEL_BUILT"}),
                     invalid=frozenset({"MODEL_BUILT"}))
    assert result == ["model", "semantic"]


def test_clobber_check_refuses_bare_rebuild_of_held_enrichment():
    r = CP.clobber_check(["model"], held=frozenset({"LATEX_INGESTED"}))
    assert isinstance(r, CP.ClobberRefused)
    assert r.action == "model" and r.destroyed == "LATEX_INGESTED"


def test_clobber_check_allows_rebuild_when_enrichment_reestablished_after():
    # latex re-runs AFTER the model rebuild → the destroyed fact is restored → OK
    assert CP.clobber_check(["model", "injectlatex"],
                            held=frozenset({"LATEX_INGESTED"})) is None


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
