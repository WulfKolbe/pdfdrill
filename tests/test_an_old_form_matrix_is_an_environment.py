r"""`\pmatrix{a\cr b}` is the plain-TeX form, and amsmath refuses it.

T-0156. amsmath answers it with "Package amsmath Error: Old form `\pmatrix'
should be \begin{pmatrix}" and stops. arxiv.0912.2444 writes three of each:

    \pmatrix{\lfloor cN \rfloor\cr\lfloor cN_2\rfloor}
    \cases{ H(\mathbb{G}_0)+\beta, &\quad if … \cr H_{m+1}+\beta, &\quad …}

6 errors for the forms and 9 more for the `\cr` inside them. MEASURED: all
nine `\cr` in that document sit inside those six groups, so this is ONE
construct and not the two classes the message classes suggested.

THE ROW SEPARATOR GOES WITH THE FORM. Plain TeX breaks a row with `\cr` and
the amsmath environment with `\\`, so a conversion that kept `\cr` would trade
one error for another.

WHAT IS DELIBERATELY NOT CONVERTED, each for a stated reason:

  * `\matrix`, `\eqalign`, `\atop` — zero occurrences in the corpus. A name
    added without one is a guess.
  * `\over` — 207 occurrences on that same document and NOT ONE error. amsmath
    accepts it. Rewriting it to `\frac` means parsing its two sides, which is a
    different job with its own failure mode, and nothing is asking for it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

P = pytest.importorskip("docops.projectors.latex_pipeline")


@pytest.mark.parametrize("src,want", [
    (r"\pmatrix{a\cr b}", r"\begin{pmatrix}a\\ b\end{pmatrix}"),
    (r"\cases{a&x\cr b&y}", r"\begin{cases}a&x\\ b&y\end{cases}"),
])
def test_the_old_form_becomes_the_environment(src, want):
    assert P._plain_tex_matrices(src) == want


def test_the_row_separator_goes_with_the_form():
    r"""`\cr` is plain TeX's row break and `\\` is the environment's; keeping
    `\cr` would trade one error for another."""
    out = P._plain_tex_matrices(r"\pmatrix{1&2\cr3&4}")
    assert "\\cr" not in out
    assert out.count("\\\\") == 1


def test_a_trailing_separator_is_dropped():
    r"""`\cases{a\cr b\cr}` would end in an empty row, which amsmath reports as
    a misplaced `\noalign`."""
    out = P._plain_tex_matrices(r"\cases{a\cr b\cr}")
    assert out == r"\begin{cases}a\\ b\end{cases}"
    assert not out.replace("\\end{cases}", "").rstrip().endswith("\\\\")


def test_it_converts_in_place_and_leaves_the_rest():
    out = P._plain_tex_matrices(r"x + \pmatrix{1&2\cr3&4} + y")
    assert out == r"x + \begin{pmatrix}1&2\\3&4\end{pmatrix} + y"


def test_a_nested_one_is_converted_too():
    out = P._plain_tex_matrices(r"\pmatrix{\pmatrix{a\cr b}\cr c}")
    assert out.count("\\begin{pmatrix}") == 2
    assert out.count("\\end{pmatrix}") == 2
    assert "\\cr" not in out


@pytest.mark.parametrize("src", [
    r"a \over 2",
    r"\matrix{a\cr b}",
    r"\eqalign{a&=b\cr}",
    r"{a \atop b}",
    r"no matrices at all",
])
def test_what_is_not_converted_stays_untouched(src):
    """`\\over` is accepted by amsmath (207 uses, 0 errors); the other three
    have no occurrence in the corpus to measure against."""
    assert P._plain_tex_matrices(src) == src


def test_an_unbalanced_group_is_left_alone():
    r"""A `\pmatrix{` whose brace never closes is a reading that has gone
    wrong; rewriting it would invent an `\end{pmatrix}` for content that has no
    end. It is left for the crop to defer."""
    src = r"\pmatrix{a\cr b"
    assert P._plain_tex_matrices(src) == src


def test_sanitize_math_applies_it():
    """The rule has to be on the path the projector actually uses."""
    out = P.sanitize_math(r"\pmatrix{a\cr b}")
    assert "\\begin{pmatrix}" in out
    assert "\\cr" not in out
