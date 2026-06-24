"""First step of the canonical CSP math layer.

The value is NOT the SymPy representation per se — it's that one canonical tree
(anchored on SymPy's srepr) is the single source future backends project from:
SymPy, Lean4, FriCAS, Mathematica, SMT-LIB, GraphRAG. This seed wires the SymPy
parse + the SymPy/Mathematica/SMT-LIB renderings off that tree, declares the
remaining targets as explicit stubs, and attaches the result to FO/EQ objects.

Parsing uses the imported `latex2sympy2_extended` library (optional `[math]`
extra); everything degrades gracefully when it is absent.
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _have_parser():
    from mathlayer import parse
    return parse.available()


# --------------------------------------------------------------------------- #
# Canonical parse → tree
# --------------------------------------------------------------------------- #
def test_formula_parses_to_expression():
    if not _have_parser():
        print("SKIP (latex2sympy2_extended absent)"); return
    from mathlayer import from_latex
    cm = from_latex(r"\frac{x^2 + 1}{2}")
    assert cm.role == "expression"
    assert cm.srepr and "Pow" in cm.srepr and "Symbol('x')" in cm.srepr


def test_equation_parses_to_relation():
    if not _have_parser():
        print("SKIP"); return
    from mathlayer import from_latex
    cm = from_latex(r"E = mc^2")
    assert cm.role == "relation"            # an EQ object is a relation, not an expr
    assert cm.srepr.startswith("Equality(")


def test_canonical_srepr_round_trips():
    """srepr is the canonical IR — it must reconstruct the same tree."""
    if not _have_parser():
        print("SKIP"); return
    import sympy
    from mathlayer import from_latex
    cm = from_latex(r"\frac{x^2 + 1}{2}")
    again = sympy.sympify(cm.srepr)
    assert sympy.srepr(again) == cm.srepr


# --------------------------------------------------------------------------- #
# Backends off the SAME tree
# --------------------------------------------------------------------------- #
def test_sympy_and_mathematica_backends_render():
    if not _have_parser():
        print("SKIP"); return
    from mathlayer import from_latex
    from mathlayer import backends
    cm = from_latex(r"E = mc^2")
    assert backends.render(cm.expr, "sympy_str") == "Eq(e, c**2*m)"
    assert "==" in backends.render(cm.expr, "mathematica")


def test_planned_backends_are_explicit_stubs():
    from mathlayer import backends
    assert {"lean4", "fricas", "graphrag"} <= set(backends.PLANNED)
    # a planned target raises a CLEAR NotImplementedError naming itself
    try:
        backends.render(object(), "lean4")
        assert False, "expected NotImplementedError"
    except NotImplementedError as e:
        assert "lean4" in str(e)


def test_available_vs_planned_listing():
    from mathlayer import backends
    assert "sympy_srepr" in backends.available()
    assert "mathematica" in backends.available()
    assert set(backends.available()).isdisjoint(backends.PLANNED)


# --------------------------------------------------------------------------- #
# FO / EQ object integration
# --------------------------------------------------------------------------- #
def _obj(t, latex):
    o = types.SimpleNamespace()
    o.type = t
    o.props = {"latex": latex}
    return o


def test_annotate_attaches_math_to_fo_and_eq():
    if not _have_parser():
        print("SKIP"); return
    from mathlayer import annotate_object
    fo = _obj("Formula", r"\frac{x^2+1}{2}")
    eq = _obj("Equation", r"E = mc^2")
    annotate_object(fo); annotate_object(eq)
    assert fo.props["math"]["ir"] == "sympy" and fo.props["math"]["role"] == "expression"
    assert eq.props["math"]["role"] == "relation"
    assert "mathematica" in eq.props["math"]["renderings"]
    assert set(fo.props["math"]["targets_planned"]) >= {"lean4", "fricas", "graphrag"}


def test_annotate_skips_non_math_objects_and_empty_latex():
    from mathlayer import annotate_object
    para = _obj("Paragraph", "hello")
    assert annotate_object(para) is None and "math" not in para.props
    empty = _obj("Formula", "")
    assert annotate_object(empty) is None


# --------------------------------------------------------------------------- #
# Operator / symbol-normalization layer (our own LaTeX improvement, pre-parse)
# --------------------------------------------------------------------------- #
def test_operator_normalize_collapses_font_wrappers():
    from mathlayer import operators
    assert operators.normalize(r"\mathcal{L}") == "L"
    assert operators.normalize(r"\mathbb{R}^n") == "R^n"
    assert operators.normalize(r"\mathbf{x}^2") == "x^2"
    # nested / repeated wrappers collapse fully
    assert operators.normalize(r"\mathcal{X} \to \mathbb{Y}") == r"X \to Y"


def test_operator_normalize_applies_user_ops_first():
    """The operator-definition layer: a user map rewrites author operators that
    expansion alone can't fix (e.g. an undefined-to-the-parser macro)."""
    from mathlayer import operators
    out = operators.normalize(r"\gL + 1", ops={r"\gL": "L"})
    assert out == "L + 1"


def test_from_latex_normalizes_before_parse():
    if not _have_parser():
        print("SKIP"); return
    from mathlayer import from_latex
    cm = from_latex(r"\mathbb{R}^n")           # fails raw, parses after normalize
    assert cm.role == "expression"
    # parses after our normalization (latex2sympy lowercases symbols: R->r)
    assert "Pow(" in (cm.srepr or "") and "Symbol('r')" in (cm.srepr or "")
    assert cm.normalized == "R^n" and cm.normalized != cm.latex


def test_annotate_records_source_and_normalized():
    if not _have_parser():
        print("SKIP"); return
    from mathlayer import annotate_object
    fo = _obj("Formula", r"\mathcal{L}")
    annotate_object(fo)
    m = fo.props["math"]
    assert m["source"] == "latex"              # the (expanded) latex field
    assert m["normalized"] == "L"              # \mathcal{L} -> L (our layer)
    assert "Symbol('l')" in (m["srepr"] or "")  # parser lowercases L->l


def test_graceful_when_parser_absent(monkeypatch=None):
    """No parser installed → from_latex yields an 'unparsed' record, no raise."""
    from mathlayer import parse, from_latex
    saved_fn, saved_tried = parse._FN, parse._TRIED
    parse._FN, parse._TRIED = None, True
    try:
        cm = from_latex(r"E=mc^2")
        assert cm.role == "unparsed" and cm.srepr is None and cm.error
    finally:
        parse._FN, parse._TRIED = saved_fn, saved_tried


if __name__ == "__main__":
    for fn in [test_formula_parses_to_expression, test_equation_parses_to_relation,
               test_canonical_srepr_round_trips, test_sympy_and_mathematica_backends_render,
               test_planned_backends_are_explicit_stubs, test_available_vs_planned_listing,
               test_annotate_attaches_math_to_fo_and_eq,
               test_annotate_skips_non_math_objects_and_empty_latex,
               test_operator_normalize_collapses_font_wrappers,
               test_operator_normalize_applies_user_ops_first,
               test_from_latex_normalizes_before_parse,
               test_annotate_records_source_and_normalized,
               test_graceful_when_parser_absent]:
        fn(); print("PASS", fn.__name__)
    print("\nAll tests passed.")
