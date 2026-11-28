r"""T-0162 item 1 — the under-rule gap: ink above, nothing below, no branch.

`_rule_role`'s tail reads

    above = _is_own_row(above_b) or _script_fraction()
    below_row = _is_own_row(below_b)
    if above and (below_row or below_b): return "fraction"
    if _sits_under(below_b) and not above: return "overline"
    return "unknown"

For ink ABOVE and nothing below, `above` may be true but `below_b` is empty,
so the fraction test is falsy; `_sits_under([])` is False; the answer is
`unknown`, and an unaccounted rule defers the whole span. That is why no
`\underline` is emitted anywhere in the corpus.

MEASURED, AND CHECKED AGAINST THE AUTHOR (the standing rule of 2026-11-23 for
a maths-structure change). arxiv.gr-qc_0212041 page 1 carries three `unknown`
rules, each 4.7 pt wide and 0.48 pt thick:

    rule x=[234.6,239.3]  ABOVE d=+1.33  'e' CMMI10 x=[234.6,239.2]
    rule x=[219.2,223.9]  ABOVE d=+1.33  'e' CMMI10 x=[219.2,223.9]
    rule x=[263.7,268.4]  ABOVE d=+1.33  'e' CMMI10 x=[263.8,268.4]

and the AUTHOR's own source (CG.tex out of the e-print, read through
`latex_source.read_source`, `\documentclass[english]{article}`) holds exactly
three `\underline`, every one of them `\underline{e}`. Three rules, three
underlines, the same argument, each rule drawn to the width of the letter it
underlines.

TWO THINGS THAT TOOK MEASURING, AND BOTH CHANGED THE DESIGN.

1. `\underrightarrow` IS NOT A RULE. The same author writes it 43 times, and
   an earlier note had it queued with `\underline` as one defect. TeX builds
   it from GLYPHS: a `minus` and an `arrowright` from CMSY10 on one baseline,
   overlapping (x=[207.6,215.3] and x=[207.6,217.6] on page 1). No rule
   object is drawn at all, so no branch here could ever emit one. It is a
   glyph-composition problem and it is a different task.

2. `above` IS FALSE FOR ALL THREE, so the branch cannot be written in terms of
   it. `_is_own_row(above_b)` counts what else sits on that baseline outside
   the bar within six ems, to catch a text line running across -- and an
   underlined `e` is PART of a running line: `=`, `d`, `x` share its baseline.
   The test that fits is the one the overline already uses: `_sits_under`
   asks whether the ink is CONTAINED by the rule, because TeX draws the accent
   to the width of what it accents. `_sits_over` is its mirror.

WHY THIS DOES NOT CATCH A FOOTNOTE RULE: the width vetoes run before the tail.
A footnote rule is 6.2 em on the measured set and `_PLAIN_OPERAND_EM` is 4.0,
so a rule that wide with no mathematics on both sides is a `separator` long
before it reaches here.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfreader.docmodel_six import (                        # noqa: E402
    GlyphNode, RuleNode, TexToken, _rule_role)


def _g(x0, base, w, *, size=10.0, text="e", name="e", font="CMMI10",
       family="math-italic"):
    """A glyph on a baseline, box as pdfminer gives it (the advance box)."""
    return GlyphNode(
        id=f"g{x0}", page=1, rect=(x0, base - 0.2 * size, x0 + w,
                                   base + 0.7 * size),
        text=text, cid=1, glyphname=name, fontname=font, family=family,
        size=size, tex=TexToken(text, "glyph", None, 1.0),
        matrix=(1, 0, 0, 1, x0, base))


def _rule(x0, y, w, h=0.48):
    return RuleNode(id="r1", page=1, rect=(x0, y, x0 + w, y + h))


#: 0212041 p1's first unknown rule, to the measurement above.
BAR_X, BAR_Y, BAR_W = 234.6, 422.3, 4.7
BASE_ABOVE = 423.63          # d = +1.33 from the rule's middle


#: 0212041 p1's first unknown rule WITH ITS REAL NEIGHBOURS, transcribed from
#: the measurement in this module's docstring. The glyph list is not optional
#: decoration: with only the underlined `e` present, `_rule_role` answers
#: `underscore`, because the underscore branch takes the baseline of the glyph
#: whose LEFT edge is nearest the rule's RIGHT edge, and with one glyph that
#: is the `e` itself, 1.09 pt above the rule. On the page it is a `t` in the
#: prose line 21.8 pt below, so the branch does not fire and the rule reaches
#: the tail as `unknown`. A one-glyph test would have been testing a path the
#: document never takes -- and would have passed against a fix for a defect
#: that is not the one on the page.
def _p1_rule1_glyphs():
    prose_base = BAR_Y + 0.24 - 21.83          # the running line below
    g = [_g(x, prose_base, w, text=t, name=t, font="Times-Roman",
            family="text")
         for x, w, t in ((198.1, 4.4, "e"), (202.6, 2.7, "l"), (205.3, 4.4, "a"),
                         (209.8, 2.7, "t"), (212.5, 2.8, "i"), (215.3, 5.0, "o"),
                         (220.3, 5.0, "n"), (227.6, 3.4, "f"), (231.0, 5.0, "o"),
                         (236.0, 3.4, "r"), (241.8, 2.8, "t"), (244.6, 4.9, "h"),
                         (249.6, 4.4, "e"), (256.4, 5.0, "o"), (261.5, 3.3, "r"),
                         (264.8, 2.8, "t"), (267.6, 5.0, "h"), (272.6, 5.0, "o"))]
    # the underlined `e`, and the rest of its own display row
    g += [_g(234.6, BASE_ABOVE, 4.6),
          _g(249.1, BASE_ABOVE, 7.8, text="=", name="equal", font="CMR10",
             family="math-roman"),
          _g(266.9, BASE_ABOVE, 5.2, text="d", name="d"),
          _g(272.0, BASE_ABOVE, 5.7, text="x", name="x")]
    return g


def test_the_page_reaches_the_tail_as_unknown_today():
    """The precondition of the red, asserted so the next reader can see that
    the new branch is reached by this input and not short-circuited."""
    g = _p1_rule1_glyphs()
    assert _rule_role(_rule(BAR_X, BAR_Y, BAR_W), g) != "underscore", (
        "the underscore branch fired, so this input is not the page's path")


def test_a_rule_under_a_contained_letter_is_an_underline():
    """THE RED. Three of these on 0212041 p1, three `\\underline{e}` in the
    author's source, each rule drawn to the width of its letter.

    An underlined `e` is PART of a running line -- `=`, `d`, `x` share its
    baseline here -- so `_is_own_row` is False and the branch cannot be
    written in terms of `above`. Containment is the test, as it is for the
    overline."""
    g = _p1_rule1_glyphs()
    assert _rule_role(_rule(BAR_X, BAR_Y, BAR_W), g) == "underline"


def test_ink_on_both_sides_is_still_a_fraction():
    """The regression that matters most: 126 rules are `fraction` today and
    the falsifier showed what happens to a reading when they stop being."""
    glyphs = [_g(234.6, BAR_Y + 4.6, 4.6, text="1", name="one"),
              _g(234.6, BAR_Y - 9.5, 4.6, text="2", name="two")]
    assert _rule_role(_rule(BAR_X, BAR_Y, BAR_W), glyphs) == "fraction"


def test_ink_below_only_is_still_an_overline():
    glyphs = [_g(234.6, BAR_Y - 3.0, 4.6)]
    assert _rule_role(_rule(BAR_X, BAR_Y, BAR_W), glyphs) == "overline"


def test_nothing_near_it_is_still_unknown():
    """Abstaining is the right answer when there is no evidence; the function
    says so in its own docstring."""
    glyphs = [_g(400.0, BAR_Y + 2.0, 4.6)]
    assert _rule_role(_rule(BAR_X, BAR_Y, BAR_W), glyphs) == "unknown"


def test_ink_above_that_the_rule_does_not_cover_is_not_an_underline():
    """TeX draws the accent to the width of what it accents, so a rule far
    narrower than the ink above it is not underlining it. This is the clause
    that keeps a short table rule out."""
    glyphs = [_g(200.0, BASE_ABOVE, 80.0, text="n", name="n",
                 font="Times-Roman", family="text")]
    assert _rule_role(_rule(BAR_X, BAR_Y, BAR_W), glyphs) != "underline"


def test_a_wide_rule_with_text_above_is_still_a_separator():
    """A footnote rule: text above, nothing below. The width vetoes run first
    -- `_PLAIN_OPERAND_EM` is 4.0 and the measured footnote rules start at
    6.2 em -- so it must never reach the new branch."""
    glyphs = [_g(100.0, BASE_ABOVE + 2, 8.0, text="h", name="h",
                 font="Times-Roman", family="text")]
    assert _rule_role(_rule(100.0, BAR_Y, 62.0), glyphs) == "separator"


def test_an_underscore_is_still_an_underscore():
    r"""`took_*` reaches the model as a zero-height rule ON the baseline, and
    that branch runs before this one. An underline sits BELOW the baseline of
    what it underlines; an underscore sits on it."""
    base = BAR_Y
    glyphs = [_g(228.0, base, 6.0, text="k", name="k", font="Times-Roman",
                 family="text")]
    assert _rule_role(_rule(BAR_X, BAR_Y, 3.14, h=0.0),
                      glyphs) == "underscore"


def test_a_vertical_rule_is_not_an_underline():
    glyphs = [_g(234.6, BASE_ABOVE, 4.6)]
    assert _rule_role(_rule(BAR_X, BAR_Y, 0.4, h=11.0), glyphs) == "separator"


def test_a_rule_with_no_thickness_is_not_an_underline_inside_a_word():
    r"""Found by checking what this branch newly claimed on the board, not by
    a test: three of its four new classifications have h=0.00 and none of them
    is an `\underline` --- a 3.09 em zero-height rule under two interleaved
    rows of a byline, and a 0.60 em zero-height rule under `te` mid-word,
    twice. The three verified cases are 0.48 pt thick.

    REVISED (board 117): "a rule with no thickness was not drawn as a line"
    is not so. pdfminer gives a STROKED line no thickness, and
    lib:c9daf79960c3 p68's `\underline{Map}` is one (a 0.398 pt stroke, 0 pt
    tall). What the false cases share is that the bar cuts a word: a glyph on
    the argument's baseline touches an end of it. So a zero-height rule under
    letters that run on past it is not an underline; the same rule under a
    free-standing argument is."""
    base = BASE_ABOVE
    word = [_g(x, base, w, text=t, name=t, font="Times-Roman", family="text")
            for x, w, t in ((227.6, 3.5, "w"), (231.1, 3.5, "r"),
                            (234.6, 2.8, "t"), (237.4, 2.3, "e"),
                            (239.7, 3.5, "s"))]
    assert _rule_role(_rule(234.6, BAR_Y, 5.1, h=0.0), word) != "underline"
    # ...and the verified one keeps its answer, thick or stroked
    g = _p1_rule1_glyphs()
    assert _rule_role(_rule(BAR_X, BAR_Y, BAR_W, h=0.48), g) == "underline"
