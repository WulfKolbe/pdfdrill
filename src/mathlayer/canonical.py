"""The canonical math record — a thin wrapper around the parsed SymPy tree whose
`srepr` is the canonical IR. JSON-safe (`to_dict`) so it can live on an FO/EQ
object's `props["math"]`, while the in-memory `expr` carries the live tree for
backend rendering during a single run.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from . import backends
from .parse import to_sympy


@dataclass
class CanonicalMath:
    latex: str
    srepr: Optional[str]                 # the canonical IR — evaluated normal form
    sympy: Optional[str]                 # human SymPy string
    role: str                            # "expression" | "relation" | "unparsed"
    srepr_raw: Optional[str] = None      # the structure-preserving parse (provenance)
    error: Optional[str] = None
    # the live tree (not serialized) — for rendering backends this run
    expr: Any = field(default=None, repr=False, compare=False)

    def to_dict(self, render: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {
            "ir": "sympy",
            "srepr": self.srepr,
            "srepr_raw": self.srepr_raw,
            "sympy": self.sympy,
            "role": self.role,
            "error": self.error,
            "targets_planned": list(backends.PLANNED),
        }
        if render and self.expr is not None:
            # extra renderings off the SAME tree (best-effort; the canonical
            # srepr/sympy above are always present)
            d["renderings"] = backends.render_all(
                self.expr, ["mathematica", "smtlib"])
        else:
            d["renderings"] = {}
        return d


def from_latex(latex: str) -> CanonicalMath:
    """Parse one LaTeX string into the canonical record (never raises).

    latex2sympy returns a structure-preserving tree; SymPy auto-evaluates on
    reconstruction, so the canonical IR is the EVALUATED normal form (a stable
    fixpoint that round-trips via `sympy.sympify(srepr)`). The raw parse is kept
    under `srepr_raw` for provenance."""
    raw = to_sympy(latex)
    if raw is None:
        return CanonicalMath(latex=latex, srepr=None, sympy=None,
                             role="unparsed",
                             error="parser unavailable or LaTeX did not parse")
    import sympy
    raw_srepr = sympy.srepr(raw)
    try:
        canon = sympy.sympify(raw_srepr)          # → evaluated normal form
    except Exception:
        canon = raw
    role = "relation" if isinstance(canon, sympy.core.relational.Relational) \
        else "expression"
    return CanonicalMath(latex=latex, srepr=sympy.srepr(canon),
                         sympy=str(canon), role=role,
                         srepr_raw=raw_srepr, expr=canon)
