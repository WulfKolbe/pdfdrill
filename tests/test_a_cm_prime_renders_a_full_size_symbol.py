r"""A KNOWN, MEASURED DEFECT, kept xfail so it is not "fixed" blindly.

`_glyph_text` (b7996491) prefers `g.tex.latex` for every maths-family glyph.
For `TeX-matha` that is right and necessary -- the font names its slots `p` `q`
`r` `s` while drawing `(` `)` `[` `]`, and 67 glyphs on lib:c9daf79960c3 p68
depend on it. But `math-symbol` is also Computer Modern's family, and CMSY8
names its slots CORRECTLY: its U+2032 prime now reads `\prime`, a full-size
symbol on the baseline, where the page draws a small raised one.

TWO CURES WERE TRIED AND MEASURED ON THE BOARD, 2026-11-18, one judge. Both
are worse than the defect. Do not try either again without reading this.

1. NARROW THE RULE to the fonts whose names are untrusted (`TeX-math[abx]`),
   on the reasoning that Computer Modern names its slots correctly.

       1511.08771 p2709   state-8 code 0.0225 / broad 0.0209 / narrowed 0.0225

   THE REASONING IS FALSE. CMSY and CMMI are misnamed under StandardEncoding
   too -- on 0864 p4 the broad rule corrects 94 readings, among them `f` -> `\{`,
   `g` -> `\}`, `;` -> `,`, `:` -> `.`, `X` -> `\mathcal{X}`. Narrowing would
   have thrown 88 correct corrections away to remove 6 wrong ones. The broad
   rule also pairs ten glyphs on 1511.08771 p2709 that the reader otherwise
   misses, which is worth more than the six primes cost.

2. MAP THE PRIME TO THE SCRIPT IT IS, `^{\prime}`, in `_MATH_SYMBOL` and the
   codepoint table.

       0864 p4            0.1676 -> 0.1676   (no change at all)
       1511.08771 p2709   0.0209 -> 0.0613   (paired 2497 -> 2401, flagged 20)
       lib:c9daf79960c3   0.0147 -> 0.0147

   A `^{...}` written into the reading's own text is not inert: it attaches to
   whatever precedes it, and the page lost 96 pairings. It also did NOT move
   0864 p4, which refutes the idea that the primes are what costs that page its
   seven glyphs. That cause is still unknown.

So the defect is real, both cures are worse, and the cause of 0864 p4's loss is
NOT this.

Recorded in drillgroup results/board-regressions-nine.md.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader import texmap


class _G:
    def __init__(self, text, latex, family, fontname):
        self.text = text
        self.family = family
        self.fontname = fontname
        self.tex = texmap.TexToken(latex, "atom", None, "corpus")


@pytest.mark.xfail(reason="measured: narrowing costs more board residual than "
                          "the six wrong primes do (see this file's docstring)",
                   strict=True)
def test_a_cm_prime_keeps_the_character_the_font_named_correctly():
    assert dm._glyph_text(
        _G("′", r"\prime", "math-symbol", "QRZVWS+CMSY8")) == "′"


def test_the_mathabx_case_the_broad_rule_exists_for_still_holds():
    """Whatever is done about the prime, this must not break."""
    assert dm._glyph_text(_G("p", "(", "math-symbol", "TeX-matha12")) == "("
