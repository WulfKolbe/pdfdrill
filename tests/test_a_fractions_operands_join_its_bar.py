r"""A fraction's numerator and denominator belong to the row its bar sits in.

T-0154, rule 4. `lib:c57ac038ae5f` p293 writes `α1 = ,` — the VALUE IS LOST,
against MathPix's and reader B's `\alpha_{1}=\frac{1}{2}`.

MEASURED, the three parts of that one fraction on three different reader rows:

    row 28   `α1 =` and the `,`      baseline 71.2    + the bar, y 73.5
    row 29   `1`  the numerator      baseline 78.1
    row 30   `2`  the denominator    baseline 64.1

`_group_lines` folds a row into its neighbour only when the row is CLEARLY
SMALLER (`s_size < 0.85 * o_size`) — a script. A display fraction's operands
are FULL SIZE, 10.0 against the row's 10.0, so they were never folded. With no
glyph above or below it, `_rule_role` then called the bar an `overline` and the
merge produced nothing at all.

α0 on the row above survives only because its `1`, `2` and bar happened to
land on one row, where `to_tex` assembles `\alpha_{0} = \frac{1}{2} ,`
correctly.

WHY THIS COMES NOW AND NOT EARLIER. `_group_lines` records two folds that
measured worse and were reverted, both because `_attach_scripts` could not
consume the result: "The rows are right and the pass that consumes them is
not." Folding α1's operands in before the consumer existed would have turned
"lost" into "flattened" — which is what α0 showed as `α0 = 12` until the
partitioner (262e2c9b) and the array pass (7de82d7a) landed. The consumer is
in, so the fold can follow.

THE BAR'S X-SPAN IS THE EVIDENCE, AND IT MUST BE STRICT. A row ENTIRELY
within the bar's x-range is an operand; a row that extends past it is a line
of the document that merely passes above or below a bar somewhere, and
folding that is how the earlier attempts scrambled a page.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")
from pdfreader.texmap import UNKNOWN


def _g(x0, text, baseline, size=10.0):
    return D.GlyphNode(
        id="g%s_%s" % (x0, baseline), page=1,
        rect=(x0, baseline - size, x0 + size * 0.5, baseline),
        text=text, cid=0, glyphname=None, fontname="ABC+CMR10",
        family="math-italic", size=size, tex=UNKNOWN,
        matrix=(size, 0, 0, size, x0, baseline))


def _bar(x0, x1, y, role="fraction"):
    return D.RuleNode(id="r", page=1, rect=(x0, y, x1, y + 0.4), role=role)


def _key(g):
    return g.baseline


def test_the_alpha_one_fraction_is_folded_into_one_row():
    """p293's real geometry: bar x 181.7-186.7 at y 73.5."""
    host = [_g(157.2, "α", 71.2), _g(169.9, "=", 71.2), _g(187.8, ",", 71.2)]
    num = [_g(181.7, "1", 78.1)]
    den = [_g(181.7, "2", 64.1)]
    out = D._fold_fraction_operands([host, num, den],
                                    [_bar(181.7, 186.7, 73.5)], _key)
    assert len(out) == 1
    assert "".join(g.text for g in sorted(out[0], key=lambda g: g.rect[0])) \
        == "α=12,"


def test_a_row_wider_than_the_bar_is_not_folded():
    """A document line that merely passes under a bar keeps its own row."""
    host = [_g(157.2, "α", 71.2)]
    line = [_g(100.0, "a", 64.1), _g(181.7, "b", 64.1), _g(300.0, "c", 64.1)]
    out = D._fold_fraction_operands([host, line],
                                    [_bar(181.7, 186.7, 73.5)], _key)
    assert len(out) == 2


def test_a_row_far_from_the_bar_is_not_folded():
    host = [_g(157.2, "α", 71.2)]
    far = [_g(181.7, "1", 140.0)]
    out = D._fold_fraction_operands([host, far],
                                    [_bar(181.7, 186.7, 73.5)], _key)
    assert len(out) == 2


def test_an_overline_does_not_gather_operands():
    """Only a FRACTION binds a row above AND below; `\overline` has one side."""
    host = [_g(157.2, "α", 71.2)]
    num = [_g(181.7, "1", 78.1)]
    out = D._fold_fraction_operands([host, num],
                                    [_bar(181.7, 186.7, 73.5, "overline")],
                                    _key)
    assert len(out) == 2


def test_no_rule_changes_nothing():
    rows = [[_g(1.0, "a", 10.0)], [_g(2.0, "b", 20.0)]]
    assert len(D._fold_fraction_operands(rows, [], _key)) == 2


#: ------------------------------------------------------------------
#: AND THE ROOT CAUSE WAS NOT THE FOLD: THE BAR WAS NOT A FRACTION.
#:
#: `_rule_role` classified p293's bar as `overline`, so neither
#: `_split_fractions` nor the fold above would touch it. `_is_own_row` counts
#: full-size glyphs on the numerator's baseline that lie OUTSIDE the bar, to
#: tell a numerator from a line of text passing over it. On that page it found
#: one: `bracketrightbig` at x 136.7, baseline 79.11 — the `\bigr]` closing
#: the PREVIOUS term's column vector, within the test's 0.1 em of the
#: numerator's 78.15.
#:
#: A tall delimiter is drawn RAISED (`bracketleftbig` sits at 106.9 in a row
#: whose baseline is 98.9), so its baseline coincides with a numerator's by
#: accident. The test already excludes script-size glyphs because "a running
#: text line is not set in script type"; it is not set in extensible
#: delimiters either.


def _delim(x0, baseline, size=10.0):
    from pdfreader.texmap import TexToken
    return D.GlyphNode(
        id="d%s" % x0, page=1,
        rect=(x0, baseline - size, x0 + size * 0.5, baseline),
        text="]", cid=17, glyphname="bracketrightbig",
        fontname="ABC+CMEX10", family="math-extension", size=size,
        tex=TexToken(r"\bigr]", "delimiter", None, "corpus"),
        matrix=(size, 0, 0, size, x0, baseline))


def test_a_big_delimiter_beside_a_numerator_does_not_demote_the_bar():
    """p293's geometry: the bar at x 181.7-186.7, the numerator at 78.15,
    and a `\bigr]` at x 136.7 on baseline 79.11."""
    num = _g(181.7, "1", 78.15)
    den = _g(181.7, "2", 64.11)
    host = _g(157.2, "α", 71.2)
    bracket = _delim(136.7, 79.11)
    role = D._rule_role(_bar(181.7, 186.7, 73.5, "unknown"),
                        [num, den, host, bracket], 10.0, [], 1240.0)
    assert role == "fraction"


def test_a_full_size_letter_beside_a_numerator_still_demotes_it():
    """The test must still see a real text line: a letter is not a bracket."""
    num = _g(181.7, "1", 78.15)
    den = _g(181.7, "2", 64.11)
    letter = _g(136.7, "x", 79.11)
    role = D._rule_role(_bar(181.7, 186.7, 73.5, "unknown"),
                        [num, den, letter], 10.0, [], 1240.0)
    assert role != "fraction"
