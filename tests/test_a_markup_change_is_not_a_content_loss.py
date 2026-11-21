r"""The content counter's own test: markup is not content.

Every reading change is gated on "zero content characters lost", and the
counter behind that was wrong THREE TIMES IN ONE DAY — each time reporting a
loss where structure had been GAINED, and each time caught only by listing
the characters instead of trusting the total. Each of the three is a test
below, with the real before/after that fooled it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

CC = pytest.importorskip("mathgold.contentchars")


def test_a_command_standing_for_a_character_is_not_a_loss():
    r"""`α0 = 12` -> `\alpha_{0} = \frac{1}{2}`: the α is still there."""
    lost, _ = CC.content_delta("α0 = 12", r"\alpha_{0} = \frac{1}{2}")
    assert lost == 0


def test_the_greek_letters_that_were_counted_lost():
    r"""The five from the real board run: θ ϕ ω Λ α."""
    for ch, cmd in (("θ", r"\theta"), ("ϕ", r"\phi"), ("ω", r"\omega"),
                    ("Λ", r"\Lambda"), ("α", r"\alpha")):
        lost, _ = CC.content_delta(ch, cmd)
        assert lost == 0, ch


def test_a_structural_commands_argument_is_not_content():
    r"""`\documentclass{article}\begin{document}` carries no words."""
    assert CC.content_chars(
        r"\documentclass{article}\begin{document}\end{document}") == {}


def test_an_environment_name_is_not_content():
    r"""`\begin{array}{c}` -> `\begin{smallmatrix}`: 60 letters of "array"
    and the `{c}` spec against "smallmatrix"'s, and no content either way."""
    before = r"\left[\begin{array}{c}1 \\ -1/2\end{array}\right]"
    after = r"\left[\begin{smallmatrix}1 \\ -1/2\end{smallmatrix}\right]"
    assert CC.content_delta(before, after) == (0, 0)


def test_a_real_loss_is_still_reported():
    """The counter must not be so forgiving that it cannot fail."""
    lost, gained = CC.content_delta("alpha 1 = 1/2", "alpha 1 =")
    assert lost == 2 and gained == 0       # the `1` and the `2`


def test_the_alpha_one_loss_that_is_still_open():
    r"""p293's real defect: `\alpha_{1}=\frac{1}{2}` against `α1 = ,`."""
    lost, _ = CC.content_delta(r"\alpha_{1}=\frac{1}{2}", "α1 = ,")
    assert lost == 2                       # the `1` and the `2` of the value
