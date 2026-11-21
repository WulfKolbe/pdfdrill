r"""Glyphs stacked inside a bracket are a column vector, not a run of digits.

T-0154, the second consumer commit. `lib:c57ac038ae5f` p293 sets

    t_0 = 3 [ 1 / -1/2 ],   as 1 OVER -1/2 inside one big bracket

MEASURED, that term's glyphs (reader row 27, x order):

    bracketleftbig   base 106.9  size 10.0
    −  1  /  2       base  96.3  size  7.6      the LOWER entry
    1                base 102.9  size  7.6      the UPPER entry
    bracketrightbig  base 106.9  size 10.0

Two baselines, 6.6 apart, both entries at the same size, their x-ranges
overlapping. Read in x order the two rows interleave to `−11/2`, which is what
the reading carried; MathPix writes
`\left[\begin{array}{c} 1 \\ -1/2 \end{array}\right]`.

A HIGHER BASELINE IS A HIGHER ROW: the y axis grows upward here, which the
fraction pass already relies on — `\alpha_0 = \frac{1}{2}` comes from `1` at
baseline 105.9 over `2` at 91.8.

WHAT MUST NOT BECOME AN ARRAY is the reason this needs two tests rather than
one. `[x^2]` also puts glyphs on two baselines. It is one row, because a
script sits to the RIGHT of its base and does not overlap it in x, and is
SMALLER than it. A stacked entry sits in the same column as its sibling and at
the same size. Both tests are below; getting this wrong turns every
parenthesised power into a 1-column array.
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
        id="g%s_%s" % (x0, baseline), page=1,
        rect=(x0, baseline - size, x0 + size * 0.5, baseline),
        text=text, cid=0, glyphname=None, fontname="ABC+CMR10",
        family="math-italic", size=size, tex=UNKNOWN,
        matrix=(size, 0, 0, size, x0, baseline))


def test_two_entries_in_one_column_are_two_rows():
    """p293's shape: `1` over `-1/2`, same size, overlapping x."""
    gs = [_g(100.6, "-", 96.3, 7.6), _g(106.4, "1", 96.3, 7.6),
          _g(110.3, "/", 96.3, 7.6), _g(113.9, "2", 96.3, 7.6),
          _g(107.2, "1", 102.9, 7.6)]
    rows = S._stacked_rows(gs, 10.0)
    assert rows is not None and len(rows) == 2
    assert "".join(g.text for g in rows[0]) == "1"        # higher baseline first
    assert "".join(g.text for g in rows[1]) == "-1/2"


def test_a_superscript_is_not_a_row():
    r"""`x^2` — the script is to the RIGHT of its base and smaller."""
    gs = [_g(100.0, "x", 100.0, 10.0), _g(105.5, "2", 104.0, 7.0)]
    assert S._stacked_rows(gs, 10.0) is None


def test_one_baseline_is_not_stacked():
    gs = [_g(100.0, "1"), _g(105.0, "2")]
    assert S._stacked_rows(gs, 10.0) is None


def test_three_entries_are_three_rows():
    gs = [_g(100.0, "a", 110.0, 7.6), _g(100.0, "b", 100.0, 7.6),
          _g(100.0, "c", 90.0, 7.6)]
    rows = S._stacked_rows(gs, 10.0)
    assert rows is not None
    assert [g.text for r in rows for g in r] == ["a", "b", "c"]


def test_nothing_is_not_stacked():
    assert S._stacked_rows([], 10.0) is None


#: ------------------------------------------------------------------
#: AND AN ORDINARY BRACKETED EXPRESSION IS NOT AN ARRAY.
#:
#: The first version of this pass had only the column and size tests, and it
#: read p293 line 8's
#:
#:     \biggl(-\epsilon e_i^T r(y)) + \frac{1}{2} \epsilon^2 e_i^T Ae_i\biggr)
#:
#: as a 2-row array, because its scripts and fraction also form two bands of
#: similar size in overlapping columns. A line that had assembled CORRECTLY
#: flattened instead — measured on the board as 4 lost `\epsilon`.
#:
#: What separates them: a column vector has NOTHING on the row's own
#: baseline between its brackets. An ordinary bracketed expression has its
#: body there, with scripts and fractions around it.


def test_a_bracketed_expression_on_the_baseline_is_not_an_array():
    """Body on the row baseline, a superscript above it: one row."""
    gs = [_g(100.0, "e", 100.0, 10.0), _g(105.0, "T", 104.5, 7.0),
          _g(110.0, "r", 100.0, 10.0), _g(115.0, "y", 100.0, 10.0)]
    assert S._stacked_rows(gs, 10.0, 100.0) is None


def test_a_column_vector_clear_of_the_baseline_is_still_an_array():
    """p293's entries at 96.3 and 102.9 in a row whose baseline is 98.9."""
    gs = [_g(100.6, "-", 96.3, 7.6), _g(106.4, "1", 96.3, 7.6),
          _g(107.2, "1", 102.9, 7.6)]
    rows = S._stacked_rows(gs, 10.0, 98.9)
    assert rows is not None and len(rows) == 2


#: ------------------------------------------------------------------
#: AND A SCRIPT-SIZE MATRIX IS A `smallmatrix`.
#:
#: Board state 45 scored 7de82d7a: p293 went 0.0791 -> 0.0668, rules invented
#: 7 -> 2, flagged 30 -> 21 — but unpaired went 3/22 -> 5/24, and the two new
#: ones are THE SAME GLYPHS ON BOTH SIDES:
#:
#:     side A (ink)   + L30 "2"   + L31 "/"
#:     side B (ours)  + L30 "2"   + L31 "/"
#:
#: A glyph unpaired on both sides is a pairing failure, not a loss: it is in
#: the ink and in our rendering, at positions that do not match. They are the
#: `/` and `2` of a `1/2` entry on the two matrix rows.
#:
#: MEASURED, all 12 arrays on p293: entries 7.57 against a row of 9.96 —
#: ratio 0.760, every one of them. The page sets these matrices at SCRIPT
#: size and we set `array` at full size, so LaTeX positions `1/2` by its own
#: metrics and those glyphs land off the ink.
#:
#: Same discriminator as `\tfrac` (`_is_text_style`): the entries' size
#: against the row's full-size glyphs. `smallmatrix` needs amsmath, which the
#: preamble loads and which was verified for `\tfrac`.
#:
#: NOTE: `smallmatrix` takes NO column specification, so the `{c}` that
#: `array` carries must be dropped rather than passed on — otherwise it is
#: typeset as the body's first characters.


def test_script_size_entries_choose_smallmatrix():
    """p293's ratio: 7.57 entries in a 9.96 row."""
    assert S._matrix_env(7.57, 9.96) == "smallmatrix"


def test_full_size_entries_keep_array():
    assert S._matrix_env(9.96, 9.96) == "array"


def test_the_boundary_belongs_to_array():
    """0.85 exactly is not script size — the same edge as `_is_text_style`."""
    assert S._matrix_env(8.5, 10.0) == "array"


def test_an_unknown_row_size_keeps_array():
    """No row to compare against: do not guess a smaller environment."""
    assert S._matrix_env(7.57, 0.0) == "array"
