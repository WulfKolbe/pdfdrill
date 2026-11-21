r"""A fraction set in script-size numerals is `\tfrac`, not `\frac`.

T-0156, found by inkdrill-10 on lib:6d90e8d27b8b p174: that page's fractions
are text style inside a display line, with CMR6/CMMI6 numerals, and our
`\frac` sets them display-size. The glyph findings on those numerals are
correct — the numbers really are the wrong size in our rendering.

THE SIZE OF THE NUMERALS IS THE EVIDENCE. Measured on p174: the page's
dominant type size is 9.6, the fractions' numerals are 6.7, and the glyphs
beside each fraction are 9.6. 6.7/9.6 = 0.70, which is CMR6 against a 9.6 pt
line.

MEASURED over the 24 board-14 extracts: 118 fractions, of which **49** carry
script-size numerals —

    lib:6d90e8d27b8b p174   50 fractions   42 tfrac
    lib:c57ac038ae5f p293   12              4
    lib:3fe71b4ef018 p328   17              1
    0864 p4                  1              1
    lib:4859edad9294 p1287   1              1
    six further pages                       0

TWO THINGS THE COUNT HAD TO LEARN, because the first two versions of it were
wrong in opposite directions.

A fraction inside a SUPERSCRIPT also has small numerals — the whole
subexpression is small. So the test cannot be "numerals smaller than the
page": that version counted 51 and could not see the difference at all. It
has to be "numerals smaller than the fraction's own NEIGHBOURS, which are
full size".

And the neighbour has to be the NEAREST one, not the largest within reach. A
nested inner fraction (p174 has one, numerals at 4.8 inside an outer at 6.7)
finds a full-size glyph a few em away and counts itself. Nearest-neighbour
gives 49 `\tfrac` and 2 inside a script, and those 2 are exactly the nested
cases. It matters: an inner fraction INHERITS its style, so only the
outermost may be marked — `\tfrac` inside a `\tfrac` would force textstyle
where the context is already script, making the inner one too big.

`\tfrac` needs `amsmath`, which the judge's setter preamble loads
(`judge.py:936-937`, `\usepackage{amsmath,amssymb,amsfonts}`).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

S = pytest.importorskip("pdfreader.structure")
D = pytest.importorskip("pdfreader.docmodel_six")
from pdfreader.texmap import UNKNOWN


def _g(x0, size, text="1"):
    return D.GlyphNode(
        id="g%s" % x0, page=1, rect=(x0, 100.0, x0 + size * 0.5, 100.0 + size),
        text=text, cid=0, glyphname=None, fontname="ABC+CMR10",
        family="math-italic", size=size, tex=UNKNOWN,
        matrix=(size, 0, 0, size, x0, 100.0))


def test_script_size_numerals_beside_full_size_text_are_a_tfrac():
    """p174's shape: numerals 6.7, the glyph beside the fraction 9.6."""
    assert S._is_text_style([_g(10.0, 6.7)], [_g(10.0, 6.7)],
                            [_g(0.0, 9.6)], 9.6, 0) is True


def test_full_size_numerals_are_an_ordinary_frac():
    assert S._is_text_style([_g(10.0, 9.6)], [_g(10.0, 9.6)],
                            [_g(0.0, 9.6)], 9.6, 0) is False


def test_a_nested_fraction_is_not_marked():
    """Depth is the nesting: an inner fraction inherits the outer's style,
    and `\tfrac` inside a `\tfrac` would make it too big."""
    assert S._is_text_style([_g(10.0, 4.8)], [_g(10.0, 4.8)],
                            [_g(0.0, 6.7)], 6.7, 1) is False


def test_the_nearest_neighbour_decides_not_the_largest():
    """A nested inner fraction finds a full-size glyph a few em away. The
    near neighbour is small, so the fraction is script context, not tfrac."""
    near, far = _g(12.0, 6.7), _g(200.0, 9.6)
    assert S._is_text_style([_g(20.0, 4.8)], [_g(20.0, 4.8)],
                            [near, far], 9.6, 0) is False


def test_a_fraction_with_no_neighbour_abstains():
    """Nothing to compare against: the ordinary `\frac` is kept."""
    assert S._is_text_style([_g(10.0, 6.7)], [_g(10.0, 6.7)], [], 9.6, 0) is False


def test_an_empty_fraction_abstains():
    assert S._is_text_style([], [], [_g(0.0, 9.6)], 9.6, 0) is False
