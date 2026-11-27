r"""
B13, lib:c57ac038ae5f p293: vectors set in MathTime's bold maths italic
(MTMIB). Read as plain `r` they were 90 style findings, and the narrower `r`
moved each `r_k^T`'s subscript a point left, where the judge no longer
paired it. A letter from a bold maths italic (cmmib, MTMIB) is
`\boldsymbol{...}`. Judge (pin 8a67b8a) c57a p293: 0.0101 -> 0.0042,
formulas 3/6 -> 5/6.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import texmap as T


def _p(font, name):
    return T.project(T.family_of(font), name, fontname=font).latex


def test_mathtime_bold_italic_letter():
    assert _p("PbjxxxMTMIB", "r") == r"\boldsymbol{r}"


def test_cm_bold_italic_greek():
    assert _p("ABC+CMMIB10", "alpha") == r"\boldsymbol{\alpha}"


def test_plain_maths_italic_stays_plain():
    assert _p("ABC+CMMI10", "r") == "r"
    assert _p("ABC+MTMI", "r") == "r"


def test_punctuation_is_not_bolded():
    assert _p("PbjxxxMTMIB", "comma") == ","
