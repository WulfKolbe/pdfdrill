r"""A display row is several independent terms, and each assembles on its own.

T-0154. `lib:c57ac038ae5f` p293 sets four terms on one row:

    t_0 = 3[1 / -1/2],   \alpha_0 = 1/2,   x_1 = -4^{-1}[1/2],   r_1 = ...

MEASURED before this change, on reader rows 27 and 28 of that page:

    to_tex(the whole row)        -> REFUSED, both rows
    to_tex(the \alpha_0 term)    -> `\alpha_{0} = \frac{1}{2} ,`   CORRECT
    over both rows               -> 1 of 8 terms assembles alone

So the assembler already does this mathematics. It refuses only because the
whole row arrives at once, and one refusal then flattens every term in the row
to its glyph text in x order — losing `t_0`'s subscript, `\alpha_0`'s fraction
and `-4^{-1}`'s exponent together.

A TERM BOUNDARY IS A SEPARATOR ON THE ROW'S OWN BASELINE, and outside every
rule. A comma inside a fraction (`A_{i,j}`, a vector `[1, 2]`) is not a
boundary: it sits off the dominant baseline, or within the x-span of the rule
that binds it. Both tests below pin that distinction, because getting it wrong
splits an expression in half rather than between two expressions.

This is the partitioner only. It is necessary and NOT sufficient: 6 of p293's
8 terms hold a stacked column vector, which needs the Above/Below relation and
an array, and the 7th is `\alpha_1`, whose operands lie on other rows. Both are
named in `docs/superpowers/specs/2026-11-21-the-multi-baseline-row-design.md`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

S = pytest.importorskip("pdfreader.structure")
D = pytest.importorskip("pdfreader.docmodel_six")
from pdfreader.texmap import UNKNOWN


def _g(x0, text, baseline=100.0, size=10.0):
    return D.GlyphNode(
        id="g%s" % x0, page=1,
        rect=(x0, baseline - size, x0 + size * 0.5, baseline),
        text=text, cid=0, glyphname=None, fontname="ABC+CMR10",
        family="math-italic", size=size, tex=UNKNOWN,
        matrix=(size, 0, 0, size, x0, baseline))


def _rule(x0, x1, y=95.0, role="fraction"):
    return D.RuleNode(id="r%s" % x0, page=1, rect=(x0, y, x1, y + 0.4),
                      role=role)


def test_a_row_of_two_terms_splits_at_the_comma():
    gs = [_g(10, "a"), _g(15, "="), _g(20, "1"), _g(25, ","),
          _g(30, "b"), _g(35, "="), _g(40, "2")]
    out = S.split_terms(gs, [])
    assert len(out) == 2
    assert "".join(g.text for g in out[0]) == "a=1,"
    assert "".join(g.text for g in out[1]) == "b=2"


def test_a_row_with_no_separator_is_one_term():
    gs = [_g(10, "a"), _g(15, "="), _g(20, "1")]
    assert len(S.split_terms(gs, [])) == 1


def test_a_comma_off_the_baseline_is_not_a_boundary():
    r"""`A_{i,j}` — the comma is a subscript, not a separator."""
    gs = [_g(10, "A"), _g(15, "i", baseline=103.0, size=7.0),
          _g(19, ",", baseline=103.0, size=7.0),
          _g(22, "j", baseline=103.0, size=7.0)]
    assert len(S.split_terms(gs, [])) == 1


def test_a_comma_inside_a_fraction_is_not_a_boundary():
    """A separator within a rule's x-span belongs to what the rule binds."""
    gs = [_g(10, "1"), _g(14, ","), _g(18, "2"), _g(10, "3", baseline=108.0)]
    assert len(S.split_terms(gs, [_rule(8, 22)])) == 1


def test_an_empty_row_has_no_terms():
    assert S.split_terms([], []) == []
