r"""B1 — a digit after a relation was left OUTSIDE the inline maths.

Board state 75, three occurrences across two documents (drillgroup
results/errors-open.md B1):

    lib:4859edad9294 p1287 L25   "... if $x <$ 0, and for a complex"
    lib:6d90e8d27b8b p174  L7    "$x(1) =$ 1 liefert $c =$ 1, und es ist"

THE CAUSE IS NOT THE DIGIT'S FONT, which was the standing hypothesis. The
same line of 4859 carries both readings:

    ... if $x \geq 0, |x| = -x$ if $x <$ 0, and for a complex
             ^^^^^^ the 0 is INSIDE        ^^^^ and here it is OUTSIDE

and the two zeros are identical — family `text-cm`, glyphname `zero`,
size 12.0. So is the relation's recognition: `greaterequal` comes from CMSY
(family `math-symbol`) and `less` from CMMI (`math-italic`, where TeX keeps
`<` and `>`), and `texmap` maps both.

What differs is WHAT FOLLOWS THE DIGIT. `_spans` absorbs a neutral run only
when maths sits on BOTH sides —

    absorb = left_any and right_any and neutral

— so `0,` between `x \geq` and `|x|` is taken, while `0,` between `x <` and
the prose `and for a complex` is not. A digit that ENDS an expression can
never be absorbed, whatever its font.

NOR CAN SPACING DECIDE IT, measured on that line (word gap 2.20):

    '≥'->'0'  4.08     '<'->'0'  4.08      identical
    ','->'|'  4.46     ','->'a'  4.46      identical
    an ordinary prose word gap 'r'->'a'  4.35

The relation-to-digit gap is 6% narrower than a prose word gap, and `_tight`
demands under 0.35 of the word gap. Spacing cannot carry this.

THE EVIDENCE THAT CAN is the mathematics: a relation or a binary operator
CANNOT END A WELL-FORMED EXPRESSION. `$x<$` is malformed; the thing to its
right is its operand. So a neutral run is absorbed with maths on the LEFT
alone when that maths run ends with such a glyph. The set is derived from the
reader's own `texmap` tables, not from a list of what these pages happen to
use, and `bar` is excluded from it because `|` arrives as glyphname `bar` and
is a DELIMITER (`|x|`), not a relation.

NOT FIXED HERE, and a different cause: 6d90 L8 ends `lautet $x(t) =$` with
its operand on L9 (`$\sqrt{2 - t^{2}}.$`). The author's one expression
straddles a line break, so there is no run to the right on that line at all.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfreader.docmodel_six import (                           # noqa: E402
    GlyphNode, LineNode, TexToken, _spans)


def _g(x0, w, text, name, family, *, size=12.0, kind="atom", base=119.04):
    return GlyphNode(
        id=f"g{x0}", page=2, rect=(x0, base - 0.2 * size, x0 + w,
                                   base + 0.75 * size),
        text=text, cid=1, glyphname=name,
        fontname={"math-italic": "CMMI12", "math-symbol": "CMSY12",
                  "text-cm": "CMR12"}.get(family, "CMR12"),
        family=family, size=size,
        tex=TexToken(text, kind, None, "corpus"),
        matrix=(1, 0, 0, 1, x0, base))


def _line(glyphs):
    xs = [g.rect for g in glyphs]
    return LineNode(
        id="p2l25", page=2,
        rect=(min(r[0] for r in xs), min(r[1] for r in xs),
              max(r[2] for r in xs), max(r[3] for r in xs)),
        glyphs=sorted(glyphs, key=lambda g: g.rect[0]),
        type="text")


#: 4859 p1287 L25, to the measured coordinates: `x < 0, and for`
def _x_less_zero_then_prose():
    return _line([
        _g(408.8, 6.6, "x", "x", "math-italic"),
        _g(419.6, 9.2, "<", "less", "math-italic"),
        _g(432.8, 5.8, "0", "zero", "text-cm"),
        _g(438.6, 3.3, ",", "comma", "text-cm"),
        _g(446.3, 5.9, "a", "a", "text-cm", kind="unknown"),
        _g(452.2, 6.5, "n", "n", "text-cm", kind="unknown"),
        _g(458.7, 6.3, "d", "d", "text-cm", kind="unknown"),
        _g(469.5, 3.6, "f", "f", "text-cm", kind="unknown"),
        _g(473.1, 5.9, "o", "o", "text-cm", kind="unknown"),
        _g(479.0, 4.1, "r", "r", "text-cm", kind="unknown"),
    ])


def _maths_text(line):
    out = []
    for sp in _spans(line):
        out.append((sp.kind, "".join(g.text or "" for g in sp.glyphs)))
    return out


def test_the_digit_after_a_relation_is_inside_the_maths():
    """THE RED. Three occurrences on the board's two worst prose pages."""
    got = _maths_text(_x_less_zero_then_prose())
    maths = "".join(t for k, t in got if k == "math")
    assert "0" in maths, (
        f"the operand of `<` was left outside the maths: {got}")
    assert maths.startswith("x<0"), got


def test_the_prose_after_it_is_still_prose():
    """The guard that matters: absorbing on one side must not swallow words."""
    got = _maths_text(_x_less_zero_then_prose())
    text = "".join(t for k, t in got if k != "math")
    assert "and" in text.replace(" ", "") and "for" in text.replace(" ", ""), got
    maths = "".join(t for k, t in got if k == "math")
    for w in ("and", "for", "a", "n", "d"):
        assert "and" not in maths and "for" not in maths, got


def test_a_digit_between_two_maths_runs_is_unchanged():
    r"""`x \geq 0, |x|` on the same real line, which already worked."""
    line = _line([
        _g(309.2, 6.6, "x", "x", "math-italic"),
        _g(319.9, 9.4, "≥", "greaterequal", "math-symbol"),
        _g(333.3, 5.8, "0", "zero", "text-cm"),
        _g(339.1, 3.3, ",", "comma", "text-cm"),
        _g(346.8, 3.3, "|", "bar", "math-symbol", kind="delimiter"),
        _g(350.1, 6.7, "x", "x", "math-italic"),
        _g(356.8, 3.3, "|", "bar", "math-symbol", kind="delimiter"),
    ])
    maths = "".join(t for k, t in _maths_text(line) if k == "math")
    assert "0" in maths, _maths_text(line)


def test_a_delimiter_does_not_claim_what_follows_it():
    r"""`bar` is excluded from the set on purpose: `|x|` ENDS an expression,
    so a digit after it is not its operand. Without the exclusion
    `$|x|$ 5 apples` would take the 5."""
    line = _line([
        _g(100.0, 3.3, "|", "bar", "math-symbol", kind="delimiter"),
        _g(104.0, 6.7, "x", "x", "math-italic"),
        _g(111.0, 3.3, "|", "bar", "math-symbol", kind="delimiter"),
        _g(120.0, 5.8, "5", "five", "text-cm"),
        _g(130.0, 5.9, "a", "a", "text-cm", kind="unknown"),
        _g(136.0, 6.5, "p", "p", "text-cm", kind="unknown"),
    ])
    maths = "".join(t for k, t in _maths_text(line) if k == "math")
    assert "5" not in maths, _maths_text(line)


def test_an_expression_that_ends_in_a_variable_claims_nothing():
    """`$x$ 5 apples` — a variable is a complete expression, so the digit
    beside it is not an operand and must stay prose."""
    line = _line([
        _g(100.0, 6.7, "x", "x", "math-italic"),
        _g(112.0, 5.8, "5", "five", "text-cm"),
        _g(122.0, 5.9, "a", "a", "text-cm", kind="unknown"),
        _g(128.0, 6.5, "p", "p", "text-cm", kind="unknown"),
    ])
    maths = "".join(t for k, t in _maths_text(line) if k == "math")
    assert "5" not in maths, _maths_text(line)
