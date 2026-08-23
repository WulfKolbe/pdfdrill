r"""126 — flag an environment-balance defect; do not blank the equation.

MathPix glues a stray closer onto display math that ends a list:
`\[ x \] \end{itemize}`. Two facts live there: the mathematics is intact (and
renderable() repairs it — 0902.0431 went 31 unrendered -> 7), and the
extraction is defective (a fragment of prose structure inside a maths value).
Rejecting the value records the second by destroying the first.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.env_balance import env_defect, flag_document, summarise
from pdfdrill.report_tex import renderable


def test_trailing_stray_closer_is_flagged():
    d = env_defect(r"\[ (A \vee B)^{\prime}=-B \vee A . \] \end{itemize}")
    assert d["unmatched_end"] == {"itemize": 1}
    assert d["unmatched_begin"] == {}
    assert d["trailing"] == "itemize"


def test_the_flagged_value_still_renders():
    """The whole point of reading (b): flagged and rendered are not exclusive."""
    src = r"\[ (A \vee B)^{\prime}=-B \vee A . \] \end{itemize}"
    assert env_defect(src) is not None
    assert renderable(src) == r"(A \vee B)^{\prime}=-B \vee A ."


def test_balanced_values_are_not_flagged():
    for v in (r"\begin{aligned} a &= b \end{aligned}",
              r"\left(\begin{array}{cc}1&2\\3&4\end{array}\right)",
              r"\frac{a}{b}", "", r"x^2"):
        assert env_defect(v) is None, v


def test_counts_not_set_membership():
    """`array` opened once and closed twice is unbalanced even though the name
    appears on both sides — a set-difference check would call this clean."""
    d = env_defect(r"\begin{array}{c}1\end{array}\end{array}")
    assert d["unmatched_end"] == {"array": 1}


def test_unmatched_opener_is_flagged_too():
    d = env_defect(r"\begin{array}{c} 1")
    assert d["unmatched_begin"] == {"array": 1}
    assert d["unmatched_end"] == {}
    assert d["trailing"] is None


def test_mid_string_closer_is_flagged_and_not_repairable():
    """Only a TRAILING closer is repaired; one mid-string leaves the value
    genuinely unrenderable, and both facts must show."""
    src = r"x \end{itemize} + y"
    assert env_defect(src)["unmatched_end"] == {"itemize": 1}
    assert env_defect(src)["trailing"] is None
    assert renderable(src) == ""


def _doc(latexes):
    from docmodel.core import Document, DocObject
    d = Document()
    for i, lx in enumerate(latexes):
        d.add(DocObject(type="Equation", id=f"e{i}", props={"latex": lx}))
    return d


def test_flag_document_sets_and_clears():
    d = _doc([r"\[ x \] \end{itemize}", r"\frac{a}{b}"])
    assert flag_document(d) == 1
    assert d.objects["e0"].props["env_mismatch"]["unmatched_end"] == {"itemize": 1}
    assert "env_mismatch" not in d.objects["e1"].props
    # idempotent, and a corrected value LOSES the flag rather than keeping a
    # stale one
    assert flag_document(d) == 1
    d.objects["e0"].props["latex"] = r"x"
    assert flag_document(d) == 0
    assert "env_mismatch" not in d.objects["e0"].props


def test_summarise_groups_by_environment():
    d = _doc([r"\[ x \] \end{itemize}", r"\[ y \] \end{itemize}",
              r"\begin{array}{c} 1", r"\frac{a}{b}"])
    flag_document(d)
    assert summarise(d) == {"itemize": 2, "array": 1}


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
