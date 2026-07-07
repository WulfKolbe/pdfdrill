"""
pdfdrill context — structural projection of the docmodel into an LLM context.
A query selects typed docmodel objects; they render to Markdown blocks WITH
metadata + object ids, capped to a token budget. Selection = filters ∩ a
PLUGGABLE per-aspect ranker (default structural/IDF; embedding rankers register
without touching the core). Pure/offline over a fake doc.
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import projection as X


def _o(id, t, **props):
    return types.SimpleNamespace(id=id, type=t, props=props)


def _nodes():
    return [
        _o("P1", "Paragraph", text="We define the alignment kernel over datasets.",
           page=2, section_number="1", flow_index=1),
        _o("P2", "Paragraph", text="Unrelated prose about the weather today.",
           page=3, section_number="2", flow_index=2),
        _o("F1", "Formula", latex=r"\{\gamma^m,\gamma^n\}=2\delta^{mn}",
           page=7, section_number="3.2", refnum="(12)", flow_index=3),
        _o("T1", "Theorem", text="Every convergent representation is Platonic.",
           page=8, section_number="4", refnum="Thm 1", flow_index=4),
        _o("C1", "Concept", name="alignment kernel", subtype="term",
           page=2, flow_index=5),
    ]


def test_filter_by_type():
    md = X.project_context(_nodes(), types=["formula", "theorem"])
    assert "F1" in md and "T1" in md
    assert "P1" not in md and "P2" not in md      # prose filtered out


def test_section_filter():
    md = X.project_context(_nodes(), section="3.2")
    assert "F1" in md and "P1" not in md and "T1" not in md


def test_freetext_ranks_relevant_first_and_cites_id():
    units = X.select_units(_nodes(), query="alignment kernel datasets", k=2)
    assert units[0]["id"] == "P1"                  # the relevant paragraph ranks first
    md = X.project_context(_nodes(), query="alignment kernel datasets", k=2)
    assert "id=P1" in md                           # cited by object id, not filename


def test_markdown_block_has_metadata_header():
    md = X.project_context(_nodes(), types=["formula"])
    assert "<!-- id=F1 type=Formula page=7 section=3.2 refnum=(12)" in md
    assert r"\gamma" in md                         # the formula LaTeX is the body
    assert "token" in md.lower()                   # trailer reports token estimate


def test_max_tokens_truncates_and_reports():
    full = X.project_context(_nodes())             # all units
    tiny = X.project_context(_nodes(), max_tokens=12)
    assert len(tiny) < len(full)
    assert "dropped" in tiny.lower() or "of" in tiny.lower()


def test_concept_filter_pulls_the_concept():
    md = X.project_context(_nodes(), concept="alignment kernel")
    assert "C1" in md                              # the named concept surfaces


def test_ranker_registry_seam():
    # a registered aspect ranker is used; absent → default structural
    calls = []
    def fake_math(query, units):
        calls.append(query)
        return sorted(units, key=lambda u: u["id"], reverse=True)
    X.register_ranker("mathtest", fake_math)
    try:
        X.select_units(_nodes(), query="x", aspect="mathtest")
        assert calls == ["x"]                      # the registered ranker ran
    finally:
        X.RANKERS.pop("mathtest", None)
    # an unknown aspect degrades to structural, never raises
    out = X.select_units(_nodes(), query="alignment", aspect="does-not-exist")
    assert out and "P1" in [u["id"] for u in out]   # ranked, no crash


if __name__ == "__main__":
    tests = [(k, v) for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for name, t in tests:
        try: t(); print(f"PASS {name}")
        except AssertionError as e: failed.append(name); print(f"FAIL {name}: {e}")
        except Exception as e: failed.append(name); print(f"ERROR {name}: {e!r}")
    if failed: print(f"\n{len(failed)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} passed.")
