r"""Nested fractions on a MathTime-style page (lib:7e9f02b4f39f p287).

`\frac{1-\frac{-a^2+b^2+c^2}{2bc}}{1+\frac{-a^2+b^2+c^2}{2bc}}`:
- the inner bars (6 em) have Latin variables in the TEXT italic on both
  sides, none `is_math`, so they were taken for separators;
- two outer bars were given to rows that a later merge emptied, and lost.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

dm = pytest.importorskip("pdfreader.docmodel_six")
texmap = pytest.importorskip("pdfreader.texmap")
_N = [0]
ITALIC, ROMAN, SYM = "X+TimesTen-Italic", "X+TimesTen-Roman", "X+MTSYN"


def _g(text, x0, base, font, family, latex=None, w=5.0, size=10.0):
    _N[0] += 1
    tex = (texmap.TexToken(latex, "atom", None, "corpus") if latex
           else texmap.UNKNOWN)
    return dm.GlyphNode(
        id="g%d" % _N[0], page=1, rect=(x0, base - 2, x0 + w, base + size - 2),
        text=text, cid=0, glyphname=None, fontname=font, family=family,
        size=size, tex=tex, matrix=(size, 0, 0, size, x0, base))


def _bar(x0, x1, y):
    return dm.RuleNode(id="r", page=1, rect=(x0, y, x1, y))


def _seq(spec, x, base, gap=1.5):
    out = []
    for t in spec:
        if t in "+−":
            out.append(_g(t, x, base, SYM, "math-symbol", "+" if t == "+" else "-"))
        elif t.isdigit():
            out.append(_g(t, x, base, ROMAN, "text"))
        else:
            out.append(_g(t, x, base, ITALIC, "text"))
        x += 5.0 + gap
    return out


def _role(bar, glyphs):
    return dm._rule_role(bar, glyphs, 10.0, [bar], page_width=430.0)


def test_a_6_em_bar_over_text_italic_maths_is_a_fraction():
    bar = _bar(297.2, 357.2, 235.7)
    num = _seq("−a+b+c", 298.0, 240.2)
    den = _seq("2bc", 315.0, 227.0, gap=0.0)
    assert _role(bar, num + den) == "fraction"


def test_a_wide_table_rule_over_single_letters_stays_a_separator():
    # 0864 p4's set-cover table: `10 a a a a b` over `11 b c c c c`
    bar = _bar(100.0, 217.0, 300.0)
    up = _seq("10aaaab", 101.0, 304.0, gap=12.0)
    dn = _seq("11bcccc", 101.0, 291.0, gap=12.0)
    assert _role(bar, up + dn) == "separator"


def test_a_6_em_rule_with_words_stays_a_separator():
    bar = _bar(100.0, 160.0, 300.0)
    up = _seq("the", 101.0, 304.0, gap=0.0)
    dn = _seq("2bc", 110.0, 291.0, gap=0.0)
    assert _role(bar, up + dn) == "separator"
