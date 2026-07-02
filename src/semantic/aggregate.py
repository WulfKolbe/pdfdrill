"""
The aggregation kit — Collector → Accumulator → Readout (A2, 2606.28429v1).

The paper's three-stage pipeline as first-class, registry-registered pieces:
a COLLECTOR produces the multiset (a kitem's independent evidence spans, a
section's quantities, …); an ACCUMULATOR is a commutative monoid over a
declared semantic space (`spaces.py`) folding the multiset; a READOUT maps the
aggregate back into the base space (M → K). Monotonicity — the paper's single
soundness condition, which makes threshold guarantees compositional — is a
DECLARED LAW on every piece and is property-tested in
tests/test_aggregate.py (random pointwise-ordered tuples).

pdfdrill already contained two unlabeled instances of this algebra: the kitems
`accepted` rule (Threshold(2) ∘ Count ∘ IndependentSpans) and belief.py's
weakest-link propagation (a (min, ×) semiring over the DERIVED_FROM DAG). The
A2 refactors name them into the framework — behavior-preserving, golden-tested.

Notes on honesty:
  * Mean is the (sum, count) PRODUCT MONOID (associative), finalized by
    `.value()` — a running float mean is not a monoid.
  * Hybrid(k, α) = r₍ₖ₎ + α(c⁺ − k) — the margin of the k-th best witness plus
    the scaled count surplus (the paper's worked example: sees both the
    count-margin and the edge-margin that min and count each miss). With fewer
    than k values it returns None — a margin that does not exist is not
    reported.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Optional

from .registry import FnSpec, register_fn


# --------------------------------------------------------------------------- #
#  Accumulators — commutative monoids over a declared space
# --------------------------------------------------------------------------- #

class Accumulator:
    name: str = ""
    space: str = ""                              # spaces.py vocabulary
    identity: Any = None

    def combine(self, a, b):
        raise NotImplementedError

    def fold(self, items: Iterable) -> Any:
        acc = self.identity
        for x in items:
            acc = self.combine(acc, x)
        return acc


class Count(Accumulator):
    name, space, identity = "count", "count", 0
    def combine(self, a, x): return a + 1


class Min(Accumulator):
    name, space, identity = "min", "scalar", None
    def combine(self, a, x): return x if a is None else min(a, x)


class Max(Accumulator):
    name, space, identity = "max", "scalar", None
    def combine(self, a, x): return x if a is None else max(a, x)


class Sum(Accumulator):
    name, space, identity = "sum", "scalar", 0
    def combine(self, a, x): return a + x


class Mean(Accumulator):
    """The (sum, count) product monoid — associative where a running mean is
    not; `value()` finalizes."""
    name, space, identity = "mean", "scalar", (0, 0)
    def combine(self, a, x): return (a[0] + x, a[1] + 1)
    @staticmethod
    def value(pair) -> Optional[float]:
        s, n = pair
        return (s / n) if n else None


class WitnessUnion(Accumulator):
    """⊞ = ∪ over witness sets — every aggregate arrives already carrying the
    spans that produced it (the paper's product-space construction)."""
    name, space, identity = "witness_union", "witness_set", frozenset()
    def combine(self, a, x): return a | frozenset(x)


class ProductAcc(Accumulator):
    """Componentwise product of accumulators: fold tuples, each component by
    its own monoid — scalar ⊕ alongside witness ∪ in ONE pass."""
    def __init__(self, *parts: Accumulator):
        self.parts = parts
        self.name = "product(" + ",".join(p.name for p in parts) + ")"
        self.space = "*".join(p.space for p in parts)
        self.identity = tuple(p.identity for p in parts)
    def combine(self, a, x):
        return tuple(p.combine(ai, xi) for p, ai, xi in zip(self.parts, a, x))


# --------------------------------------------------------------------------- #
#  Readouts — M → K
# --------------------------------------------------------------------------- #

class Readout:
    name: str = ""
    space_in: str = ""
    space_out: str = ""

    def __call__(self, m):
        raise NotImplementedError


class Threshold(Readout):
    """m ≥ k → True. The kitems `accepted` rule's readout (k=2)."""
    name, space_in, space_out = "threshold", "count", "bool"
    def __init__(self, k): self.k = k
    def __call__(self, m): return m >= self.k


class SignedDeficit(Readout):
    """c⁺ − k: how far past (or short of) the threshold — sign-compatible with
    Threshold but margin-carrying."""
    name, space_in, space_out = "signed_deficit", "count", "scalar"
    def __init__(self, k): self.k = k
    def __call__(self, m): return m - self.k


class Hybrid(Readout):
    """r₍ₖ₎ + α(c⁺ − k) over a value multiset: the k-th best value's margin
    plus the scaled count surplus — sees both what Min and Count each miss.
    None with fewer than k values (no invented margins)."""
    name, space_in, space_out = "hybrid", "scalar", "scalar"
    def __init__(self, k, alpha): self.k, self.alpha = k, alpha
    def __call__(self, values) -> Optional[float]:
        vs = sorted(values, reverse=True)
        if len(vs) < self.k:
            return None
        return vs[self.k - 1] + self.alpha * (len(vs) - self.k)


# --------------------------------------------------------------------------- #
#  Collectors — produce the multisets the pipelines fold
# --------------------------------------------------------------------------- #

def independent_spans(graph, kitem_id: str) -> frozenset:
    """A kitem's independent (bibkey, node) span pairs over its TRANSITIVE
    evidence — the exact multiset the `accepted` rule counts (kitems.status_of
    is the golden reference)."""
    from . import kitems as _kitems
    spans = _kitems._transitive_spans(graph, kitem_id)
    return frozenset((s.get("bibkey"), s.get("node")) for s in spans)


# --------------------------------------------------------------------------- #
#  Registry entries — each with its spaces + the monotone law
# --------------------------------------------------------------------------- #

for _spec, _impl in [
    (FnSpec("AGG.COUNT", "Count fold over any multiset.", "1",
            laws=("monotone",), space_in="scalar", space_out="count"),
     Count().fold),
    (FnSpec("AGG.MIN", "Min fold (pointwise-monotone on equal-length tuples).",
            "1", laws=("monotone",), space_in="scalar", space_out="scalar"),
     Min().fold),
    (FnSpec("AGG.MAX", "Max fold.", "1", laws=("monotone",),
            space_in="scalar", space_out="scalar"), Max().fold),
    (FnSpec("AGG.SUM", "Sum fold.", "1", laws=("monotone",),
            space_in="scalar", space_out="scalar"), Sum().fold),
    (FnSpec("AGG.MEAN", "Mean as the (sum,count) product monoid.", "1",
            laws=("monotone", "componentwise"), space_in="scalar",
            space_out="scalar"), Mean().fold),
    (FnSpec("AGG.WITNESS_UNION", "Union fold over witness sets — aggregates "
            "arrive carrying their spans.", "1",
            laws=("monotone",), space_in="witness_set",
            space_out="witness_set"), WitnessUnion().fold),
    (FnSpec("RO.THRESHOLD", "m >= k readout (the accepted rule's shape).", "1",
            laws=("monotone", "threshold-sound"), space_in="count",
            space_out="bool"), Threshold),
    (FnSpec("RO.SIGNED_DEFICIT", "c+ - k readout: margin-carrying, "
            "sign-compatible with Threshold.", "1",
            laws=("monotone", "threshold-sound"), space_in="count",
            space_out="scalar"), SignedDeficit),
    (FnSpec("RO.HYBRID", "r_(k) + alpha*(c+ - k): k-th-best margin plus scaled "
            "count surplus; None below k values.", "1",
            laws=("monotone",), space_in="scalar", space_out="scalar"),
     Hybrid),
    (FnSpec("COL.INDEPENDENT_SPANS", "A kitem's independent (bibkey,node) span "
            "pairs over transitive evidence.", "1",
            laws=(), space_in="status", space_out="witness_set"),
     independent_spans),
]:
    register_fn(_spec, _impl)
