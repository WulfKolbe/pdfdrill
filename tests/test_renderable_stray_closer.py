r"""MathPix glues a stray environment closer onto display math that ends a list:

    \[ (A \vee B)^{\prime}=-B \vee A . \] \end{itemize}

The equation is intact; the `\end{itemize}` belongs to prose that was cut away.
Left in place it puts a `\]` MID-STRING, and renderable()'s delimiter gate then
refuses the whole row — 24 of 0902.0431's 31 unrendered equations, at
confidences up to 1.000, blanked to "(not rendered)" for a defect that is not
in the mathematics at all.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.report_tex import renderable


def test_stray_trailing_closer_is_dropped():
    got = renderable(r"\[ (A \vee B)^{\prime}=-B \vee A . \] \end{itemize}")
    assert got == r"(A \vee B)^{\prime}=-B \vee A ."


def test_several_stray_closers():
    got = renderable(r"\[ x=1 \] \end{itemize} \end{enumerate}")
    assert got == "x=1"


def test_a_genuine_environment_keeps_its_closer():
    """The converse: an environment OPENED inside the math must survive, or the
    fix would silently truncate every aligned/array equation in the corpus."""
    src = r"\begin{aligned} a &= b \\ c &= d \end{aligned}"
    assert renderable(src) == src


def test_nested_genuine_environment_survives():
    src = r"\left(\begin{array}{cc} 1 & 2 \\ 3 & 4 \end{array}\right)"
    assert renderable(src) == src


def test_unbalanced_environment_is_still_refused():
    """Dropping a stray closer must not turn the balance gate off: a value that
    OPENS an environment and never closes it is still unrenderable."""
    assert renderable(r"\frac{x}{y} \begin{array}{c} 1") == ""


def test_closer_without_opener_mid_string_still_refused():
    """Only a TRAILING stray closer is dropped. One in the middle still means
    the value is malformed and must not be fed to xelatex."""
    assert renderable(r"x \end{itemize} + y") == ""


def test_real_0902_row():
    """The highest-confidence member of the affected set (EQ0467-shaped)."""
    src = (r"\[ \operatorname{dim}_{C}\left(\mathfrak{e}_{6}{ }^{C}\right)"
           r"=52+26=78 . \] \end{itemize}")
    out = renderable(src)
    assert out and r"\]" not in out and r"\end{itemize}" not in out


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
