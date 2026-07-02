"""
semantic/aggregate.py — the aggregation kit (A2, 2606.28429v1): Collector →
Accumulator (commutative monoid over a declared space) → Readout (M → K),
mirroring the paper's collect → count-constrained fold → readout pipeline.
Monotonicity is PROPERTY-TESTED (random pointwise-ordered tuples, assert order
preservation in the out space) — the paper's soundness condition as a unit test.
"""
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic import aggregate as A
from semantic import registry as R
from semantic import spaces as S


def test_accumulators_fold():
    assert A.Count().fold([3, 1, 2]) == 3
    assert A.Min().fold([3, 1, 2]) == 1
    assert A.Max().fold([3, 1, 2]) == 3
    assert A.Sum().fold([3, 1, 2]) == 6
    # Mean is the (sum, count) product monoid — associative; value() finalizes
    m = A.Mean()
    pair = m.fold([3, 1, 2])
    assert pair == (6, 3) and m.value(pair) == 2.0
    assert A.WitnessUnion().fold([frozenset({"a"}), frozenset({"b"})]) == \
        frozenset({"a", "b"})
    # empty multisets → the monoid identity
    assert A.Count().fold([]) == 0
    assert A.WitnessUnion().fold([]) == frozenset()


def test_product_accumulator_componentwise():
    # the paper's product space: scalar ⊕ alongside witness ∪, in ONE fold
    p = A.ProductAcc(A.Sum(), A.WitnessUnion())
    out = p.fold([(1, frozenset({"a"})), (2, frozenset({"b"}))])
    assert out == (3, frozenset({"a", "b"}))
    assert p.identity == (0, frozenset())


def test_readouts():
    assert A.Threshold(2)(3) is True and A.Threshold(2)(1) is False
    assert A.SignedDeficit(2)(5) == 3 and A.SignedDeficit(2)(1) == -1
    # Hybrid(k, α) over a value multiset: r_(k) + α(c⁺ − k)
    h = A.Hybrid(k=2, alpha=0.5)
    # values [0.9, 0.7, 0.4]: r_(2)=0.7 (2nd best), surplus = 3-2 = 1
    assert abs(h([0.9, 0.7, 0.4]) - (0.7 + 0.5 * 1)) < 1e-9
    # fewer than k values → bottom (dishonest to report a margin that isn't there)
    assert h([0.9]) is None


def test_monotonicity_property_accumulators():
    """The paper's soundness condition: pointwise-ordered equal-length tuples →
    fold results ordered in the out space. Random sampling."""
    rng = random.Random(7)
    sc = S.get_space("scalar")
    for acc, needs in [(A.Count(), "count"), (A.Min(), "scalar"),
                       (A.Max(), "scalar"), (A.Sum(), "scalar")]:
        out_sp = S.get_space(needs)
        for _ in range(200):
            n = rng.randint(1, 6)
            a = [rng.uniform(0, 10) for _ in range(n)]
            b = [x + rng.uniform(0, 5) for x in a]        # pointwise a <= b
            fa, fb = acc.fold(a), acc.fold(b)
            assert out_sp.order(fa, fb), f"{acc.name}: {fa} !<= {fb}"
    ws = S.get_space("witness_set")
    wu = A.WitnessUnion()
    for _ in range(100):
        n = rng.randint(1, 5)
        a = [frozenset(rng.sample("abcdef", rng.randint(0, 3))) for _ in range(n)]
        b = [x | frozenset(rng.sample("ghij", rng.randint(0, 2))) for x in a]
        assert ws.order(wu.fold(a), wu.fold(b))


def test_monotonicity_property_readouts():
    rng = random.Random(11)
    bool_sp = S.get_space("bool")
    for _ in range(200):
        m1 = rng.uniform(0, 10)
        m2 = m1 + rng.uniform(0, 5)
        assert bool_sp.order(A.Threshold(3)(m1), A.Threshold(3)(m2))
        assert A.SignedDeficit(3)(m1) <= A.SignedDeficit(3)(m2)
    h = A.Hybrid(k=2, alpha=0.5)
    for _ in range(200):
        n = rng.randint(2, 6)
        a = [rng.uniform(0, 1) for _ in range(n)]
        b = [x + rng.uniform(0, 0.5) for x in a]
        assert h(a) <= h(b)


def test_registered_with_monotone_law_and_spaces():
    for fid in ("AGG.COUNT", "AGG.MIN", "AGG.MAX", "AGG.SUM", "AGG.MEAN",
                "AGG.WITNESS_UNION", "RO.THRESHOLD", "RO.SIGNED_DEFICIT",
                "RO.HYBRID"):
        entry = R.get_fn(fid)
        assert entry is not None, f"{fid} unregistered"
        assert "monotone" in entry.spec.laws, f"{fid} lacks the monotone law"
        assert entry.spec.space_out, f"{fid} lacks space_out"


def test_independent_spans_collector():
    """The kitems collector: a kitem's independent (bibkey, node) span pairs —
    the multiset the accepted rule folds."""
    from semantic.graph import SemanticGraph
    from semantic.identity import IdentityResolver
    from semantic import kitems
    g = SemanticGraph(); r = IdentityResolver(g)
    k = kitems.emit_kitem(g, r, "a statement of fact", kind="claim", stratum=4,
                          spans=[{"bibkey": "A", "node": "p1", "range": "",
                                  "role": "asserts"},
                                 {"bibkey": "A", "node": "p1", "range": "",
                                  "role": "asserts"},          # duplicate
                                 {"bibkey": "B", "node": "p9", "range": "",
                                  "role": "asserts"}],
                          produced_by="claims_v1")
    spans = A.independent_spans(g, k.id)
    assert spans == frozenset({("A", "p1"), ("B", "p9")})


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
