"""Two things a reading must not do: invent letters, and lose an accent.

**pdfminer's placeholder is not text.** A font with no ToUnicode map makes
`get_text()` return the literal string `(cid:205)`, and writing that into a
reading puts nine characters on the page that are not there. Measured over the
board's 24 born-digital pages (drillgroup 35331e2): 61 of them on 9 pages,
against MathPix's none; on 1805.01788 p3 all 21 are a `\\sum` from txfonts,
named `summationtext.1` and `summationdisplay.1`. PostScript names a font's
alternates `<name>.<variant>` and the tables are keyed by the base name, so
every variant abstained. After: 61 -> 0, of which 31 recovered their real LaTeX
and 30 became one explicit unknown character each.

**An accent's bar is not contained by its base.** `_covers_as_overline` asked
for containment, which is right for `\\overline{A}` -- TeX draws it to the width
of the box it covers -- and wrong for `\\bar{M}`, drawn to the width of the
ACCENT. On 2103.01507 p118 the bar runs 222.83..233.63 over an `M` at
222.84..232.50 and failed by 0.63 pt: all 26 of that page's overlines were
found, classified `overline`, and attached to no line at all. Board-wide,
accent commands in our reading went 29 -> 57 (MathPix 87).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

docmodel = pytest.importorskip("pdfreader.docmodel_six")
texmap = pytest.importorskip("pdfreader.texmap")


def _glyph(text, x0, x1, baseline=100.0, size=10.0, name=None, tex=None):
    return docmodel.GlyphNode(
        id="g%d" % int(x0), page=1, rect=(x0, baseline, x1, baseline + size),
        text=text, cid=0, glyphname=name, fontname="CMR10", family="cm",
        size=size, tex=tex or texmap.UNKNOWN)


def _rule(x0, x1, y):
    return docmodel.RuleNode(id="r", page=1, rect=(x0, y - 0.24, x1, y + 0.24),
                             role="overline")


# ---- the placeholder ----------------------------------------------------

def test_a_variant_glyph_name_resolves_from_its_base():
    assert texmap.project("math-extension", "summationtext.1", -1,
                          "ERHUAP+txexs").latex == r"\sum"
    assert texmap.project("math-extension", "summationdisplay.1", -1,
                          "ERHUAP+txexs").latex == r"\sum"


def test_the_base_is_tried_only_after_the_full_name_abstains():
    # A name the table knows outright keeps its own answer.
    assert texmap.project("math-extension", "summationtext", -1,
                          "ERHUAP+txexs").latex == r"\sum"


def test_an_identified_glyph_is_written_as_its_latex_not_as_a_placeholder():
    g = _glyph("(cid:205)", 0, 8, tex=texmap.project(
        "math-extension", "summationtext.1", -1, "ERHUAP+txexs"))
    out = docmodel._run_text([g])
    assert "(cid:" not in out
    assert r"\sum" in out


def test_an_unidentified_glyph_is_written_as_one_explicit_unknown():
    out = docmodel._run_text([_glyph("(cid:999)", 0, 8)])
    assert "(cid:" not in out
    assert out == docmodel.UNKNOWN_GLYPH_CHAR


def test_ordinary_text_is_untouched():
    out = docmodel._run_text([_glyph("a", 0, 5), _glyph("b", 5, 10)])
    assert out == "ab"


def test_a_string_that_merely_looks_like_one_is_left_alone():
    # Real text on a page may read "(cid:x)"; only the exact shape is dropped.
    assert docmodel._run_text([_glyph("(cid:x)", 0, 8)]) == "(cid:x)"


# ---- the accent ---------------------------------------------------------

def test_a_bar_overhanging_its_base_is_still_that_base_s_accent():
    # 2103.01507 p118, measured: the bar overhangs the M by 1.13 pt.
    M = _glyph("M", 222.84, 232.50, baseline=645.51, size=9.96)
    bar = _rule(222.83, 233.63, 656.27)
    assert docmodel._covers_as_overline(bar, 656.27, [M])


def test_an_overline_drawn_to_the_box_still_matches():
    A = _glyph("A", 177.50, 184.97, baseline=645.51, size=9.96)
    bar = _rule(177.50, 184.97, 656.00)
    assert docmodel._covers_as_overline(bar, 656.00, [A])


def test_a_rule_far_longer_than_the_glyph_is_not_its_accent():
    # A table rule passes over a glyph; it is not that glyph's bar.
    M = _glyph("M", 222.84, 232.50, baseline=645.51, size=9.96)
    rule = _rule(72.0, 532.0, 656.27)
    assert not docmodel._covers_as_overline(rule, 656.27, [M])


def test_a_bar_below_the_glyph_top_is_not_an_overline():
    M = _glyph("M", 222.84, 232.50, baseline=645.51, size=9.96)
    bar = _rule(222.83, 233.63, 640.0)
    assert not docmodel._covers_as_overline(bar, 640.0, [M])
