"""
Unit tests for Phase-2 scoring (pdfdrill.scoring).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.scoring import normalize_latex, latex_similarity, score_equation


def test_normalize_ignores_cosmetic_differences():
    a = "$$E = mc^2$$"
    b = "E=mc^{2}".replace("^{2}", "^2")
    # spacing + delimiters normalized away
    assert normalize_latex("$E = m c^2$") == normalize_latex("E=mc^2")
    assert normalize_latex("\\left(x\\right)") == normalize_latex("(x)")
    assert normalize_latex("\\operatorname{Exact}(e)") == normalize_latex("Exact(e)")


def test_similarity_high_for_equivalent_latex():
    s = latex_similarity("\\begin{aligned} s_e(q) =& \\lambda_1 x \\end{aligned}",
                         "s_{e}(q)= \\lambda_{1} x")
    assert s > 0.7
    assert latex_similarity("a+b", "a+b") == 1.0
    assert latex_similarity("a+b", "") == 0.0


def test_score_equation_agreement_and_flags():
    cands = {
        "snip": {"latex": "E=mc^{2}", "score": 0.98},
        "llm": {"latex": "E = mc^2", "score": None},
    }
    s = score_equation("E=m c^2", cands)
    assert set(s["agreement"]) == {"snip", "llm"}
    assert s["snip_confidence"] == 0.98
    assert s["mean_agreement"] > 0.8
    assert s["flags"] == []                       # high agreement + confidence


def test_score_flags_low_confidence_and_disagreement():
    cands = {"snip": {"latex": "totally different stuff", "score": 0.30}}
    s = score_equation("E = mc^2", cands)
    assert "low_confidence" in s["flags"]
    assert "low_agreement" in s["flags"]
    assert s["min_signal"] is not None and s["min_signal"] < 0.6


def test_no_candidates_flagged():
    s = score_equation("E=mc^2", {})
    assert "no_competing_reading" in s["flags"]
    assert s["mean_agreement"] is None


def test_single_low_conf_not_corroborated():
    s = score_equation("E=mc^2", {"snip": {"latex": "E=mc^2", "score": 0.3}})
    assert s["corroborated"] is False
    assert "low_confidence" in s["flags"]


def test_corroboration_clears_low_confidence():
    # Two independent readings agree strongly -> trust despite low snip conf.
    cands = {"snip": {"latex": "E=mc^2", "score": 0.3},
             "llm": {"latex": "E = mc^{2}", "score": None}}
    s = score_equation("E=mc^2", cands)
    assert s["corroborated"] is True
    assert "low_confidence" not in s["flags"]


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__)
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__)
            print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} failed out of {len(tests)}")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
