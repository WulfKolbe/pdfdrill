"""
Phase 0 of the capability-planner plan: the branching state-machine (FSM) apparatus
was DEAD CODE — `engine.Engine`/`Transition`/`always`/`Metric`, plus `transitions.py`
and `metrics.py`, were imported by nothing. Only the linear `SequentialEngine`
(the `md`/`drill` engine path) actually runs. Removing the dead FSM leaves the
capability planner as the single, unambiguous "graph traversal" story.

See docs/superpowers/plans/2026-07-14-capability-planner.md (Phase 0).
"""
import importlib
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))


def test_branching_fsm_symbols_are_gone():
    engine = importlib.import_module("pdfdrill.engine")
    for dead in ("Engine", "Transition", "always", "Metric"):
        assert not hasattr(engine, dead), f"dead FSM symbol {dead!r} still in engine.py"


def test_dead_modules_are_deleted():
    for dead in ("pdfdrill.transitions", "pdfdrill.metrics"):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module(dead)
    assert not (SRC / "pdfdrill" / "transitions.py").exists()
    assert not (SRC / "pdfdrill" / "metrics.py").exists()


def test_sequential_engine_and_node_survive():
    engine = importlib.import_module("pdfdrill.engine")
    assert hasattr(engine, "SequentialEngine")
    assert hasattr(engine, "Node")


def test_no_source_file_imports_the_dead_cluster():
    offenders = []
    for py in (SRC / "pdfdrill").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for bad in ("from .transitions", "import transitions",
                    "from .metrics", "import metrics",
                    "from .engine import Engine", "engine import Transition"):
            if bad in text:
                offenders.append(f"{py.name}: {bad}")
    assert not offenders, f"still importing dead cluster: {offenders}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
