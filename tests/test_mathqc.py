"""
Formula QC (src/pdfdrill/mathqc.py): detect FLATTENED formulas — a vision/OCR
reconstruction that linearised a 2-D equation instead of emitting LaTeX (the
"M = m a (F + j ) (B65) … n … 0" failure: subscripts dropped to separate lines,
the equation number mashed in). Such a "formula" is not valid LaTeX and won't
transclude/render, so `pdfdrill mathcheck` flags them for re-`remath`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import mathqc


def test_flattened_examples_flagged():
    assert mathqc.is_flattened("M = m a (F + j ) (B65) n + 0")   # the reported case
    assert mathqc.is_flattened("E = m c (12)")                   # eq-number mashed in
    assert mathqc.is_flattened("k t (x, y) =\nsum i e")          # spans visual lines
    assert mathqc.is_flattened("a b c d e f g h")                # collapsed, no structure


def test_clean_latex_not_flagged():
    assert not mathqc.is_flattened(r"M = m_a (F + j_0)")          # real subscripts
    assert not mathqc.is_flattened(r"x^2 + y^2 = r^2")
    assert not mathqc.is_flattened(r"\frac{1}{2}\sum_i \lambda_i")
    assert not mathqc.is_flattened("a = b + c")                   # simple but valid
    assert not mathqc.is_flattened(r"E = m c^2 \tag{12}")         # number as \tag is fine
    assert not mathqc.is_flattened("")


def test_audit_formulas_counts_and_samples():
    class N:
        def __init__(self, t, **p): self.type, self.id, self.props = t, p.get("id", "x"), p
    nodes = [
        N("Equation", id="e1", latex=r"x^2 + 1"),                # clean
        N("Equation", id="e2", latex="M = m a (F + j ) (B65) n"),  # flattened
        N("Formula", id="f1", latex="a b c d e f"),              # flattened
        N("Formula", id="f2", latex=""),                          # empty (ignored)
        N("Paragraph", id="p", text="not a formula"),
    ]
    rep = mathqc.audit_formulas(nodes)
    assert rep["total"] == 3                                      # 3 non-empty formulas
    assert rep["flattened"] == 2
    assert {s["id"] for s in rep["samples"]} == {"e2", "f1"}


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
