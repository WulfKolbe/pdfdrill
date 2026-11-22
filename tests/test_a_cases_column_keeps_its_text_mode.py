r"""Plain TeX's `\cases` and amsmath's `cases` differ in MODE, not only spelling.

T-0156, requirement 1, second step.

An earlier change rewrote plain-TeX `\pmatrix{…}` and `\cases{…}` into the
amsmath environments, because amsmath HALTS on the old forms ("Old form
`\pmatrix' should be \begin{pmatrix}"). That was right and it is kept.

BUT THE TWO FORMS DIFFER IN MORE THAN SPELLING. Plain TeX sets the column
after `&` in TEXT mode; amsmath's `cases` sets it in MATH mode. So an author
who writes

    \cases{ H(\G_0)+\beta, &\quad if $i\stackrel{0}{\not\sim} k$; \cr …}

is CORRECT — the `$…$` opens maths inside a text column — and the same row
inside `\begin{cases}` toggles maths OFF, leaving `k$;` in text mode.
xelatex answers "Missing $ inserted", three times for that one row.

So the bug was created by a fix, and the author was never wrong.

MEASURED on the eight e-prints: 24 of 146 errors were `Missing $ inserted`;
arxiv.0912.2444, which writes three `\cases` groups, carried 18 of them.
After this, that document goes 36 -> 18 and the total 113 -> 95, with every
content column identical. The remaining 5 are a DIFFERENT cause — an
`algorithmic` body (`\gets$ weights as in \cref{…}`) and a citation key —
and are not claimed here.

RESTORED, NOT REWRITTEN. Wrapping the column in `\text{…}` gives back the
mode the author wrote for, and their own `$…$` stays valid INSIDE it, so
nothing is dropped and no mathematics is reinterpreted. `\quad` and its
relatives stay OUTSIDE the box, where they are spacing rather than letters.
"""
from docops.projectors.latex_pipeline import _plain_tex_matrices as convert


def test_the_second_column_regains_text_mode():
    out = convert(r"\cases{ A, &\quad if $x>0$; \cr B, &\quad if $x\le0$ \cr}")
    assert r"\text{if $x>0$;}" in out
    assert r"\text{if $x\le0$}" in out


def test_the_spacing_stays_outside_the_text_box():
    r"""`\quad` inside `\text{}` would be set as the word "quad"."""
    out = convert(r"\cases{ A, &\quad if $x>0$ \cr}")
    assert r"&\quad \text{" in out


def test_the_authors_own_maths_survives_inside():
    r"""`$…$` is valid inside `\text{}`; the row is restored, not rewritten."""
    out = convert(r"\cases{ A, &\quad if $i\stackrel{0}{\not\sim} k$; \cr}")
    assert r"$i\stackrel{0}{\not\sim} k$" in out


def test_a_column_with_no_maths_is_left_alone():
    """Already what amsmath expects."""
    out = convert(r"\cases{ A, & x>0 \cr B, & x\le0 \cr}")
    assert r"\text{" not in out


def test_a_pmatrix_column_is_untouched():
    """Only `\cases` has the text-mode column; pmatrix never did."""
    out = convert(r"\pmatrix{a & $b$ \cr c & d}")
    assert r"\text{" not in out


def test_the_environment_conversion_still_happens():
    """The fix this builds on is kept: amsmath halts on the old forms."""
    out = convert(r"\cases{ A, & x \cr B, & y \cr}")
    assert out.startswith(r"\begin{cases}") and out.endswith(r"\end{cases}")
    assert r"\cr" not in out


def test_a_row_without_an_ampersand_is_left_alone():
    out = convert(r"\cases{ $x$ \cr $y$ \cr}")
    assert r"\text{" not in out
