r"""A table's row rule is not a fraction bar, and the operands say so.

T-0154. Calling a rule `fraction` does not merely build a wrong `\frac`: it
MERGES the band above the rule with the band below it. On 2312.11532 p7 — a
board page — the horizontal rule between two rows of Table 3 was classified
`fraction`, and the two rows came out as one line 83 units tall:

    'Codebook 106 money, profit, guarantee, hope, financial, ...Codebook 176
     life, today, time, economy, bank, ...'

`_rule_role` already refuses a wide rule two ways: a share of the page width
together with an em count (`>= 0.45 * page_width and >= 25 em`), and the reach
test at `> 12 em` (one operand must span the bar end to end). This rule
cleared neither — 0.38 of the page at 26 em, and a table's row DOES span its
rule end to end, which that guard's own comment says.

So the evidence is not the width. It is what the operands ARE. MEASURED by
spying on `_rule_role` over the 24 board-14 extracts, 140 rules classified
`fraction`, of which 50 have no mathematical glyph on either side of the bar:

    23.2 em  2312.11532 p7    'Codebook106money,profi / Codebook176life,today'
    20.3 em  2311.09533v3     'Bay,Alaska[3].Thewavew / ExamplefromASQA'
    18.5 em  RE4B-DE p559     'buggeroderDBIzuüberwac / 5DynamicBinaryInstrume'
    13.7 em  2311.09533v3     'ascaptured...Theworld / datawascapturedina1958'
    11.7 em  0864 p4          '10aaaab / 11bcccc'
    11.7 em  0864 p4          '5a5a5a / 6aaaab'
     7.2 em  2311.09533v3     'WithTTApriorunsupporte / ,a7.8strike-slipearthq'
     7.2 em  2311.09533v3     'to...priorunsupporteds / tencewasconfirmedin195'
     6.2 em  lib:69bc5c71b881 'https://iddp.is/ / ur Olaf Fridleifss'
    ------------------------------------------------------------------- gap
     2.0 em  lib:3c16fac66fdd 'qge„ / 4m'
     1.5 em  lib:3c16fac66fdd '@ / @xj'          (a partial derivative)
     1.2 em  1805.01788       'ai1 / ri1'
     0.5 em  and below        '1 / 2', '1 / e', '3 / 4'  — 30 of them
      ...    41 in all under 2.1 em

Above the gap: four table rules, two footnote separators, three more table
rules. Below it: forty-one real fractions whose operands are plain digits or
upright letters, which carry no maths font and so no mathematics. Nothing
lies between 2.0 and 6.2 em.

A SECOND TEST AT A LARGER WIDTH. Six more rules on 2312 p7 are the axis rules
of Figure 3's plots, with the tick labels under them: `k=1 / 100 200 300`, one
maths glyph above (the `=`) and none below, 12.7 em wide. They survive the
first test. Where the reach test already runs — `> 12 em` — a fraction bar can
be required to have mathematics on BOTH sides, because the digit-only
fractions above all live under 2.1 em. The one genuine wide display fraction
in the set keeps its role: lib:3fe71b4ef018 p328, 15.1 em, nine maths glyphs
above and five below.

STILL OPEN, and said rather than hidden: two of 0864 p4's four table rules
carry mathematics on ONE side (`X1X2X3X4Y / 11a11a`) at 11.7 em, so neither
test reaches them. That table stays partly merged.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

pytest.importorskip("pdfreader.docmodel_six")
from pdfreader.docmodel_six import GlyphNode, RuleNode, _rule_role
from pdfreader.texmap import UNKNOWN

SIZE = 10.0


def _g(x, baseline, text, family="text", glyphname=None):
    return GlyphNode(
        id="g", page=1, rect=(x, baseline, x + 5.0, baseline + SIZE),
        text=text, cid=ord(text[0]) if text else 0, glyphname=glyphname,
        fontname="NimbusRomNo9L-Regu", family=family, size=SIZE,
        tex=UNKNOWN, matrix=(1, 0, 0, 1, x, baseline))


def _rule(x0, width, y):
    return RuleNode(id="r", page=1, rect=(x0, y, x0 + width, y + 0.5))


def _row(x0, width, baseline, text, family="text"):
    """One row of glyphs spanning the bar end to end.

    TeX sets a fraction bar as wide as the wider operand, so `_is_own_row`
    requires the operand to be CONTAINED by the bar and the reach test
    requires one side to span it. A row laid out at a fixed pitch fails both
    on a wide bar, which is geometry, not the rule under test.
    """
    n = max(len(text), 1)
    step = (width - 5.0) / n if n > 1 else 0.0
    return [_g(x0 + step * i, baseline, ch, family=family)
            for i, ch in enumerate(text)]


def _role(width, above, below, *, y=100.0, page_width=600.0, family="text"):
    """`_rule_role` for a bar of `width`, with `above` over and `below` under."""
    rule = _rule(50.0, width, y)
    glyphs = (_row(50.0, width, y + 4.0, above, family=family)
              + _row(50.0, width, y - 6.0, below, family=family))
    return _rule_role(rule, glyphs, SIZE, (), page_width)


def _role_math(width, above, below, **kw):
    return _role(width, above, below, family="math-italic", **kw)


def test_a_small_bar_over_plain_digits_is_still_a_fraction():
    """41 of the 50 measured: `1/2`, `1/e`, `3/4`, `ai1/ri1`. Plain digits
    and upright letters carry no maths font, so a content test alone would
    destroy every one of them."""
    assert _role(5.0, "1", "2") == "fraction"
    assert _role(12.0, "ai1", "ri1") == "fraction"
    assert _role(20.0, "qge", "4m") == "fraction"


def test_a_wide_bar_over_plain_prose_is_not_a_fraction():
    """2312 p7's table rule, and eight more like it."""
    assert _role(232.0, "Codebook106money", "Codebook176life") != "fraction"
    assert _role(117.0, "10aaaab", "11bcccc") != "fraction"
    assert _role(62.0, "https://iddp.is/", "urOlafFridleifss") != "fraction"


def test_a_wide_bar_over_mathematics_is_a_fraction():
    """lib:3fe71b4ef018 p328's display fraction, 15.1 em with nine maths
    glyphs above and five below. The test must not cost this one."""
    assert _role_math(151.0, "1+14a2eTrQ22N2", "Mir4N2M1") == "fraction"


def test_a_wide_bar_with_mathematics_on_one_side_only_is_not_a_fraction():
    """Figure 3's six axis rules on 2312 p7: `k=1` above, tick labels below,
    12.7 em. Past `_PLAIN_OPERAND_EM` a fraction has operands on both sides,
    and these have one."""
    rule = _rule(50.0, 127.0, 100.0)
    glyphs = (_row(50.0, 127.0, 104.0, "k=1", family="math-italic")
              + _row(50.0, 127.0, 94.0, "100200300"))
    assert _rule_role(rule, glyphs, SIZE, (), 600.0) != "fraction"


def test_the_half_merged_table_rule_is_caught_too():
    """0864 p4's two surviving table rules, 11.7 em, one side the running
    head and the other the table's own `X1 X2 X3 X4 Y` header in maths
    italic. Under 12 em, so the earlier both-sides test at that width did
    not reach them; the boundary is `_PLAIN_OPERAND_EM` for both halves of
    the rule, which is what the 4-to-12 em band measures.

    MEASURED, all nine rules the board set classifies `fraction` between 4
    and 12 em: seven defects (four on 0864 p4, two table rules on
    2311.09533v3, one footnote rule on lib:69bc5c71b881) and two genuine
    fractions, `DCG@k(ρ∗) / DCG@k(ρ)` at 5.1 em and `2rli−1 / log2(j+1)` at
    4.1 em. BOTH genuine ones carry mathematics on both sides; both
    maths-on-one-side cases are 0864's table rules."""
    rule = _rule(50.0, 117.0, 100.0)
    glyphs = (_row(50.0, 117.0, 104.0, "X1X2X3X4Y", family="math-italic")
              + _row(50.0, 117.0, 94.0, "11a11a"))
    assert _rule_role(rule, glyphs, SIZE, (), 600.0) != "fraction"
    rule2 = _rule(50.0, 117.0, 100.0)
    glyphs2 = (_row(50.0, 117.0, 104.0, "ftheTwentyEighthInterna")
               + _row(50.0, 117.0, 94.0, "X1X2X3X4Y", family="math-italic"))
    assert _rule_role(rule2, glyphs2, SIZE, (), 600.0) != "fraction"


def test_a_genuine_fraction_in_that_band_keeps_its_role():
    """The two the band actually holds, at 5.1 em and 4.1 em. If this test
    ever goes red the boundary has eaten real mathematics."""
    assert _role_math(51.0, "DCGk", "DCGk") == "fraction"
    assert _role_math(41.0, "2rli1", "log2j1") == "fraction"


def test_the_page_share_guard_still_answers_first():
    """A rule over half the page and 25 em wide is a table rule whatever
    sits around it — the guard that was already there."""
    rule = _rule(50.0, 300.0, 100.0)
    glyphs = (_row(50.0, 300.0, 104.0, "abc", family="math-italic")
              + _row(50.0, 300.0, 94.0, "def", family="math-italic"))
    assert _rule_role(rule, glyphs, SIZE, (), 600.0) == "table"
