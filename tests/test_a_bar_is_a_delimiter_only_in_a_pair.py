r"""A vertical bar encloses in PAIRS and separates ALONE (the eqtable regression).

`13c88c09` (2026-11-17) made a bar a delimiter whenever the page set it flush,
measured over 122 bars of the board's 24 pages. It bought board row
lib:4859edad9294 p1287 (0.0406 -> 0.0000, 28 glyphs that had failed to pair).

Over the 441 gold display equations of the wzlxjtu corpus, ONE INSTRUMENT, the
same population, five states of this reader:

    24 Sep, the library's own copy      202 reproduced exactly
    660ea83c  16 Nov, the parent        206
    13c88c09  17 Nov, the spacing rule  156      <- -50
    b171a7db  today, before this        160
    with pairing                        214      <- and MathPix is 210

A conditional probability prints its bar flush too, so spacing cannot separate
the two roles:

    p_{1|0}        ->  p_{1} |_{0}       the bar took the 0 as its own script
    E[Y_1|D = 1]   ->  E[Y_{1} |D = 1]   a relation set as a delimiter

and the first is the worse failure: valid LaTeX saying something else, where a
refusal would at least have been visible.

PAIRING needs no threshold. A delimiter encloses, so it comes in twos with
content between them; a relation separates and stands alone.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfreader.docmodel_six import GlyphNode, _bar_by_its_pair, _shares_row
from pdfreader.texmap import project


def g(name, x, *, size=10.0, baseline=100.0, text="x", width=None,
      family="math-symbol", height=None):
    w = size * 0.5 if width is None else width
    h = size if height is None else height
    return GlyphNode(
        id=f"g{name}{x}", page=1, rect=(x, baseline, x + w, baseline + h),
        text=text, cid=1, glyphname=name, fontname="T+CMSY10",
        family=family, size=size, tex=project(family, name),
        matrix=(size, 0, 0, size, x, baseline),
    )


def bar(x, **kw):
    return g("bar", x, text="|", **kw)


def latexes(glyphs):
    return [gl.tex.latex for gl in glyphs if (gl.glyphname or "") == "bar"]


def test_a_bar_starts_as_a_relation():
    assert bar(0).tex.latex == r"\mid"


def test_two_bars_around_one_glyph_are_delimiters():
    """`|x| = x` — the line the spacing rule was written for."""
    glyphs = [bar(0), g("x", 5, family="math-italic"), bar(10),
              g("equal", 18, text="=", family="math-symbol"),
              g("x", 26, family="math-italic")]
    _bar_by_its_pair(glyphs)
    assert latexes(glyphs) == ["|", "|"]


def test_a_lone_bar_between_two_atoms_stays_a_relation():
    """`\\{x \\in R \\mid x \\geq 0\\}` — "such that" is not a delimiter."""
    glyphs = [g("A", 0, family="math-italic"), bar(6),
              g("B", 12, family="math-italic")]
    _bar_by_its_pair(glyphs)
    assert latexes(glyphs) == [r"\mid"]


def test_a_script_sized_pair_cannot_enclose_full_sized_glyphs():
    """THE DEFECT, measured: the two bars of `p_{1|0}, p_c = p_{1|1}` share a
    baseline, hold only `, p =` between them and are balanced, so they paired
    and the subscript came out `p_{1} |_{0}`. A delimiter is set at the size of
    what it encloses: a pair cannot hold a bigger glyph."""
    small, big = 7.97, 11.955
    sub = 98.2                              # the script baseline
    glyphs = [
        g("p", 0, size=big, family="math-italic"),
        g("one", 6, size=small, baseline=sub, text="1"),
        bar(10, size=small, baseline=sub),
        g("zero", 13, size=small, baseline=sub, text="0"),
        g("comma", 17, size=big, text=","),
        g("p", 22, size=big, family="math-italic"),
        g("equal", 28, size=big, text="="),
        g("p", 36, size=big, family="math-italic"),
        g("one", 42, size=small, baseline=sub, text="1"),
        bar(46, size=small, baseline=sub),
        g("one", 49, size=small, baseline=sub, text="1"),
    ]
    _bar_by_its_pair(glyphs)
    assert latexes(glyphs) == [r"\mid", r"\mid"]


def test_a_window_that_closes_a_bracket_it_never_opened_is_no_pair():
    """`E[Y_1|D = 1] - E[Y_1|D = 0]`: the two bars share a baseline and a size,
    and between them stands a `]` with no `[` of its own. They are two
    relations in two groups, not one pair spanning both."""
    glyphs = [
        g("bracketleft", 0, text="["), g("Y", 4, family="math-italic"),
        bar(9), g("D", 13, family="math-italic"),
        g("bracketright", 20, text="]"),
        g("minus", 26, text="-"),
        g("bracketleft", 33, text="["), g("Y", 37, family="math-italic"),
        bar(42), g("D", 46, family="math-italic"),
        g("bracketright", 53, text="]"),
    ]
    _bar_by_its_pair(glyphs)
    assert latexes(glyphs) == [r"\mid", r"\mid"]


def test_a_pair_spaced_on_the_inside_is_not_a_delimiter():
    """The 0.15 em is the surviving measurement of the spacing rule; what
    changed is WHERE it is taken. A pair closed on its content is a delimiter;
    one with a relation's space inside it is not."""
    glyphs = [bar(0), g("x", 9, family="math-italic"), bar(20)]
    _bar_by_its_pair(glyphs)
    assert latexes(glyphs) == [r"\mid", r"\mid"]


def test_a_delimiter_may_have_space_OUTSIDE_it():
    """A bar that OPENS a row has no left neighbour at all. The first version
    asked for the smaller gap to a bar's two neighbours and therefore refused
    to answer: on lib:4859edad9294 p1287 the display
    `|d(x, y) - d(y, z)| <= d(x, z)` begins with a bar."""
    glyphs = [bar(0), g("d", 5, family="math-italic"), bar(11),
              g("lessequal", 25, text="<=")]
    _bar_by_its_pair(glyphs)
    assert latexes(glyphs) == ["|", "|"]


def test_bars_enclosing_nothing_are_not_a_pair():
    glyphs = [bar(0), bar(5)]
    _bar_by_its_pair(glyphs)
    assert latexes(glyphs) == [r"\mid", r"\mid"]


class TestWhichRowAGlyphIsOn:
    """`_shares_row`: this pass runs before `_group_lines`, so there are no
    lines to ask — only boxes. Two wrong answers were measured first."""

    def test_an_ascender_of_the_next_line_is_not_on_this_row(self):
        """ANY box overlap: a bar's box is as tall as the line, so the
        ascenders above and below reach into it, and the window of `|x|` came
        back as `txr` and `lxl`."""
        b = bar(0, size=12.0, baseline=100.0)          # box 100..112
        l_above = g("l", 2, size=12.0, baseline=111.0)  # box 111..123
        assert _shares_row(l_above, b) is False

    def test_the_base_lines_own_glyphs_are_on_a_script_bars_row(self):
        """The glyph's CENTRE inside the bar's box: that excluded the base
        line's glyphs when the bar is SCRIPT size — the very glyphs the size
        test needs — and `F_{Y_1|D=1}^{-1} - F_{Y_1|D=0}^{-1}` paired through
        the `(q) -` between them."""
        b = bar(0, size=7.97, baseline=98.2)            # box 98.2..106.2
        base = g("paren", 2, size=11.955, baseline=100.0)   # box 100..112
        assert _shares_row(base, b) is True

    def test_a_glyph_on_the_same_baseline_shares_the_row(self):
        assert _shares_row(g("x", 5), bar(0)) is True
