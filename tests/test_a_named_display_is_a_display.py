r"""
B14, 1805.01788 p3: `DCG@k(r) = \sum_{i=1}^k \frac{2^{r(i)}-1}{\log_2(i+1)}`
is a display (its sum is the display cut), but the name is set in TEXT
italic, so the line read as prose with an inline formula and the sum and
its fraction came out at text size. A short text-italic name before one
maths span, on a line with a display-cut operator, is one display with the
name as `\mathit`. Judge (pin 8a67b8a) 1805 p3: 0.0033 -> 0.0002.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")
from pdfreader.texmap import TexToken

TEXT = r"\textit{DCG}@\textit{k} $(r ) = \sum\limits_{i =1}^{k} \frac{2^{r (i )} - 1}{\log_{2} (i + 1)}$"


def _line(display_cut=True):
    name = "summationdisplay.1" if display_cut else "summationtext"
    g = SimpleNamespace(glyphname=name, fontname="ABC+txexs", size=9.96,
                        rect=(0.0, 0.0, 14.0, 14.0),
                        tex=TexToken(r"\sum", "bigop", None, "corpus"))
    return SimpleNamespace(glyphs=[g])


def test_the_named_line_becomes_one_display():
    out = D._display_by_operator(_line(), TEXT)
    assert out.startswith("\\[\n" + r"\mathit{DCG}@\mathit{k} (r ) = \sum"), out
    assert "$" not in out and r"\textit" not in out


def test_without_a_display_cut_it_stays_inline():
    assert D._display_by_operator(_line(False), TEXT) == TEXT


def test_prose_does_not_match():
    t = r"we have $x = \sum_i a_i$"
    assert D._display_by_operator(_line(), t) == t
