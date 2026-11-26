"""
Inside maths a character with a LaTeX command is written as the command
(contracts/reading.md §7; owner, 2026-11-25: "inside a math expression the
translation to the LaTeX is required").

A maths span that cannot be typed is written from its glyphs' characters, and
that left `⊕`, `−`, `α`, `∗`, `⊃`, `′` inside `$...$`: 17 non-ASCII characters
in the 572 maths spans of the 24 born board pages, 1 after this (a lone
macron, which has no command without its base and is counted).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader.docmodel_six import _maths_chars


def test_the_contract_examples_are_commands():
    cases = {"ρ": r"\rho", "Γ": r"\Gamma", "µ": r"\mu", "∆": r"\Delta",
             "−": "-", "≤": r"\leq", "∈": r"\in", "′": r"^{\prime}",
             "·": r"\cdot", "∞": r"\infty", "⊕": r"\oplus", "×": r"\times"}
    for ch, tex in cases.items():
        assert _maths_chars(ch) == tex, ch


def test_a_command_does_not_run_into_a_letter():
    assert _maths_chars("αe") == r"\alpha e"


def test_greek_capitals_without_a_command_are_latin_and_omicron_is_o():
    assert _maths_chars("Α") == "A" and _maths_chars("ο") == "o"


def test_a_character_without_a_command_stays():
    assert _maths_chars("�") == "�" and _maths_chars("¯") == "¯"
