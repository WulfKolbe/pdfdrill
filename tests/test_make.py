"""
Phase E of the capability-planner plan: the executor + `make`. plan → execute via
an injected runner, stopping at the first failure; a refused (clobbering) plan runs
NOTHING (the guard sits before any side effect).

See docs/superpowers/plans/2026-07-14-capability-planner.md (Phase E).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import capability_planner as CP


def test_execute_runs_all_in_order():
    ran = []
    report = CP.execute(["model", "semantic"],
                        run=lambda c: (ran.append(c), (True, f"{c}-ok"))[1])
    assert ran == ["model", "semantic"]
    assert report["failed"] is None
    assert report["executed"] == ["model", "semantic"]


def test_execute_stops_at_first_failure():
    ran = []

    def run(cmd):
        ran.append(cmd)
        return (cmd != "model"), ("boom" if cmd == "model" else "ok")

    report = CP.execute(["model", "semantic"], run)
    assert ran == ["model"]                        # semantic never attempted
    assert report["failed"] == "model"
    assert report["executed"] == []


def test_make_executes_the_plan():
    ran = []
    report = CP.make("SEMANTIC_BUILT",
                     run=lambda c: (ran.append(c), (True, "ok"))[1],
                     held=frozenset())
    assert ran == ["model", "semantic"]            # planned order executed
    assert report["plan"] == ["model", "semantic"]
    assert report["failed"] is None


def test_make_refused_plan_runs_nothing():
    ran = []
    result = CP.make("SEMANTIC_BUILT",
                     run=lambda c: (ran.append(c), (True, "ok"))[1],
                     held=frozenset({"MODEL_BUILT", "LATEX_INGESTED"}),
                     invalid=frozenset({"MODEL_BUILT"}))
    assert isinstance(result, CP.ClobberRefused)
    assert ran == []                               # the guard runs before any side effect


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
