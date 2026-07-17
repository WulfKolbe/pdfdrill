"""
Phase A of the capability-planner plan: the capability GRAPH — per command, the
facts it PRODUCES (derived from its `add_fact` calls) and the facts it DESTROYS
(the model-rebuild clobber the proposal names as non-negotiable). Kept code-synced
by AST-deriving `produces` so the manifest can never drift from the handlers.

See docs/superpowers/plans/2026-07-14-capability-planner.md (Phase A).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import capgraph as CG


def test_produces_is_ast_derived_from_add_fact():
    p = CG.produces()
    assert p["model"] == ["MODEL_BUILT", "NEEDS_VISION_OCR"] or "MODEL_BUILT" in p["model"]
    assert p["injectlatex"] == ["LATEX_INGESTED"]
    assert p["geometry"] == ["GEOMETRY_FUSED"]
    assert p["semantic"] == ["SEMANTIC_BUILT"]
    assert p["size"] == ["SIZE_KNOWN"]
    # a read-only command sets no fact
    assert "status" not in p or p.get("status", []) == []


def test_model_rebuild_destroys_latex_ingested():
    """The core clobber: rebuilding the docmodel silently invalidates the A-mode
    enrichments (latex/geometry/eqnums/nlp/bibliography…) though it never calls
    remove_fact on them. The planner MUST know this."""
    d = CG.destroys("model")
    assert "LATEX_INGESTED" in d
    assert "GEOMETRY_FUSED" in d
    assert "EQNUMS_FUSED" in d
    assert "NLP_ENHANCED" in d
    assert "BIBLIOGRAPHY_BUILT" in d
    # a model rebuild does NOT destroy its own INPUT (lines.json / size)
    assert "SIZE_KNOWN" not in d
    assert "OCR_BUILT" not in d


def test_remove_fact_destroys_are_included():
    # latex/visionocr explicitly remove_fact(NEEDS_VISION_OCR) — an upgrade
    assert "NEEDS_VISION_OCR" in CG.destroys("injectlatex")
    assert "NEEDS_VISION_OCR" in CG.destroys("visionocr")
    # a read-only command destroys nothing
    assert CG.destroys("status") == []


def test_no_phantom_clobber_every_destroyed_fact_is_produced():
    """A clobber must destroy something real: every fact any command DESTROYS
    must be PRODUCED by some command — otherwise the planner reasons about a
    fact that can never be established (a manifest typo)."""
    produced = {f for facts in CG.produces().values() for f in facts}
    for cmd in CG.MODEL_BUILDERS + ("injectlatex", "visionocr"):
        for f in CG.destroys(cmd):
            assert f in produced, f"{cmd} destroys {f} which no command produces"


def test_every_fact_is_wellformed_and_in_universe():
    universe = CG.all_facts()
    for cmd, facts in CG.produces().items():
        for f in facts:
            assert f.isupper() and f in universe, f"{cmd}: bad fact {f!r}"


def test_graph_merges_requires_from_manifest():
    g = CG.capability_graph()
    assert "produces" in g["model"] and "destroys" in g["model"]
    # `requires` carried through from the manifest (command-name prereqs)
    assert "requires" in g["tiddlers"]


def test_requires_closure_every_prereq_command_produces_facts():
    """Phase A closure: every manifest `requires:` names a real fact-producing
    command, so a capability prereq always resolves to producible facts."""
    prod = CG.produces()
    g = CG.capability_graph()
    for cmd, spec in g.items():
        for prereq in spec["requires"]:
            assert prereq in prod, (
                f"{cmd} requires '{prereq}' but that command produces no fact")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
