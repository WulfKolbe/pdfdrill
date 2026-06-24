"""LaTeX → SymPy, via the imported `latex2sympy2_extended` library (optional
`[math]` extra). Lazy-loaded and graceful: when the library is absent or a
string doesn't parse, `to_sympy` returns None rather than raising — so the
canonical layer degrades to an 'unparsed' record instead of crashing a build."""
from __future__ import annotations

from typing import Any, Optional

_FN: Optional[Any] = None      # the latex2sympy callable, once resolved
_TRIED: bool = False           # have we attempted the import yet


def _loader() -> Optional[Any]:
    global _FN, _TRIED
    if not _TRIED:
        _TRIED = True
        try:                                   # the huggingface extended fork
            from latex2sympy2_extended import latex2sympy
            _FN = latex2sympy
        except Exception:                      # not installed → graceful
            _FN = None
    return _FN


def available() -> bool:
    """True iff a LaTeX→SymPy parser is importable."""
    return _loader() is not None


def to_sympy(latex: str) -> Optional[Any]:
    """Parse a LaTeX string to a SymPy object, or None (unavailable / unparseable)."""
    fn = _loader()
    if fn is None or not latex:
        return None
    try:
        return fn(latex)
    except Exception:
        return None
