"""mathlayer — the seed of a canonical CSP math layer.

Step 1: LaTeX (from FO/EQ objects) → a canonical tree (a SymPy expression,
anchored by its `srepr`) → backend renderings. The value is the SINGLE tree:
SymPy is just the first backend; Lean4 / FriCAS / Mathematica / SMT-LIB /
GraphRAG annotations are future printers off the same tree (see `backends.PLANNED`).

Parsing uses the imported `latex2sympy2_extended` library (optional `[math]`
extra: `pip install 'pdfdrill[math]'`); everything degrades gracefully when it
is absent.

    from mathlayer import from_latex, annotate_object, backends
    cm = from_latex(r"E = mc^2")          # CanonicalMath(role="relation", srepr=…)
    backends.render(cm.expr, "mathematica")
    annotate_object(formula_obj)          # → formula_obj.props["math"]
"""
from __future__ import annotations

from . import backends, parse
from .annotate import MATH_TYPES, annotate_document, annotate_object
from .canonical import CanonicalMath, from_latex

__all__ = [
    "from_latex", "CanonicalMath",
    "annotate_object", "annotate_document", "MATH_TYPES",
    "backends", "parse",
]
