"""188 — a trailing structural token belongs to the document, not the equation."""
from docmodel.modules.equation import _normalize_latex, _strip_trailing_structure


MEASURED = "\n\\[\n\\frac{d^{2} u}{d \\phi^{2}}+u=\\frac{G M}{B^{2}}\n\\]\n\\end{itemize}"


def test_the_measured_case_loses_the_closer_and_the_wrapper():
    """The trailing token also DEFEATED the wrapper strip, because the
    delimiter regex requires the value to END with \\]. So these kept their
    \\[ \\] too and failed to compile with 'Bad math environment delimiter'."""
    out = _normalize_latex(MEASURED)
    assert "\\end{itemize}" not in out
    assert not out.startswith("\\[") and not out.endswith("\\]")
    assert out == "\\frac{d^{2} u}{d \\phi^{2}}+u=\\frac{G M}{B^{2}}"


def test_several_closers_are_all_dropped():
    assert _normalize_latex("\\[ x=1 \\]\n\\end{itemize}\n\\end{document}") == "x=1"


def test_a_BALANCED_environment_is_kept():
    """Removing a closer whose opener is present would corrupt a correct value
    in order to repair an incorrect one."""
    lx = "\\begin{itemize}\\item x \\end{itemize}"
    assert _strip_trailing_structure(lx) == lx


def test_a_balanced_align_is_untouched():
    lx = "\\begin{aligned} a &= b \\end{aligned}"
    assert _strip_trailing_structure(lx) == lx


def test_an_ordinary_equation_is_unchanged_apart_from_its_wrapper():
    assert _normalize_latex("\\[ E = mc^{2} \\]") == "E = mc^{2}"


def test_a_maths_environment_closer_is_NOT_treated_as_structure():
    """\\end{array} closes mathematics, not a document section."""
    lx = "1 & 2 \\end{array}"
    assert _strip_trailing_structure(lx) == lx


def test_empty_and_none_are_safe():
    assert _normalize_latex("") == ""
    assert _strip_trailing_structure("") == ""


def test_leading_unmatched_begin_is_dropped():
    """MathPix also OPENS a list on the line carrying the first equation:
    \\begin{itemize} \\item[] \\[ … \\] — the mirror of the trailing case."""
    out = _normalize_latex(r"\begin{itemize} \item[] \[ C=\gamma T+\alpha T^{3} \]")
    assert out == r"C=\gamma T+\alpha T^{3}"


def test_leading_begin_with_a_matching_end_is_kept():
    lx = r"\begin{itemize} \item x \end{itemize}"
    assert _strip_trailing_structure(lx) == lx
