"""
semantic/verify.py — VER.EQ.RECOMPUTE (S3.1): recompute derivation quantity
records and confirm/refute the stated result. Integer rounding tolerance ±1;
approx=True widens to ±5% relative.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from semantic import verify as V
from semantic import registry as R


def _deriv(lhs_terms, op, rhs, **extra):
    return {"kind": "derivation", "value": rhs, "unit": None, "dimension": None,
            "raw": "fixture", "payload": {"lhs_terms": lhs_terms, "op": op,
                                          "rhs": rhs}, **extra}


def test_fo0044_verifies():
    # the real 2303.11082 derivation: 7,871,085 * 0.86 = 6,769,133.1 ≈ 6,769,133
    r = V.verify_derivation(_deriv([7871085, 0.86], "mul", 6769133))
    assert r["ok"] is True
    assert abs(r["computed"] - 6769133.1) < 1e-6
    assert r["stated"] == 6769133


def test_corrupted_rhs_refutes_with_detail():
    r = V.verify_derivation(_deriv([7871085, 0.68], "mul", 6769133))
    assert r["ok"] is False
    assert abs(r["computed"] - 7871085 * 0.68) < 1e-6
    assert "computed" in r["detail"] and str(int(r["computed"])) in r["detail"]


def test_add_sub_div_chains():
    assert V.verify_derivation(_deriv([1, 2, 3], "add", 6))["ok"] is True
    assert V.verify_derivation(_deriv([10, 4], "sub", 6))["ok"] is True
    assert V.verify_derivation(_deriv([10, 4], "div", 2.5))["ok"] is True
    assert V.verify_derivation(_deriv([10, 4], "div", 3))["ok"] is False


def test_approx_widens_to_5_percent():
    # stated 100 vs computed 104: fails at ±1, passes with approx (±5% rel)
    exact = V.verify_derivation(_deriv([13, 8], "mul", 100))
    assert exact["ok"] is False
    approx = V.verify_derivation(_deriv([13, 8], "mul", 100, approx=True))
    assert approx["ok"] is True                        # 104 within 5% of 100


def test_non_derivation_is_uncheckable():
    r = V.verify_derivation({"kind": "ratio", "value": 82})
    assert r["ok"] is None and "not a derivation" in r["detail"]


def test_registered():
    entry = R.get_fn("VER.EQ.RECOMPUTE")
    assert entry is not None and entry.impl is V.verify_derivation


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
