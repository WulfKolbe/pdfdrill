"""Engine — the linear node pipeline behind the `md`/`drill` engine path.

`SequentialEngine` runs a flat list of `Node`s in order over a `DocumentContext`.

Historical note: this module used to also carry a branching state-machine
(`Engine` + declarative `Transition` edges, driven by `transitions.py`) and a
`Metric` layer (`metrics.py`). Both were dead — imported by nothing — and were
removed in Phase 0 of the capability-planner work (see
docs/superpowers/plans/2026-07-14-capability-planner.md). The capability planner
(`capability_planner.py`) is now the single "graph traversal" story; the runtime
pipeline is strictly the linear engine below.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from .context import DocumentContext


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
# SequentialEngine — flat, in-order pipeline (the only engine that runs)
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
