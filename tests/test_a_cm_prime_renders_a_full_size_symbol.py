r"""The CM prime, and the two wrong cures that were tried for it first.

CMSY8 sets a prime whose `text` is already U+2032. `_glyph_text` (b7996491)
preferred `g.tex.latex` for every maths-family glyph, so it read `\prime` --
a full-size symbol on the baseline where the page draws a small raised mark,
and the judge flagged all six on board page 1511.08771 p2709.

IT IS NOW RIGHT, through the rule in
`test_a_minus_sign_is_not_downgraded_to_a_hyphen.py`: a glyph whose own
character is already correct and non-ASCII keeps it, unless its FONT is one
that misnames its slots. U+2032 is correct and CMSY names its slots, so the
character stays. Measured: 1511.08771 p2709 0.0209 -> 0.0186, flagged 12 -> 6.

TWO CURES WERE TRIED BEFORE THAT AND BOTH WERE WORSE. They are kept here with
their numbers so neither is tried again.

1. NARROW THE PREFERENCE TO THE UNTRUSTED FONTS ALONE (`TeX-math[abx]`), on
   the reasoning that Computer Modern names its slots correctly.

       1511.08771 p2709   state-8 code 0.0225 / broad 0.0209 / narrowed 0.0225

   Half right, and that half is now in the rule. But as the WHOLE test it is
   false: CMSY and CMMI are misnamed under StandardEncoding too, and on
   0864 p4 the broad rule corrects 94 readings -- `f` -> `\{`, `g` -> `\}`,
   `;` -> `,`, `:` -> `.`, `X` -> `\mathcal{X}`. Narrowing by font alone
   discards 88 correct corrections to remove 6 wrong ones.

2. MAP THE PRIME TO THE SCRIPT IT IS, `^{\prime}`, in `_MATH_SYMBOL` and the
   codepoint table.

       0864 p4            0.1676 -> 0.1676   (no change at all)
       1511.08771 p2709   0.0209 -> 0.0613   (paired 2497 -> 2401, flagged 20)

   A `^{...}` written into the reading's own text attaches to whatever
   precedes it. It also refuted the idea that the primes were what cost
   0864 p4 its seven characters -- that was U+2212 read as an ASCII hyphen,
   on two leaf lines of the judged page.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm  # noqa: E402
from pdfreader import texmap  # noqa: E402


class _G:
    def __init__(self, text, latex, family, fontname):
        self.text = text
        self.family = family
        self.fontname = fontname
        self.tex = texmap.TexToken(latex, "atom", None, "corpus")


def test_a_cm_prime_keeps_the_character_the_font_named_correctly():
    assert dm._glyph_text(
        _G("′", r"\prime", "math-symbol", "QRZVWS+CMSY8")) == "′"


def test_a_prime_encoded_as_its_standard_name_still_takes_the_field():
    """0864 p4 sets the same mark as CMSY7 slot 48, reported as `0`. ASCII,
    so it is the misnamed case and the correction stands."""
    assert dm._glyph_text(
        _G("0", r"\prime", "math-symbol", "QRZVWS+CMSY7")) == r"\prime"


def test_the_mathabx_case_the_broad_rule_exists_for_still_holds():
    assert dm._glyph_text(_G("p", "(", "math-symbol", "TeX-matha12")) == "("


def test_the_prime_is_still_a_baseline_symbol_in_the_table():
    """Cure 2 is NOT in the tables: `^{...}` in a reading's text is not inert."""
    assert texmap.project("math-symbol", "prime").latex == r"\prime"
