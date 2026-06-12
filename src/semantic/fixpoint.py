"""
The fixpoint driver + stratum discipline (two-store plan, step 3).

"Repeating build-up" made safe: run the kitem-producing passes (strata >= 4)
in stratum order, repeatedly, until a full round adds no new kitem. Three
properties make this terminating and idempotent — all supplied by the
existing machinery, not by this driver:

  * content-hash identity   re-deriving the same statement is a no-op
                            (kitems.emit_kitem resolves before minting)
  * additive-only writes    no pass mutates a lower stratum
  * stratum monotonicity    a pass reads its own stratum and below, writes
                            its own and above — never downward

`check_stratum_order` is the (warning, not fail) enforcement hook: the
configured pipeline must be non-decreasing in stratum, which is the static
half of the monotonicity rule (the dynamic half — what a pass actually
touches — stays a code-review property until it ever bites).
"""
from __future__ import annotations

import sys
from typing import Any, Callable

from . import kitems as _kitems

Pass = Callable[..., Any]            # pass(graph, resolver) -> ignored


def _kitem_fingerprint(graph) -> frozenset:
    """The quiescence test: the set of (kitem id, #evidence rows) — grows when
    a new kitem is minted OR new evidence lands on an existing one."""
    return frozenset((e.id, len(e.evidence)) for e in _kitems.all_kitems(graph))


def run_fixpoint(graph, resolver, passes: list[tuple[int, Pass]],
                 max_rounds: int = 10) -> dict[str, Any]:
    """Run (stratum, pass) callables in stratum order, looping until a full
    round changes nothing (or max_rounds). Returns {rounds, new_kitems}."""
    passes = sorted(passes, key=lambda t: t[0])
    before_all = len(_kitems.all_kitems(graph))
    rounds = 0
    prev = _kitem_fingerprint(graph)
    while rounds < max_rounds:
        rounds += 1
        for _stratum, fn in passes:
            fn(graph, resolver)
        cur = _kitem_fingerprint(graph)
        if cur == prev:
            break                          # quiescence: the round was a no-op
        prev = cur
    return {"rounds": rounds,
            "new_kitems": len(_kitems.all_kitems(graph)) - before_all}


def check_stratum_order(named: list[tuple[str, int]],
                        warn: Callable[[str], Any] = None) -> bool:
    """The static monotonicity check: the configured order must be
    non-decreasing in stratum. Warns (never raises) on each inversion."""
    if warn is None:
        warn = lambda m: print(m, file=sys.stderr)
    ok = True
    high = None
    for name, stratum in named:
        if high is not None and stratum < high[1]:
            warn(f"[stratum] {name} (stratum {stratum}) is configured AFTER "
                 f"{high[0]} (stratum {high[1]}) — a pass must never run "
                 f"below an already-run higher stratum")
            ok = False
        if high is None or stratum >= high[1]:
            high = (name, stratum)
    return ok
