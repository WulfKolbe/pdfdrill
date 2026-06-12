"""
Stratum discipline + the fixpoint driver (src/semantic/fixpoint.py):
- modules/passes declare a stratum; running them out of order WARNS (monotonic
  reads-below/writes-above is the stratified-Datalog contract);
- the driver re-runs strata >=4 until quiescence; termination comes from
  content-hash identity (re-emitting a kitem is a no-op).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic.graph import SemanticGraph
from semantic.identity import IdentityResolver
from semantic import fixpoint, kitems


def test_fixpoint_terminates_and_is_idempotent():
    g = SemanticGraph(); r = IdentityResolver(g)
    calls = {"n": 0}

    def claim_pass(graph, resolver):
        calls["n"] += 1
        kitems.emit_kitem(graph, resolver, "Rule one.", kind="rule", stratum=4,
                          spans=[{"bibkey": "B", "node": "n1", "range": "a1",
                                  "role": "asserts"}], produced_by="p1")
        return None

    def derive_pass(graph, resolver):
        # stratum 5: derives from whatever stratum 4 produced (kitem-from-kitem)
        rules = [e for e in kitems.all_kitems(graph) if e.subtype == "rule"]
        for e in rules:
            kitems.emit_kitem(graph, resolver, f"Derived from: {e.id}",
                              kind="derivation", stratum=5,
                              derived_from=[e.id], produced_by="p2")
        return None

    res = fixpoint.run_fixpoint(g, r, [(4, claim_pass), (5, derive_pass)],
                                max_rounds=10)
    assert res["rounds"] >= 2                  # round 2 confirms quiescence
    assert res["rounds"] < 10                  # terminated, not exhausted
    n_kitems = len(kitems.all_kitems(g))
    assert n_kitems == 2                       # one rule + one derivation
    # idempotent: a second driver run changes nothing
    res2 = fixpoint.run_fixpoint(g, r, [(4, claim_pass), (5, derive_pass)])
    assert len(kitems.all_kitems(g)) == n_kitems
    assert res2["new_kitems"] == 0


def test_fixpoint_cascades_new_facts_to_higher_strata():
    g = SemanticGraph(); r = IdentityResolver(g)
    state = {"round": 0}

    def growing_pass(graph, resolver):
        # emits a SECOND rule only after the first round (simulating a pass
        # that sees more once other passes ran)
        state["round"] += 1
        kitems.emit_kitem(graph, resolver, "Always here.", kind="rule",
                          stratum=4, spans=[{"bibkey": "B", "node": "x",
                                             "range": "a", "role": "asserts"}],
                          produced_by="p")
        if state["round"] >= 2:
            kitems.emit_kitem(graph, resolver, "Late arrival.", kind="rule",
                              stratum=4, spans=[{"bibkey": "B", "node": "y",
                                                 "range": "b", "role": "asserts"}],
                              produced_by="p")

    res = fixpoint.run_fixpoint(g, r, [(4, growing_pass)], max_rounds=10)
    names = {e.properties().get("statement_md") for e in kitems.all_kitems(g)}
    assert "Late arrival." in names            # the cascade reached it
    assert res["new_kitems"] == 2


def test_stratum_order_warning():
    msgs = []
    fixpoint.check_stratum_order(
        [("ExtractorA", 0), ("ClaimPass", 4), ("LateExtractor", 0)],
        warn=msgs.append)
    assert len(msgs) == 1 and "LateExtractor" in msgs[0]
    msgs2 = []
    fixpoint.check_stratum_order(
        [("A", 0), ("B", 2), ("C", 4)], warn=msgs2.append)
    assert msgs2 == []


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
