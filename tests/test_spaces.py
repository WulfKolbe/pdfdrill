"""
semantic/spaces.py — the semantic-space registry (A1, 2606.28429v1 amendment):
SemanticSpace{name, order, bottom} with the initial vocabulary + product()
(componentwise order — the paper's product construction, PARA_0044).
Order-law property checks: reflexive, antisymmetric-ish (on distinct reprs),
transitive on sampled triples.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic import spaces as S


def test_vocabulary_present():
    for name in ("scalar", "bool", "interval", "count", "ratio", "money",
                 "time", "witness_set", "status"):
        sp = S.get_space(name)
        assert sp is not None, f"space {name!r} missing"
        assert sp.name == name


def test_scalar_and_count_order():
    sc = S.get_space("scalar")
    assert sc.order(1.0, 2.0) is True and sc.order(2.0, 1.0) is False
    assert sc.order(1.0, 1.0) is True                     # reflexive
    cn = S.get_space("count")
    assert cn.order(0, 5) is True and cn.bottom == 0


def test_witness_set_order_is_subset():
    ws = S.get_space("witness_set")
    assert ws.order(frozenset(), frozenset({"a"})) is True
    assert ws.order(frozenset({"a"}), frozenset({"a", "b"})) is True
    assert ws.order(frozenset({"a"}), frozenset({"b"})) is False
    assert ws.bottom == frozenset()


def test_status_order_is_the_kitem_lattice():
    st = S.get_space("status")
    assert st.order("proposed", "supported") is True
    assert st.order("supported", "accepted") is True
    assert st.order("accepted", "proposed") is False
    assert st.bottom == "proposed"


def test_product_componentwise():
    p = S.product("scalar", "witness_set")
    assert p.name == "scalar*witness_set"
    a = (1.0, frozenset({"x"}))
    b = (2.0, frozenset({"x", "y"}))
    assert p.order(a, b) is True                          # both components rise
    assert p.order(b, a) is False
    # mixed: scalar rises but witness set is incomparable → not ordered
    c = (3.0, frozenset({"z"}))
    assert p.order(a, c) is False
    assert p.bottom == (0.0, frozenset())
    # the product registers itself → later get_space finds it
    assert S.get_space("scalar*witness_set") is p


def test_order_laws_property_check():
    """Sampled reflexivity + transitivity over the ordered spaces."""
    import itertools
    samples = {
        "scalar": [0.0, 1.0, 2.5], "count": [0, 1, 7],
        "ratio": [0.0, 0.5, 1.0],
        "witness_set": [frozenset(), frozenset({"a"}), frozenset({"a", "b"})],
        "status": ["proposed", "supported", "accepted"],
    }
    for name, vals in samples.items():
        sp = S.get_space(name)
        for v in vals:
            assert sp.order(v, v), f"{name}: not reflexive on {v!r}"
        for x, y, z in itertools.product(vals, repeat=3):
            if sp.order(x, y) and sp.order(y, z):
                assert sp.order(x, z), f"{name}: not transitive {x},{y},{z}"


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
