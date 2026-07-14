"""
The capability planner — the backward traversal of the capability graph.

`plan(goal, held, invalid)` resolves the ordered list of commands that establishes
`goal`, inserting each producer's command-name prerequisites (from the manifest)
only when their facts aren't already (validly) held, in topological order. Before
returning it runs `clobber_check`: if any action in the plan would DESTROY a fact
the user currently HOLDS and no later action re-establishes it, the plan is
REFUSED (`ClobberRefused`) rather than silently automating the data-loss bug —
option (a) from the proposal, pure planning logic, zero pipeline change.

`invalid` is the set of held-but-stale capabilities (proof no longer verifies —
Phase D wires it from `Sidecar.capability_valid`); they are treated as absent for
satisfaction (so the planner rebuilds them) but the ORIGINAL `held` set is what
the clobber check protects (a stale model must not license destroying a valid
LaTeX enrichment).

Phase C of docs/superpowers/plans/2026-07-14-capability-planner.md. Pure; no I/O,
no execution.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import capgraph


@dataclass(frozen=True)
class ClobberRefused:
    """A plan was refused because `action` would destroy the still-held,
    not-re-established capability `destroyed`."""
    action: str
    destroyed: str
    plan: tuple[str, ...] = ()

    def __str__(self) -> str:
        return (f"CLOBBER_REFUSED: `{self.action}` would destroy held capability "
                f"{self.destroyed} (the plan {list(self.plan)} does not re-establish "
                f"it). Refusing rather than silently discarding your work — re-run "
                f"the enrichment after, or drop it from the goal.")


# Preferred producer when a fact can be made by several commands (MODEL_BUILT is
# produced by model/markdown/latexbook; the canonical builder is `model`).
_PREFERRED_PRODUCER = {"MODEL_BUILT": "model"}

# Human-friendly capability aliases → the underlying fact name.
_ALIASES = {
    "modelavailable": "MODEL_BUILT",
    "semanticgraphavailable": "SEMANTIC_BUILT",
    "latexingested": "LATEX_INGESTED",
    "geometryfused": "GEOMETRY_FUSED",
    "bibliographyavailable": "BIBLIOGRAPHY_BUILT",
    "tiddlersavailable": "TIDDLERS_BUILT",
    "reportavailable": "REPORT_BUILT",
}


def _producer_index() -> dict[str, list[str]]:
    inv: dict[str, list[str]] = {}
    for cmd, facts in capgraph.produces().items():
        for f in facts:
            inv.setdefault(f, []).append(cmd)
    return inv


def resolve_goal(token: str) -> str:
    """Map a user goal token → a fact name. Accepts a fact name (MODEL_BUILT), a
    capability alias (ModelAvailable), or a command name (model → its primary
    produced fact)."""
    if token in capgraph.all_facts():
        return token
    low = token.lower()
    if low in _ALIASES:
        return _ALIASES[low]
    prod = capgraph.produces().get(token)
    if prod:
        return prod[0]
    raise ValueError(f"unknown goal {token!r} (not a fact, alias, or producing command)")


def _choose_producer(fact: str, producers: list[str]) -> str:
    if fact in _PREFERRED_PRODUCER and _PREFERRED_PRODUCER[fact] in producers:
        return _PREFERRED_PRODUCER[fact]
    return sorted(producers)[0]


def clobber_check(order: list[str], held) -> "ClobberRefused | None":
    """Return a ClobberRefused if any action in `order` destroys a fact in `held`
    that is not re-produced by a LATER action; else None."""
    held = set(held)
    produces = capgraph.produces()
    for i, cmd in enumerate(order):
        later_produced = set()
        for nxt in order[i + 1:]:
            later_produced.update(produces.get(nxt, []))
        for f in capgraph.destroys(cmd):
            if f in held and f not in later_produced:
                return ClobberRefused(cmd, f, tuple(order))
    return None


def plan(goal: str, held=frozenset(), invalid=frozenset()):
    """Ordered command list establishing `goal`, or a ClobberRefused. `held` =
    facts currently held; `invalid` ⊆ held = held-but-stale (treated as absent
    for satisfaction, still protected by the clobber check)."""
    goal_fact = resolve_goal(goal)
    held = set(held)
    effective = held - set(invalid)          # what actually counts as satisfied
    inv = _producer_index()

    order: list[str] = []
    visiting: set[str] = set()
    placed: set[str] = set()

    def add_command(cmd: str):
        if cmd in placed or cmd in visiting:
            return
        visiting.add(cmd)
        for req in capgraph.capability_graph().get(cmd, {}).get("requires", []):
            req_facts = capgraph.capability_facts(req)
            if req_facts and not all(f in effective for f in req_facts):
                add_command(req)
        visiting.discard(cmd)
        if cmd not in placed:
            placed.add(cmd)
            order.append(cmd)

    def need(fact: str):
        if fact in effective:
            return
        producers = inv.get(fact)
        if not producers:
            raise ValueError(f"no command produces {fact!r}")
        add_command(_choose_producer(fact, producers))

    need(goal_fact)
    refusal = clobber_check(order, held)
    if refusal is not None:
        return refusal
    return order


def describe(goal: str, held=frozenset(), invalid=frozenset()) -> str:
    """Human-readable plan / refusal for `pdfdrill plan`."""
    try:
        result = plan(goal, held=held, invalid=invalid)
    except ValueError as e:
        return f"plan error: {e}"
    if isinstance(result, ClobberRefused):
        return str(result)
    if not result:
        return f"{goal}: already satisfied — nothing to do."
    steps = " → ".join(result)
    return f"plan for {goal}: {steps}"
