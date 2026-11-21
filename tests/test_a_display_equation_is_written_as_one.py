r"""A display equation is written `\[...\]`, not `$...$`.

T-0154/T-0156. Every maths span was written `$...$` — inline maths — whatever
the line's type. So a line the classifier established as a DISPLAY equation
reached the reading in text style, and a `\frac` inside it is set small with
its bar low, where the page sets it large with the bar high.

MEASURED on lib:6d90e8d27b8b p174, from the judge's rule findings: four
fraction bars the ink draws at y=1987 are drawn by our LaTeX at y=1970 (x2)
and y=2001 (x2) — 17 above and 14 below — so each one counts twice, once
missing and once invented. The same shape appears on L3 (ink 638, ours 633)
and L5 (ink 959, ours 943).

The CONTENT is not in question. Our line and MathPix's are the same equation:

    ours     `$\int \frac{\mathrm{d}x}{x} = \int \frac{t^{2}}{t+1} ...$`
    MathPix  `\[ \int \frac{\mathrm{d} x}{x}=\int \frac{t^{2}}{t+1} ... \]`

Same fractions, same order, same structure; the delimiters differ and so does
the style they select.

SCOPE, over the 24 board-14 extracts: **128 of 131 lines typed `math` or
`equation` are written with inline delimiters** — lib:c57ac038ae5f p293 20,
0864 p4 18, p174 18, lib:1a36bfe66b9c p154 16, 2103.01507 p118 13, and six
more pages. It is the whole class, not one page's accident.

ONLY WHEN EVERY SPAN IS MATHS. A line that mixes prose and maths is inline
maths inside a sentence and keeps `$...$` per span: wrapping the whole line
in `\[...\]` would set its words in maths mode.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")


def test_a_whole_line_of_maths_becomes_a_display():
    assert D._as_display("$x = 1$", "math") == "\\[\nx = 1\n\\]"
    assert D._as_display("$x = 1$", "equation") == "\\[\nx = 1\n\\]"


def test_a_line_that_is_not_maths_is_untouched():
    assert D._as_display("just words", "text") == "just words"
    assert D._as_display("$x$ and words", "text") == "$x$ and words"


def test_a_mixed_line_keeps_its_inline_spans():
    """A sentence with maths in it is not a display equation, and wrapping
    the whole line would set its words in maths mode."""
    assert D._as_display("Let $x$ be", "math") == "Let $x$ be"
    assert D._as_display("$a$ or $b$", "math") == "$a$ or $b$"


def test_an_empty_or_delimiterless_line_is_untouched():
    for s in ("", "   ", "x = 1"):
        assert D._as_display(s, "math") == s


def test_a_display_is_not_wrapped_twice():
    assert D._as_display("\\[\nx = 1\n\\]", "math") == "\\[\nx = 1\n\\]"
