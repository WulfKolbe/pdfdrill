"""
semantic/physical.py — the PHY constraint family (S3.2): five live checks
(BOUNDS / CONVERT / CONSERVE / MONO / UNCERT) + two declared-not-faked stubs
(CAUSE / FRAME, waiting on a physics corpus). Each registered + individually
tested; every check returns {'ok': True|False|None, 'detail'} — three-valued
like VER.EQ.RECOMPUTE.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic import physical as P
from semantic import registry as R


def _q(kind, value, unit=None, **extra):
    return {"kind": kind, "value": value, "unit": unit,
            "dimension": {"%": "ratio", "$": "currency"}.get(unit),
            "raw": str(value), **extra}


def test_bounds():
    assert P.check_bounds(_q("ratio", 82, "%"))["ok"] is True     # 82% ∈ [0,100]
    assert P.check_bounds(_q("ratio", 0.82))["ok"] is True        # bare fraction
    assert P.check_bounds(_q("ratio", 130, "%"))["ok"] is False   # >100%
    assert P.check_bounds(_q("count", 42, noun="facts"))["ok"] is True
    assert P.check_bounds(_q("count", -3, noun="facts"))["ok"] is False
    assert P.check_bounds(_q("count", 2.5, noun="facts"))["ok"] is False  # non-int
    assert P.check_bounds(_q("money", 2, "$"))["ok"] is True
    assert P.check_bounds(_q("money", -2, "$"))["ok"] is False
    assert P.check_bounds(_q("named_metric", 90))["ok"] is None   # out of scope


def test_convert_consistency():
    # "2 USD ... could drop to 40 Cents" — 2 USD = 200 ct, stated 40 ct is a
    # DIFFERENT amount (a drop), so pair-consistency only flags CLAIMED-equal pairs
    ok = P.check_convert_pair(_q("money", 2, "USD"), _q("money", 200, "ct"))
    assert ok["ok"] is True
    bad = P.check_convert_pair(_q("money", 2, "USD"), _q("money", 40, "ct"))
    assert bad["ok"] is False and "200" in bad["detail"]
    # dimension mismatch → uncheckable, never a guess
    assert P.check_convert_pair(_q("money", 2, "USD"),
                                _q("number", 2, "min"))["ok"] is None


def test_conserve():
    assert P.check_conserve({"total": 350, "parts": [7, 50], "op": "mul"})["ok"] is True
    assert P.check_conserve({"total": 100, "parts": [60, 30], "op": "add"})["ok"] is False
    assert P.check_conserve({"total": 90, "parts": [60, 30], "op": "add"})["ok"] is True
    assert P.check_conserve({"total": 90, "parts": []})["ok"] is None


def test_mono_r_at_p():
    # R@P series: recall must be non-increasing as precision rises
    good = [(80, 0.61), (90, 0.44), (95, 0.30)]
    bad = [(80, 0.61), (90, 0.70)]
    assert P.check_mono(good)["ok"] is True
    assert P.check_mono(bad)["ok"] is False
    assert P.check_mono([(90, 0.5)])["ok"] is None    # one point: nothing to check


def test_uncert_propagation():
    # a derivation whose terms came from an approx quantity must carry approx
    ok = P.check_uncert({"kind": "derivation", "approx": True},
                        parents=[{"approx": True}])
    assert ok["ok"] is True
    bad = P.check_uncert({"kind": "derivation"}, parents=[{"approx": True}])
    assert bad["ok"] is False
    none = P.check_uncert({"kind": "derivation"}, parents=[{}])
    assert none["ok"] is True                          # nothing to propagate


def test_stubs_declared_not_faked():
    for fid in ("PHY.CAUSE", "PHY.FRAME"):
        entry = R.get_fn(fid)
        assert entry is not None and entry.spec.laws == ()
        assert entry.impl()["status"] == "not_implemented"


def test_all_five_registered():
    for fid in ("PHY.BOUNDS", "PHY.CONVERT", "PHY.CONSERVE", "PHY.MONO",
                "PHY.UNCERT"):
        assert R.get_fn(fid) is not None, f"{fid} unregistered"


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
