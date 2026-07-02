"""
Semantic spaces — declared value spaces with a partial order (A1, the
2606.28429v1 amendment).

The paper's discipline: every semantic function maps between DECLARED spaces,
each carrying a partial order and a bottom element; monotonicity w.r.t. those
orders is the single condition that makes threshold guarantees compositional
(its soundness theorem). This module is the vocabulary those declarations draw
from — `FnSpec.space_in`/`space_out` name spaces registered here.

`SemanticSpace{name, order, bottom}`: `order(a, b)` = "a ≤ b" (True/False;
None-order spaces are unordered — declared but not comparable). `product(...)`
builds the componentwise-ordered product space (the paper's product
construction, PARA_0044: a tuple rises iff every component rises), registering
it so later `get_space` calls find it.

Initial vocabulary: scalar, bool, interval, count, ratio, money, time,
witness_set (frozensets, ⊆-ordered — the spatio-temporal-implicant shape),
status (the kitem lattice proposed ≤ supported ≤ accepted; disputed is a
DEMOTION flag, not a lattice point — kept out of the order on purpose).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class SemanticSpace:
    name: str
    order: Optional[Callable[[Any, Any], bool]]   # a <= b ; None = unordered
    bottom: Any


REGISTRY: dict[str, SemanticSpace] = {}


def register_space(sp: SemanticSpace) -> SemanticSpace:
    REGISTRY[sp.name] = sp
    return sp


def get_space(name: str) -> Optional[SemanticSpace]:
    return REGISTRY.get(name)


def all_spaces() -> list[SemanticSpace]:
    return list(REGISTRY.values())


# --------------------------------------------------------------------------- #
#  Initial vocabulary
# --------------------------------------------------------------------------- #

def _num_le(a, b) -> bool:
    return float(a) <= float(b)


def _subset_le(a, b) -> bool:
    return frozenset(a) <= frozenset(b)


def _interval_le(a, b) -> bool:
    # interval containment order: [a0,a1] <= [b0,b1] iff a is inside b
    return float(b[0]) <= float(a[0]) and float(a[1]) <= float(b[1])


_STATUS_RANK = {"proposed": 0, "supported": 1, "accepted": 2}


def _status_le(a, b) -> bool:
    ra, rb = _STATUS_RANK.get(a), _STATUS_RANK.get(b)
    return ra is not None and rb is not None and ra <= rb


for _sp in [
    SemanticSpace("scalar", _num_le, 0.0),
    SemanticSpace("bool", lambda a, b: (not a) or bool(b), False),
    SemanticSpace("interval", _interval_le, (0.0, 0.0)),
    SemanticSpace("count", _num_le, 0),
    SemanticSpace("ratio", _num_le, 0.0),
    SemanticSpace("money", _num_le, 0.0),
    SemanticSpace("time", _num_le, 0.0),
    SemanticSpace("witness_set", _subset_le, frozenset()),
    SemanticSpace("status", _status_le, "proposed"),
]:
    register_space(_sp)


# --------------------------------------------------------------------------- #
#  Products — componentwise order (PARA_0044)
# --------------------------------------------------------------------------- #

def product(*names: str) -> SemanticSpace:
    """The componentwise-ordered product of registered spaces: a tuple rises
    iff EVERY component rises (mixed movement is incomparable — the honest
    partial order, never a collapsed total one). Registered under
    'name1*name2*…' so later `get_space` calls find the same object."""
    if len(names) < 2:
        raise ValueError("product() needs >= 2 space names")
    parts = []
    for n in names:
        sp = get_space(n)
        if sp is None:
            raise KeyError(f"unknown space: {n}")
        parts.append(sp)
    pname = "*".join(names)
    existing = get_space(pname)
    if existing is not None:
        return existing

    def _order(a, b) -> bool:
        if len(a) != len(parts) or len(b) != len(parts):
            return False
        return all(sp.order is not None and sp.order(x, y)
                   for sp, x, y in zip(parts, a, b))

    return register_space(SemanticSpace(
        pname, _order, tuple(sp.bottom for sp in parts)))
