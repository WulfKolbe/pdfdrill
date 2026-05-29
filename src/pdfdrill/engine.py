"""Engine — state-machine-driven pipeline with declarative transitions.

The engine drives Nodes over a DocumentContext using a transition table.
Each tick: find first matching transition from current state, run target
node, update state, log, persist.

Two modes:
  tick(ctx)              run one transition
  run(ctx)               run to terminal state
  plan(ctx)              dry-run, show path
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Optional

from .context import DocumentContext, STATE_ANSWER


# ---------------------------------------------------------------------------
# Node — a single processing step
# ---------------------------------------------------------------------------

class Node(ABC):
    name: str = "unnamed"

    @abstractmethod
    def should_run(self, ctx: DocumentContext) -> bool:
        """Return True if this node can/should execute."""

    @abstractmethod
    def run(self, ctx: DocumentContext) -> DocumentContext:
        """Execute the node, returning the updated context."""


# ---------------------------------------------------------------------------
# Transition — declarative edge in the state graph
# ---------------------------------------------------------------------------

@dataclass
class Transition:
    from_state: str
    to_state: str
    node: Node
    guard: Callable[[DocumentContext], bool] = lambda _: True
    label: str = ""


def always(_: DocumentContext) -> bool:
    return True


# ---------------------------------------------------------------------------
# Metric
# ---------------------------------------------------------------------------

class Metric(ABC):
    name: str

    @abstractmethod
    def compute(self, ctx: DocumentContext) -> float:
        ...


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class Engine:
    def __init__(
        self,
        transitions: list[Transition],
        metrics: Optional[list[Metric]] = None,
        verbose: bool = False,
    ):
        self.transitions = transitions
        self.metrics = metrics or []
        self.verbose = verbose

    def _find_transition(self, ctx: DocumentContext) -> Optional[Transition]:
        """Find the first transition whose from_state matches and guard passes."""
        for t in self.transitions:
            if t.from_state == ctx.state and t.guard(ctx):
                return t
        return None

    def tick(self, ctx: DocumentContext) -> tuple[DocumentContext, bool]:
        """Run one state transition. Returns (ctx, is_terminal)."""
        t = self._find_transition(ctx)
        if t is None:
            if self.verbose:
                print(f"[engine] no transition from state={ctx.state}", flush=True)
            return ctx, True

        node = t.node
        if self.verbose:
            label = t.label or node.name
            print(f"[{ctx.state} → {t.to_state}] {label}...", flush=True)

        t0 = time.monotonic()
        ctx = node.run(ctx)
        elapsed = time.monotonic() - t0

        ctx.state = t.to_state
        ctx.log(node.name, detail=t.label, cost_ms=round(elapsed * 1000, 1))

        if self.verbose:
            print(f"  done in {elapsed:.2f}s  state={ctx.state}", flush=True)

        return ctx, ctx.state == STATE_ANSWER

    def run(self, ctx: DocumentContext) -> DocumentContext:
        """Run transitions until terminal state or no transition found."""
        steps = 0
        while ctx.state != STATE_ANSWER and steps < 50:
            ctx, done = self.tick(ctx)
            steps += 1
            if done:
                break
        return ctx

    def plan(self, ctx: DocumentContext) -> list[dict]:
        """Dry-run: walk the graph with guards only, return planned path."""
        path = []
        test_ctx = ctx.model_copy(deep=True)
        steps = 0
        while test_ctx.state != STATE_ANSWER and steps < 50:
            t = self._find_transition(test_ctx)
            if t is None:
                break
            path.append({
                "from": t.from_state,
                "to": t.to_state,
                "node": t.node.name,
                "label": t.label,
            })
            test_ctx.state = t.to_state
            steps += 1
        return path


# ---------------------------------------------------------------------------
# Legacy: simple sequential pipeline (for backward compat with existing nodes)
# ---------------------------------------------------------------------------

class SequentialEngine:
    """Runs a flat list of nodes in order (no state machine)."""

    def __init__(self, nodes: list[Node], verbose: bool = False):
        self.nodes = nodes
        self.verbose = verbose
        self._current = 0

    def tick(self, ctx: DocumentContext) -> tuple[DocumentContext, bool]:
        while self._current < len(self.nodes):
            node = self.nodes[self._current]
            self._current += 1
            if not node.should_run(ctx):
                continue
            if self.verbose:
                print(f"[{node.name}] running...", flush=True)
            t0 = time.monotonic()
            ctx = node.run(ctx)
            elapsed = time.monotonic() - t0
            ctx.log(node.name, cost_ms=round(elapsed * 1000, 1))
            if self.verbose:
                print(f"  done in {elapsed:.2f}s", flush=True)
            return ctx, self._current >= len(self.nodes)
        return ctx, True

    def run(self, ctx: DocumentContext) -> DocumentContext:
        self._current = 0
        while self._current < len(self.nodes):
            ctx, _ = self.tick(ctx)
        return ctx
