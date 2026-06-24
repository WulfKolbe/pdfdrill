"""Our own operator / symbol-definition layer — a pre-parse LaTeX improvement.

Rationale (empirically grounded): the macro-EXPANDED LaTeX parses far better than
the author's macro source (5/7 vs 1/7 on a representative sample — unknown author
macros like \\gL/\\R/\\vx just fail), so we always feed `props["latex"]`. But the
expanded form still carries font wrappers (\\mathcal{L}, \\mathbb{R}) that the
parser turns into mangled symbols. Expansion is the author's; the CANONICAL form
is ours to improve — exactly as we add a TOC / glossary / index without changing
content. This layer rewrites the surface BEFORE parsing:

  1. a user/operator-definition `ops` map (literal macro → replacement) — the
     hook where a project declares `\\gL -> L_loss`, `\\inner{}{} -> ...`, etc.;
  2. font-wrapper collapse on a simple-token argument: \\mathcal{L} -> L.

It changes only the REPRESENTATION fed to the parser; the original LaTeX is kept
on the object (`latex`) and the normalized string is recorded (`normalized`).
"""
from __future__ import annotations

import re
from typing import Optional

# font/style wrappers whose single-token argument is the real symbol
FONT_WRAPPERS = ("mathcal", "mathbb", "mathbf", "mathrm", "mathfrak",
                 "mathscr", "mathsf", "mathtt", "boldsymbol", "symbf", "symcal")

_WRAP = re.compile(
    r"\\(?:" + "|".join(FONT_WRAPPERS) + r")\s*\{([A-Za-z0-9]+)\}")


def collapse_font_wrappers(latex: str) -> str:
    """\\mathcal{L} -> L, repeatedly (handles several in one string)."""
    prev = None
    s = latex
    while prev != s:
        prev = s
        s = _WRAP.sub(r"\1", s)
    return s


def normalize(latex: str, ops: Optional[dict[str, str]] = None) -> str:
    """Apply the operator-definition map (if any), then collapse font wrappers.
    Returns the improved LaTeX to feed the parser. Pure; idempotent."""
    s = latex
    if ops:
        # longest keys first so \\gLL replaces before \\gL
        for macro in sorted(ops, key=len, reverse=True):
            s = s.replace(macro, ops[macro])
    return collapse_font_wrappers(s)
