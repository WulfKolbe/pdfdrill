"""The uniform enhancement-pass abstraction.

A PASS is one discrete, idempotent enrichment of the L5 Document (the IR):
math, citation, concepts (glossary+acronym), toc, … . Passes declare ordering
via `requires`; the runner topologically orders them, runs each that `applies`,
isolates failures, and skips a pass whose dependency did not run. This is the
general form of ChatGPT's linear `IR → pass → pass → Enhanced IR`, but
dependency-aware and decoupled from any one input format or output backend.

A pass mutates `ctx.doc` in place and returns a `PassResult`. The Document is
loaded once and saved once by the driver (e.g. `pdfdrill enhance`) — passes do
not touch the sidecar/CLI themselves.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional


@dataclass
class PassContext:
    doc: Any                                   # the L5 Document (the IR)
    pdf: Any = None                            # optional file context (sidecar passes)
    sidecar: Any = None
    options: dict = field(default_factory=dict)


@dataclass
class PassResult:
    name: str
    status: str                                # "ran" | "n/a" | "skipped" | "error"
    changed: bool = False
    summary: str = ""
    stats: dict = field(default_factory=dict)


class EnhancementPass(ABC):
    name: str = ""
    requires: tuple[str, ...] = ()

    def applies(self, ctx: PassContext) -> bool:
        """Is this pass relevant to this document? Default: yes."""
        return True

    @abstractmethod
    def run(self, ctx: PassContext) -> PassResult:
        """Enrich ctx.doc in place (idempotent) and report."""


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
REGISTRY: dict[str, EnhancementPass] = {}


def register_pass(p: EnhancementPass) -> EnhancementPass:
    REGISTRY[p.name] = p
    return p


def builtin_passes() -> list[EnhancementPass]:
    return list(REGISTRY.values())


# --------------------------------------------------------------------------- #
# Ordering + runner
# --------------------------------------------------------------------------- #
def order(passes: Iterable[EnhancementPass]) -> list[EnhancementPass]:
    """Topologically sort by `requires` (deps before dependents), deterministic
    by name. `requires` naming a pass outside the pool is ignored (the runner
    decides what to do about a genuinely-absent dependency)."""
    pool = {p.name: p for p in passes}
    done: dict[str, bool] = {}
    out: list[EnhancementPass] = []

    def visit(p: EnhancementPass) -> None:
        if p.name in done:
            return
        done[p.name] = True                    # set first → cycles can't loop
        for r in sorted(p.requires):
            if r in pool:
                visit(pool[r])
        out.append(p)

    for p in sorted(pool.values(), key=lambda x: x.name):
        visit(p)
    return out


def run_pipeline(ctx: PassContext,
                 passes: Optional[Iterable[EnhancementPass]] = None,
                 only: Optional[set[str]] = None,
                 skip: Optional[set[str]] = None) -> list[PassResult]:
    """Run the (filtered, ordered) passes over ctx. A pass runs only if every
    in-pool dependency `ran`; not-applicable / skipped / errored passes do NOT
    satisfy a dependency, so their dependents are skipped (conservative)."""
    pool = list(passes if passes is not None else REGISTRY.values())
    if only:
        pool = [p for p in pool if p.name in only]
    if skip:
        pool = [p for p in pool if p.name not in skip]
    seq = order(pool)
    in_pool = {p.name for p in seq}
    ran: set[str] = set()
    results: list[PassResult] = []
    for p in seq:
        unmet = [r for r in p.requires if r in in_pool and r not in ran]
        if unmet:
            results.append(PassResult(p.name, "skipped",
                                      summary=f"unmet deps: {', '.join(unmet)}"))
            continue
        try:
            if not p.applies(ctx):
                results.append(PassResult(p.name, "n/a", summary="not applicable"))
                continue
            r = p.run(ctx)
        except Exception as e:                 # one pass failing never aborts the run
            results.append(PassResult(p.name, "error",
                                      summary=f"{type(e).__name__}: {e}"))
            continue
        results.append(r)
        if r.status == "ran":
            ran.add(p.name)
    return results
