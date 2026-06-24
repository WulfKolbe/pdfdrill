"""Backends — projections off the canonical math tree.

The whole point of the layer: ONE tree (a SymPy expression, anchored by its
`srepr`) is the single source from which every target is generated. SymPy's own
printers already give us several targets for free; the rest are declared as
explicit, named stubs so the architecture (and the roadmap) is visible and a
caller fails loudly instead of silently skipping a target.

Add a real backend later by moving its name from PLANNED into a renderer here —
no caller changes, because everything goes through `render(expr, target)`.
"""
from __future__ import annotations

from typing import Any, Callable

import sympy
from sympy.printing.mathematica import mathematica_code


def _smtlib(expr: Any) -> str:
    # SMT-LIB printing is type-sensitive and only supports a subset; best-effort.
    from sympy.printing.smtlib import smtlib_code
    return smtlib_code(expr)


# target name -> renderer over a SymPy expression
_RENDERERS: dict[str, Callable[[Any], str]] = {
    "sympy_srepr": sympy.srepr,          # the canonical IR serialization
    "sympy_str": str,                    # human SymPy
    "mathematica": mathematica_code,
    "smtlib": _smtlib,
}

# declared-but-not-yet-implemented targets (same tree, future printers)
PLANNED: tuple[str, ...] = ("lean4", "fricas", "graphrag")


def available() -> list[str]:
    """Targets renderable today."""
    return list(_RENDERERS)


def render(expr: Any, target: str) -> str:
    """Render the canonical tree to `target`. NotImplementedError for a PLANNED
    target (names itself); KeyError for an unknown target."""
    fn = _RENDERERS.get(target)
    if fn is not None:
        return fn(expr)
    if target in PLANNED:
        raise NotImplementedError(
            f"{target}: planned canonical-math backend, not yet implemented "
            f"(the tree is ready; only the printer is missing)")
    raise KeyError(target)


def render_all(expr: Any, targets: "list[str] | None" = None) -> dict[str, str]:
    """Best-effort render to several targets; a target that raises is skipped."""
    out: dict[str, str] = {}
    for t in (targets if targets is not None else available()):
        try:
            out[t] = render(expr, t)
        except Exception:
            pass
    return out
