"""Tests for docmodel — the guarantees, and the two traps this build fell into.

Both traps produced *plausible* output, which is the dangerous kind:
  - the box bottom used as a baseline made `\\vartheta^{\\alpha}` project as
    `\\vartheta \\alpha`;
  - a lone superscript span projected as a standalone `$\\alpha$`.
Neither raised an error. Both are asserted against here.
"""

import os

import pytest

import docmodel_six as docmodel
import testpaths
from docmodel_six import GlyphNode, RuleNode, Span, _is_level, glyph_latex
from texmap import TexToken, project


# --- corpus fixtures -------------------------------------------------------
# These tests read real PDFs. They are not shipped with the toolkit (they are
# copyrighted books), so the whole module skips when they are absent rather
# than failing on a machine that simply does not have them. Point
# PDF2MMD_TEST_PDF / PDF2MMD_TEST_LINES at your own copies to run them.
MIELKE = testpaths.CORPUS_PDF

# The gate is PER CLASS, not on the module.
#
# It used to be `pytestmark`, which skipped all 142 tests in this file when
# the corpus PDF was absent -- though only SIX of them open it. On a machine
# without the fixtures the suite reported 270 passed and 250 skipped, so
# roughly half of it could not be run by anyone but me, and "519 passing"
# was a number the reader had to take on trust. That is the wrong shape for
# a project whose whole argument is that measurements should be checkable.
needs_corpus = pytest.mark.skipif(
    not os.path.exists(MIELKE),
    reason="no corpus PDF; set PDF2MMD_TEST_PDF to run these")
P209 = range(208, 209)


def g(name, family="math-italic", size=10.0, baseline=100.0, x=0.0, text="x"):
    return GlyphNode(
        id="t", page=1, rect=(x, baseline, x + size * 0.5, baseline + size),
        text=text, cid=1, glyphname=name, fontname="TEST+CMMI10",
        family=family, size=size, tex=project(family, name),
        matrix=(size, 0, 0, size, x, baseline),
    )


@pytest.fixture(scope="module")
def page209():
    return docmodel.build(MIELKE, P209)


@needs_corpus
class TestG1EveryGlyphSurvives:
    def test_node_count_equals_char_count(self, page209):
        """G1: one GlyphNode per LTChar. Nothing is dropped, ever."""
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTChar

        chars = 0
        for layout in extract_pages(MIELKE, page_numbers=list(P209)):
            stack = list(layout)
            while stack:
                o = stack.pop()
                if isinstance(o, LTChar):
                    chars += 1
                elif hasattr(o, "__iter__"):
                    stack.extend(o)
        nodes = sum(len(ln.glyphs) for p in page209 for ln in p.lines)
        merged = sum(ln.merged for p in page209 for ln in p.lines)
        assert nodes + merged == chars

    def test_every_glyph_appears_in_exactly_one_span(self, page209):
        for p in page209:
            for ln in p.lines:
                ids = [gl.id for sp in ln.spans for gl in sp.glyphs]
                assert len(ids) == len(ln.glyphs)
                assert len(set(ids)) == len(ids)


@needs_corpus
class TestG3ProjectionIsTotal:
    def test_no_math_span_is_silently_dropped(self, page209):
        """Every maths span yields either LaTeX or an explicit deferral."""
        for p in page209:
            for ln in p.lines:
                for sp in ln.spans:
                    if sp.kind != "math":
                        continue
                    out = docmodel.span_text(sp)
                    assert out.startswith("$") or "DEFERRED" in out

    def test_deferral_carries_id_and_reason(self, page209):
        """Whatever cannot be projected says so, with id, rect and reason.

        The trigger is `span_latex() is None`, not `not flat`: since the
        structure pass landed, a span with scripts or a fraction is no longer
        flat yet is still projectable.
        """
        for p in page209:
            for ln in p.lines:
                for sp in ln.spans:
                    if sp.kind != "math":
                        continue
                    out = docmodel.span_text(sp)
                    if docmodel.span_latex(sp) is None:
                        assert sp.id in out and "reason=" in out
                    else:
                        assert out.startswith("$") and out.endswith("$")


class TestBaselineTrap:
    """A superscript must never be projected as if it were level."""

    def test_superscript_is_not_level(self):
        base = g("theta1", size=9.96, baseline=568.9, x=0)
        sup = g("alpha", size=6.97, baseline=572.0, x=6)
        assert not _is_level([base, sup])

    def test_subscript_is_not_level(self):
        base = g("T", size=9.96, baseline=500.0, x=0)
        sub = g("alpha", size=6.97, baseline=497.0, x=6)
        assert not _is_level([base, sub])

    def test_same_size_same_baseline_is_level(self):
        a = g("alpha", size=9.96, baseline=500.0, x=0)
        b = g("beta", size=9.96, baseline=500.0, x=6)
        assert _is_level([a, b])

    def test_size_alone_defeats_it(self):
        """Equal baselines but different sizes is still structure."""
        a = g("alpha", size=9.96, baseline=500.0, x=0)
        b = g("beta", size=6.97, baseline=500.0, x=6)
        assert not _is_level([a, b])

    def test_baseline_comes_from_the_matrix_not_the_box(self):
        n = g("alpha", size=7.0, baseline=123.5)
        assert n.baseline == 123.5 == n.matrix[5]


class TestScriptSpanTrap:
    """A span entirely smaller than its line is a script on a neighbour."""

    def test_small_span_defers(self):
        sup = g("alpha", size=6.97, baseline=600.0)
        sp = Span(id="s", kind="math", rect=sup.rect, glyphs=[sup],
                  line_size=9.96)
        assert not sp.flat, "a lone superscript must not project standalone"

    def test_full_size_span_projects(self):
        sym = g("alpha", size=9.96, baseline=600.0)
        sp = Span(id="s", kind="math", rect=sym.rect, glyphs=[sym],
                  line_size=9.96)
        assert sp.flat
        assert docmodel.span_text(sp) == r"$\alpha$"


@needs_corpus
class TestRulesBlockProjection:
    def test_a_span_with_a_rule_is_never_flat(self):
        sym = g("alpha", size=9.96, baseline=600.0)
        sp = Span(id="s", kind="math", rect=sym.rect, glyphs=[sym],
                  rules=[RuleNode(id="r", page=1, rect=(0, 0, 5, 0))],
                  line_size=9.96)
        assert not sp.flat

    def test_page209_fraction_bar_is_found_and_classified(self, page209):
        """The \\frac{1}{2} bar: an LTLine of zero height, glyphs both sides."""
        rules = [r for p in page209 for ln in p.lines for r in ln.rules]
        assert rules, "no rules captured"
        bar = [r for r in rules if abs(r.rect[0] - 251.7) < 0.5]
        assert bar, "the p209 fraction bar was not captured"
        assert bar[0].role == "fraction"
        assert bar[0].thickness == pytest.approx(0.0, abs=0.5)


class TestLiteralsInsideMath:
    def test_digits_and_operators_project_as_themselves(self):
        for ch in "0123456789+-=()[]/.,":
            n = g(None, family="text", text=ch)
            assert glyph_latex(n) == ch

    def test_upright_letter_becomes_mathrm(self):
        n = g(None, family="text", text="d")
        n.fontname = "ABC+CMR10"
        assert glyph_latex(n) == r"\mathrm{d}"

    def test_italic_letter_is_a_bare_variable(self):
        """Maths italic is the default, so a variable needs no wrapper.

        The font test is on the FACE name: TeX writes italic as `TI`/`MI`,
        never as the substring "it", so `endswith("it")` matched nothing and
        every Computer Modern variable was uprighted.
        """
        n = g(None, family="text", text="x")
        n.fontname = "ABC+CMTI10"
        assert glyph_latex(n) == "x"

    def test_unidentified_math_glyph_still_defers(self):
        """A text literal fallback must not rescue a MATHS glyph we failed
        to identify — that would hide the very residual we must report."""
        n = g("zzz-not-a-glyph", family="math-symbol")
        assert n.tex.latex is None
        assert glyph_latex(n) is None

    def test_unsafe_character_defers(self):
        for ch in ("%", "&", "#", "_", "^", "{", "}", "\\", "$"):
            n = g(None, family="text", text=ch)
            assert glyph_latex(n) is None, ch


@needs_corpus
class TestG5LimitCheck:
    def test_page_with_no_math_yields_only_text_spans(self, page209):
        """A line with no maths-family glyph and no rule is plain text."""
        for p in page209:
            for ln in p.lines:
                if ln.type == "text":
                    assert all(sp.kind == "text" for sp in ln.spans)
                    assert "$" not in docmodel.span_text(ln.spans[0])


class TestWordBreaks:
    def test_gaps_become_spaces(self):
        a = g(None, family="text", text="a", x=0.0, size=10.0)
        b = g(None, family="text", text="b", x=5.0, size=10.0)
        far = g(None, family="text", text="c", x=40.0, size=10.0)
        assert docmodel._run_text([a, b, far]) == "ab c"


class TestScriptPullsInItsBase:
    """A script proves its base is mathematics.

    `(e_2 e_3)^2` sets the bases in an italic TEXT font and the subscripts in
    a maths font. Splitting spans by font alone put base and script in
    different spans, and a script with no base in its span can never be
    attached -- so it deferred as a crop. On a dense page that was most of the
    line: page 29 of a Clifford-algebra text went from 74% projected with the
    output reading `( e` + two crops + `3)2`.
    """

    def test_base_and_subscript_share_a_span(self):
        from docmodel_six import LineNode, _spans
        base = g("e", family="text", size=10.0, baseline=100.0, x=0.0,
                 text="e")
        base.fontname = "ABC+CMTI10"
        sub = g("two", family="math-italic", size=7.0, baseline=97.0, x=5.0,
                text="2")
        line = LineNode(id="l", page=1, rect=(0, 90, 20, 112), type="formula",
                        glyphs=[base, sub])
        spans = line.spans
        math = [sp for sp in spans if sp.kind == "math"]
        assert len(math) == 1, [(s.kind, len(s.glyphs)) for s in spans]
        assert len(math[0].glyphs) == 2, "base and script must be together"

    def test_rotated_line_is_never_parsed_as_maths(self):
        """A stamp is text. Parsing it turns `arXiv:0805` into LaTeX."""
        from docmodel_six import LineNode, _spans
        gl = [g(None, family="text", size=8.0, baseline=100.0, x=float(i),
                text=c) for i, c in enumerate("arXiv:0805")]
        line = LineNode(id="r", page=1, rect=(0, 90, 20, 110), type="text",
                        glyphs=gl, rotated=True)
        spans = line.spans
        assert len(spans) == 1 and spans[0].kind == "text"


class TestDiagramRegions:
    """A commutative diagram is a REGION, not a line of text.

    Xy-pic draws one with no path operators at all: the arrow shaft is a dash
    glyph stamped repeatedly along the line (XYDASH) and the head is an
    arrow-tip glyph (XYATIP/XYBTIP). Left in the text flow those stamps
    scatter through the prose as `****\\ */`.
    """

    def _mark(self, x, y, font="XYDASH-Medium", size=10.0, text="\u25b2"):
        n = g(None, family="text", size=size, baseline=y, x=x, text=text)
        n.fontname = font
        n.rect = (x, y, x + 4.0, y + 4.0)
        return n

    def test_dash_stamps_become_one_region(self):
        from docmodel_six import _diagram_regions
        marks = [self._mark(100.0 + 4 * i, 200.0 - 2 * i) for i in range(11)]
        regions = _diagram_regions(marks)
        assert len(regions) == 1

    def test_labels_are_absorbed(self):
        from docmodel_six import _diagram_regions
        marks = [self._mark(100.0 + 4 * i, 200.0 - 2 * i) for i in range(11)]
        label = g("E", family="math-italic", size=12.0, baseline=205.0, x=95.0,
                  text="E")
        regions = _diagram_regions(marks + [label])
        assert len(regions) == 1
        x0, y0, x1, y1 = regions[0]
        assert x0 <= 95.0, "the label must be inside the region"

    def test_absorption_does_not_cascade(self):
        """Growing iteratively swallowed the whole page: a label extends the
        box, which then reaches further, and so on."""
        from docmodel_six import _diagram_regions
        marks = [self._mark(100.0 + 4 * i, 200.0 - 2 * i) for i in range(11)]
        far = [g("x", family="math-italic", size=10.0, baseline=200.0,
                 x=300.0 + 30 * i, text="x") for i in range(6)]
        regions = _diagram_regions(marks + far)
        assert regions[0][2] < 250.0, f"region ran away: {regions[0]}"

    def test_no_drawing_font_no_region(self):
        from docmodel_six import _diagram_regions
        plain = [g("alpha", family="math-italic", size=10.0, baseline=100.0,
                   x=float(i) * 6) for i in range(8)]
        assert _diagram_regions(plain) == []


class TestRuleRoleUsesBaselines:
    """A rule is classified by the BASELINES around it, not by box edges.

    An LTChar box is the advance box and spans the whole em, so the bar of an
    overline falls INSIDE the box of the letter it covers: the box is neither
    above nor below the bar, and every overline classified as "unknown".
    """

    def _rule(self, x0, x1, y):
        from docmodel_six import RuleNode
        return RuleNode(id="r", page=1, rect=(x0, y, x1, y))

    def test_overline_has_a_base_below_only(self):
        from docmodel_six import _rule_role
        base = g("x", family="math-italic", size=10.0, baseline=417.7, x=247.7)
        base.rect = (247.7, 417.7, 253.4, 427.7)      # box top is ABOVE the bar
        r = self._rule(247.7, 253.4, 425.85)
        assert _rule_role(r, [base], 10.0) == "overline"

    def test_fraction_has_both_sides(self):
        """Geometry from a real page: numerator +4.58, denominator -9.50."""
        from docmodel_six import _rule_role
        num = g(None, family="text", size=10.0, baseline=602.78, x=252.0,
                text="1")
        den = g(None, family="text", size=10.0, baseline=588.70, x=252.0,
                text="2")
        r = self._rule(251.7, 256.7, 598.2)
        assert _rule_role(r, [num, den], 10.0) == "fraction"

    def test_window_scales_with_type_size(self):
        """The window is VERTICAL, so it must scale by size, not by the
        rule's width -- a 5.7pt-wide overline once got a 14pt window."""
        from docmodel_six import _rule_role
        far = g("x", family="math-italic", size=10.0, baseline=300.0, x=247.7)
        r = self._rule(247.7, 253.4, 425.85)
        assert _rule_role(r, [far], 10.0) == "unknown"


class TestUnconsumedRulesDefer:
    def test_a_rule_that_is_not_a_fraction_blocks_projection(self):
        """Ignoring an unmodelled rule is how `\\overline{x}` became `x`."""
        import structure
        from docmodel_six import RuleNode
        a = g("alpha", family="math-italic", size=10.0, baseline=100.0, x=0.0)
        bar = RuleNode(id="r", page=1, rect=(0.0, 130.0, 5.0, 130.0),
                       role="unknown")
        assert structure.to_tex([a], [bar]) is None

    def test_overline_is_composed_not_dropped(self):
        import structure
        from docmodel_six import RuleNode
        x = g("x", family="math-italic", size=10.0, baseline=100.0, x=0.0)
        bar = RuleNode(id="r", page=1, rect=(0.0, 110.0, 5.0, 110.0),
                       role="overline")
        assert structure.to_tex([x], [bar]) == r"\overline{x}"


class TestFractionVersusOverline:
    """Distance alone cannot tell a numerator from the text line above.

    Measured on real pages, both at 12pt:
      real fraction   numerator +4.58   denominator -9.50
      real overline   text line  +4.57   base        -9.83
    The numbers agree to a tenth of a point. What separates them is EXTENT:
    TeX sets a fraction bar at least as wide as both parts, so a numerator is
    contained by the bar, while a text line runs clean across the page.
    """

    def _rule(self, x0, x1, y):
        from docmodel_six import RuleNode
        return RuleNode(id="r", page=1, rect=(x0, y, x1, y))

    def _row(self, baseline, xs, size=12.0):
        return [g(None, family="text", size=size, baseline=baseline,
                  x=x, text="o") for x in xs]

    def test_numerator_contained_by_the_bar_is_a_fraction(self):
        from docmodel_six import _rule_role
        bar = self._rule(251.7, 256.7, 598.2)
        num = self._row(602.78, [252.0])
        den = self._row(588.70, [252.0])
        assert _rule_role(bar, num + den, 12.0) == "fraction"

    def test_text_line_across_the_page_is_not_a_numerator(self):
        from docmodel_six import _rule_role
        bar = self._rule(300.0, 308.9, 400.0)
        # a running line at the same offset a numerator would occupy
        line_above = self._row(404.57, [200.0, 240.0, 300.0, 360.0, 420.0])
        base = self._row(390.17, [300.0])
        assert _rule_role(bar, line_above + base, 12.0) == "overline"

    def test_neither_side_gives_unknown(self):
        from docmodel_six import _rule_role
        bar = self._rule(300.0, 308.9, 400.0)
        assert _rule_role(bar, [], 12.0) == "unknown"

    def test_a_narrow_mark_under_a_wide_bar_is_not_its_base(self):
        """TeX draws an accent to the width of what it accents, so something
        far narrower than the bar is not what the bar covers."""
        from docmodel_six import _rule_role
        bar = self._rule(300.0, 340.0, 400.0)
        tiny = [g(None, family="text", size=12.0, baseline=390.0, x=302.0,
                  text=".")]
        tiny[0].rect = (302.0, 390.0, 303.0, 402.0)
        assert _rule_role(bar, tiny, 12.0) == "unknown"


class TestWordGapIsMeasured:
    """A fixed fraction of the type size does not survive justification."""

    def _run(self, widths_and_gaps, size=12.0):
        out, x = [], 0.0
        for w, gap in widths_and_gaps:
            n = g(None, family="text", size=size, baseline=100.0, x=x,
                  text="a")
            n.rect = (x, 100.0, x + w, 100.0 + size)
            out.append(n)
            x += w + gap
        return out

    def test_finds_the_bimodal_split(self):
        """Measured on a real 12pt line: within-word 0.07-0.87,
        between-word 2.04-4.92. The fixed 0.22em threshold was 2.64 --
        inside the word cluster, so `any quaternion` lost its space."""
        from docmodel_six import _word_gap
        run = self._run([(5, 0.1), (5, 0.1), (5, 2.6), (5, 0.1), (5, 2.6),
                         (5, 0.1), (5, 0.1), (5, 3.0)])
        wg = _word_gap(run)
        assert 0.9 < wg < 2.4, wg

    def test_touching_letters_do_not_defeat_it(self):
        """When letters touch, every gap is ~0 except the word spaces.
        Filtering those out left only word gaps and put the threshold ABOVE
        a real space -- `oneofthemaingoalsofthesenotes`."""
        from docmodel_six import _word_gap
        run = self._run([(5, 0.0), (5, 0.0), (5, 2.3), (5, 0.0), (5, 2.3),
                         (5, 0.0), (5, 0.0), (5, 2.3)])
        wg = _word_gap(run)
        assert wg < 2.3, wg

    def test_falls_back_when_there_is_no_split(self):
        from docmodel_six import _word_gap
        run = self._run([(5, 1.0)] * 8)
        assert _word_gap(run) == pytest.approx(0.22 * 12.0, abs=0.5)

    def test_spaces_appear_where_the_gaps_are(self):
        """Needs enough gaps to measure: under four the function documents
        a fallback to the fixed fraction, and says so."""
        from docmodel_six import _run_text, _word_gap
        run = self._run([(5, 0.1), (5, 0.1), (5, 2.6), (5, 0.1), (5, 2.6),
                         (5, 0.1), (5, 3.0)])
        assert _run_text(run, _word_gap(run)).count(" ") == 2


class TestTallGlyphsDoNotReachAcrossLines:
    """A CMEX radical descends far below its origin.

    Measured: `radicalbig` with baseline 272.28 -- the same line as the text
    at 276.72 -- but ink at y 244-256, thirty points lower. An x-gap test
    accepted it, and so did a baseline test, so the word `only` lost its `on`
    into a maths span whose crop then covered two lines of prose.
    """

    def _at(self, text, x0, x1, y0, y1, baseline, size=12.0, family="text"):
        n = g(None, family=family, size=size, baseline=baseline, x=x0,
              text=text)
        n.rect = (x0, y0, x1, y1)
        n.matrix = (size, 0, 0, size, x0, baseline)
        return n

    def test_run_on_the_line_below_is_not_absorbed(self):
        from docmodel_six import LineNode
        o = self._at("o", 192.0, 197.8, 273.7, 285.7, 276.72)
        n = self._at("n", 197.9, 204.4, 273.7, 285.7, 276.72)
        rad = self._at("", 202.0, 213.9, 244.1, 256.0, 272.28,
                       family="math-extension")
        rad.glyphname = "radicalbig"
        from texmap import project
        rad.tex = project("math-extension", "radicalbig")
        line = LineNode(id="l", page=1, rect=(190, 244, 215, 286),
                        type="formula", glyphs=[o, n, rad])
        for sp in line.spans:
            names = {gl.text for gl in sp.glyphs}
            assert not ({"o", "n"} <= names and len(sp.glyphs) > 2), \
                "text was absorbed by a glyph on another line"

    def test_overlapping_runs_still_absorb(self):
        """The guard must not block a genuine operator name."""
        from docmodel_six import LineNode
        c = self._at("C", 100.0, 106.0, 200.0, 212.0, 200.0)
        l = self._at("l", 106.0, 110.0, 200.0, 212.0, 200.0)
        sub = self._at("n", 110.5, 114.0, 198.0, 206.0, 197.0, size=8.0,
                       family="math-italic")
        sub.glyphname = "n"
        from texmap import project
        sub.tex = project("math-italic", "n")
        line = LineNode(id="l", page=1, rect=(99, 197, 115, 212),
                        type="formula", glyphs=[c, l, sub])
        math = [sp for sp in line.spans if sp.kind == "math"]
        assert math and len(math[0].glyphs) == 3


class TestFractionInsideAnExpression:
    """A fraction must rejoin the expression it sits inside.

    Its numerator and denominator are their own baseline rows, and the row
    carrying the rest of the formula has NO glyph under the bar -- the
    fraction occupies that column. Measured on a real display at 12pt:
    numerator 255.4, main row 247.3, denominator 239.2. Merging only the two
    halves left `1 12 2` as an orphan line beside a stranded
    `(1,0) |-> (1 (x) 1 + i (x) i)`.
    """

    def _g(self, text, x, baseline, size=12.0, family="text"):
        n = g(None, family=family, size=size, baseline=baseline, x=x,
              text=text)
        n.rect = (x, baseline, x + 6.0, baseline + size)
        n.matrix = (size, 0, 0, size, x, baseline)
        return n

    def test_host_row_is_merged_in(self):
        from docmodel_six import build  # noqa: F401  (documented behaviour)
        from docmodel_six import _dominant_size
        # three rows, as measured
        num = [self._g("1", 216.0, 255.4)]
        den = [self._g("2", 216.0, 239.2)]
        main = [self._g(c, 170.0 + 6 * i, 247.3)
                for i, c in enumerate("(1,0)")]
        assert _dominant_size(num + den + main) == 12.0
        # the host row has nothing under the bar at x 216-222
        assert not any(216.0 <= 0.5 * (n.rect[0] + n.rect[2]) <= 222.0
                       for n in main)

    def test_display_line_with_a_fraction_is_one_span(self):
        from docmodel_six import LineNode, RuleNode
        num = self._g("1", 216.0, 255.4)
        den = self._g("2", 216.0, 239.2)
        rest = [self._g(c, 170.0 + 6 * i, 247.3, family="math-italic")
                for i, c in enumerate("xy")]
        bar = RuleNode(id="r", page=1, rect=(216.0, 250.5, 222.0, 250.5),
                       role="fraction")
        line = LineNode(id="l", page=1, rect=(170, 239, 230, 268),
                        type="formula", glyphs=[num, den] + rest,
                        rules=[bar])
        spans = line.spans
        assert len(spans) == 1 and spans[0].kind == "math", \
            "x-ordered segmentation interleaves the two halves of a fraction"
        assert len(spans[0].glyphs) == 4


class TestWordGapIsOutlierRobust:
    """One huge gap must not define the word boundary.

    Measured on a line carrying an inline summation: gaps were ~0 between
    letters, 2.67-3.30 between words, and a single 15.22 beside the sum sign.
    Taking the largest jump picked 3.30 -> 15.22, the threshold clamped to its
    ceiling, and the line came out as
    `certainkindsof"polynomials,"linearcombinationsofmonomials`.
    """

    def _run(self, gaps, size=12.0):
        out, x = [], 0.0
        for gap in gaps + [0.0]:
            n = g(None, family="text", size=size, baseline=100.0, x=x,
                  text="a")
            n.rect = (x, 100.0, x + 5.0, 100.0 + size)
            out.append(n)
            x += 5.0 + gap
        return out

    def test_single_outlier_is_ignored(self):
        from docmodel_six import _word_gap
        gaps = [0.0] * 12 + [2.7, 0.0, 2.8, 0.0, 3.0, 0.0, 2.9, 0.0] + [15.2]
        wg = _word_gap(self._run(gaps))
        assert wg < 2.7, f"the outlier defined the split: {wg}"

    def test_spaces_survive_the_outlier(self):
        from docmodel_six import _run_text, _word_gap
        gaps = [0.0] * 12 + [2.7, 0.0, 2.8, 0.0, 3.0, 0.0, 2.9, 0.0] + [15.2]
        run = self._run(gaps)
        text = _run_text(run, _word_gap(run))
        assert text.count(" ") >= 4, text


class TestCmexBoxesAreRepaired:
    """pdfminer builds a glyph's box from the FONT's descent, not the glyph's.

    CMEX10 declares -2.359em because it carries the huge extensible pieces,
    so every big operator, radical and fence reports a box about 28pt below
    its ink. Measured: `summationtext` with origin y=503.4 reporting ink at
    475.2-487.2. That wrecks any test on the box -- and puts a deferred span's
    crop rectangle in the wrong place on the page.
    """

    def test_implausible_descent_is_replaced(self):
        from docmodel_six import _sane_rect
        fixed = _sane_rect((459.4, 475.2, 472.0, 487.2), 503.4, 12.0)
        assert fixed[0] == 459.4 and fixed[2] == 472.0, "x must not change"
        assert fixed[1] < 503.4 < fixed[3], "the box must straddle the origin"

    def test_ordinary_descent_is_left_alone(self):
        from docmodel_six import _sane_rect
        box = (100.0, 97.6, 106.0, 109.6)       # descent -0.2em at 12pt
        assert _sane_rect(box, 100.0, 12.0) == box


class TestRaisedBigOperators:
    """A big operator is raised so it and its limits centre on the maths axis.

    Measured: a `\\sum` at baseline 503.4 sitting between text rows at 508.8
    and 494.4, its own subscript at 490.9. By bare baseline it joined the
    UPPER row and turned `Cl(\\Phi)` into `C\\sum l(\\Phi)`; and the structure
    pass then saw a full-size glyph off the row and refused the span.
    """

    def _g(self, name, x, baseline, size=12.0, family="math-extension"):
        from texmap import project
        n = g(name, family=family, size=size, baseline=baseline, x=x)
        n.rect = (x, baseline - 0.3 * size, x + 12.6, baseline + size)
        n.matrix = (size, 0, 0, size, x, baseline)
        n.tex = project(family, name)
        return n

    def test_bigop_groups_with_the_lower_row(self):
        from docmodel_six import _group_lines
        upper = [g(None, family="text", size=12.0, baseline=508.8,
                   x=float(i) * 6, text="a") for i in range(5)]
        lower = [g(None, family="text", size=12.0, baseline=494.4,
                   x=float(i) * 6, text="b") for i in range(5)]
        sigma = self._g("summationtext", 459.4, 503.4)
        rows = _group_lines(upper + lower + [sigma])
        for r in rows:
            if sigma in r:
                assert all(x.baseline == 494.4 for x in r if x is not sigma)
                break
        else:
            raise AssertionError("the operator was not placed in a row")

    def test_bigop_takes_its_subscript(self):
        import structure
        sigma = self._g("summationtext", 459.4, 503.4)
        sub = g("J", family="math-italic", size=8.0, baseline=490.9,
                x=472.0)
        assert structure.to_tex([sigma, sub]) == r"\sum_{J}"


class TestOverlineEdges:
    def _rule(self, x0, x1, y, role="overline"):
        from docmodel_six import RuleNode
        return RuleNode(id="r", page=1, rect=(x0, y, x1, y), role=role)

    def test_bar_over_several_narrow_glyphs(self):
        """`\\overline{e_1 e_2 e_3}` covers six narrow glyphs.

        Requiring one glyph as wide as the bar found nothing under it and
        left the rule classified "unknown", which deferred the whole span.
        """
        from docmodel_six import _rule_role
        run = []
        for i in range(6):
            n = g(None, family="math-italic", size=10.0, baseline=199.4,
                  x=238.0 + 5.0 * i, text="e")
            n.rect = (238.0 + 5.0 * i, 199.4, 243.0 + 5.0 * i, 209.4)
            run.append(n)
        assert _rule_role(self._rule(238.3, 268.8, 206.0), run, 10.0) == "overline"

    def test_a_bar_below_the_baseline_is_not_this_line_s(self):
        """An overline goes ABOVE what it covers. Rules from the line below
        were being attached and deferring spans with no accent at all."""
        from docmodel_six import _rule_role
        n = g("x", family="math-italic", size=10.0, baseline=328.0, x=440.0)
        n.rect = (440.0, 328.0, 447.0, 338.0)
        # the bar sits 8pt BELOW this glyph's baseline
        assert _rule_role(self._rule(440.7, 447.5, 320.0), [n], 10.0) != "overline"


class TestTheOverlineIsHigherThanEightTenthsOfAnEm:
    r"""763 -- which LINE an overline belongs to, not which role it has.

    wzlxjtu-031's second display is

        A=\sum_{s=2}^{\infty}\sum_{|m|<s}A_m^sV_m^s \qquad
        \overline{A}=\sum_{s=2}^{\infty}\sum_{|m|<s}\overline{A}_m^sV_m^s.

    and both bars went missing, so the two halves came out identical. The
    rules were read and classified correctly; the line-assembly window is
    0.8 em from the baseline and TeX draws `\overline` above the HEIGHT of
    what it covers plus three rule thicknesses -- 10.13pt over a 10pt `A`.

    The way in is not a wider window but the bar's own geometry: it is drawn
    to the WIDTH OF THE BOX, so the rule spans exactly 177.50..184.97 over an
    `A` spanning exactly 177.50..184.97, a tenth of a point above its top.
    """

    def _A(self, x0=177.50, x1=184.97, baseline=611.30, size=10.0):
        n = g("A", family="math-italic", size=size, baseline=baseline, x=x0)
        n.rect = (x0, baseline, x1, baseline + size)
        return n

    def _rule(self, x0, x1, y, role="overline"):
        from docmodel_six import RuleNode
        return RuleNode(id="r", page=1, rect=(x0, y, x1, y), role=role)

    def _covers(self, rule, glyphs):
        from docmodel_six import _covers_as_overline
        return _covers_as_overline(rule, 0.5 * (rule.rect[1] + rule.rect[3]),
                                   glyphs)

    def test_the_bar_of_031_is_claimed(self):
        """10.13pt above the baseline: outside the 0.8 em window, and this
        is the measurement it was taken from."""
        assert self._covers(self._rule(177.50, 184.97, 621.43),
                            [self._A()]) is True

    def test_a_bar_wider_than_the_box_is_not_its_overline(self):
        """A fraction bar is as wide as the WIDER of the two groups, so one
        reaching past the glyph below it is covering something else."""
        assert self._covers(self._rule(170.0, 195.0, 621.43),
                            [self._A()]) is False

    def test_a_bar_on_the_maths_axis_is_not_an_overline(self):
        """Where a fraction bar lives: a quarter em above the BASELINE, and
        nowhere near the top of anything."""
        assert self._covers(self._rule(177.50, 184.97, 613.80),
                            [self._A()]) is False

    def test_the_classifier_still_has_the_last_word(self):
        """This decides WHICH LINE, never whether it is an accent. A rule
        `_rule_role` called a fraction stays one, wherever it sits."""
        assert self._covers(self._rule(177.50, 184.97, 621.43, "fraction"),
                            [self._A()]) is False

    def test_a_bar_far_above_the_box_belongs_to_the_line_above(self):
        assert self._covers(self._rule(177.50, 184.97, 627.0),
                            [self._A()]) is False


class TestAbsorptionOrder:
    """Neutral operators must be absorbed BEFORE operator names.

    An operator name takes the maths run beside it. If that happens first the
    chain breaks: in `Cl_{p+1,q}` the name `Cl` swallowed the `p`, so the
    `+1,` run no longer had maths on its left and was stranded -- `+1,q`
    deferred as its own crop next to a perfectly good `\\mathrm{Cl}_{p}`.
    """

    def _g(self, text, x, baseline, size, family, font="ABC+CMR10"):
        # A glyphname is required: absorption refuses to merge into a maths
        # run it cannot identify, which is the point of `_solid`.
        from texmap import project
        name = text if family.startswith("math") else None
        n = g(name, family=family, size=size, baseline=baseline, x=x,
              text=text)
        n.tex = project(family, name)
        n.rect = (x, baseline, x + 0.5 * size, baseline + size)
        n.matrix = (size, 0, 0, size, x, baseline)
        n.fontname = font
        return n

    def test_subscript_run_stays_whole(self):
        from docmodel_six import LineNode
        # Cl  p  +  1  ,  q   -- `Cl` roman, scripts at 8pt
        gl = [self._g("C", 100.0, 200.0, 12.0, "text"),
              self._g("l", 106.0, 200.0, 12.0, "text"),
              self._g("p", 112.0, 197.0, 8.0, "math-italic",
                      "ABC+CMMI8"),
              self._g("+", 116.5, 197.0, 8.0, "text"),
              self._g("1", 121.0, 197.0, 8.0, "text"),
              self._g(",", 125.0, 197.0, 8.0, "text"),
              self._g("q", 128.5, 197.0, 8.0, "math-italic",
                      "ABC+CMMI8")]
        line = LineNode(id="l", page=1, rect=(99, 197, 135, 212),
                        type="formula", glyphs=gl)
        math = [sp for sp in line.spans if sp.kind == "math"]
        assert len(math) == 1, [(s.kind, len(s.glyphs)) for s in line.spans]
        assert len(math[0].glyphs) == len(gl), \
            "the subscript run was split away from its base"


class TestFenceFragmentsBlockProjection:
    """A fence fragment is HALF a bracket. It must not be silently dropped.

    Setting structural orphans aside stopped them breaking words, but it also
    stopped them blocking projection: a matrix then emitted as `\\{ ( ) \\}`
    with its entries scattered beside it. Nonsense is worse than a crop.
    """

    def _g(self, text, x, baseline, size=12.0, family="text", name=None):
        from texmap import project
        n = g(name, family=family, size=size, baseline=baseline, x=x,
              text=text)
        n.rect = (x, baseline, x + 0.5 * size, baseline + size)
        n.matrix = (size, 0, 0, size, x, baseline)
        n.tex = project(family, name)
        return n

    def test_adjacent_fragment_makes_its_span_defer(self):
        from docmodel_six import LineNode, span_latex
        piece = self._g("", 112.0, 200.0, family="math-extension",
                        name="vextendsingle")
        assert piece.tex.kind == "fragment"
        x = self._g("X", 100.0, 200.0, family="math-italic", name="X")
        line = LineNode(id="l", page=1, rect=(99, 199, 120, 213),
                        type="formula", glyphs=[x, piece])
        math = [sp for sp in line.spans if sp.kind == "math"]
        assert math, "expected a maths span"
        assert any(span_latex(sp) is None for sp in math), \
            "a fence fragment must block projection of its span"

    def test_distant_fragment_does_not_poison_a_run(self):
        """A radical from another row abuts nothing here; attaching it to the
        nearest maths run made that span defer and its crop cover prose."""
        from docmodel_six import LineNode, span_latex
        far = self._g("", 400.0, 200.0, family="math-extension",
                      name="vextendsingle")
        x = self._g("X", 100.0, 200.0, family="math-italic", name="X")
        line = LineNode(id="l", page=1, rect=(99, 199, 410, 213),
                        type="formula", glyphs=[x, far])
        for sp in line.spans:
            if sp.kind == "math" and len(sp.glyphs) == 1 \
                    and sp.glyphs[0] is x:
                assert span_latex(sp) == "X"
                return
        raise AssertionError("the distant fragment was merged into the run")


class TestDiagramDetectionScales:
    """Clustering must not be all-pairs.

    One page of an InDesign book carries 30,065 LTCurve objects -- a dense
    vector plot. Comparing every mark against every cluster member took 28
    seconds for that single page and made a 531-page document impossible to
    convert.
    """

    def test_many_marks_are_clustered_quickly(self):
        import time

        from docmodel_six import _diagram_regions
        marks = [(100.0 + (i % 200) * 0.5, 200.0 + (i // 200) * 0.5,
                  100.5 + (i % 200) * 0.5, 200.5 + (i // 200) * 0.5)
                 for i in range(20000)]
        t = time.time()
        regions = _diagram_regions([], marks)
        assert time.time() - t < 5.0, "clustering did not scale"
        assert len(regions) == 1


class TestFramesAreNotFigures:
    """A framed code listing is not a diagram.

    Measured: 7 marks (four rules and rounded corners) around 850 glyphs of
    code. Treating it as a figure removes the whole listing from the document.
    A real figure is the other way round -- many strokes, few labels.
    """

    def _glyphs(self, n, x0=100.0, y0=200.0):
        out = []
        for i in range(n):
            gl = g(None, family="text", size=9.0, baseline=y0 + (i // 40) * 11,
                   x=x0 + (i % 40) * 5.0, text="a")
            gl.rect = (gl.rect[0], gl.rect[1], gl.rect[0] + 4.0,
                       gl.rect[1] + 9.0)
            out.append(gl)
        return out

    def test_frame_around_text_is_rejected(self):
        from docmodel_six import _diagram_regions
        text = self._glyphs(850)
        frame = [(95.0, 195.0, 100.0, 440.0), (300.0, 195.0, 305.0, 440.0),
                 (95.0, 195.0, 305.0, 200.0), (95.0, 435.0, 305.0, 440.0),
                 (96.0, 196.0, 99.0, 199.0), (301.0, 196.0, 304.0, 199.0),
                 (96.0, 436.0, 99.0, 439.0)]
        assert _diagram_regions(text, frame) == []

    def test_a_sliver_is_rejected(self):
        from docmodel_six import _diagram_regions
        sliver = [(100.0, 200.0, 103.0, 300.0), (100.5, 210.0, 103.0, 320.0),
                  (100.0, 220.0, 102.0, 340.0)]
        assert _diagram_regions([], sliver) == []

    def test_a_real_figure_survives(self):
        from docmodel_six import _diagram_regions
        strokes = [(200.0 + i * 2.0, 300.0 + (i % 7) * 3.0,
                    204.0 + i * 2.0, 306.0 + (i % 7) * 3.0)
                   for i in range(40)]
        labels = self._glyphs(6, x0=200.0, y0=300.0)
        assert len(_diagram_regions(labels, strokes)) == 1


class TestSmallerBlocksKeepTheirOwnRows:
    """A legitimate smaller block must not be swallowed by the body rows.

    The anchor threshold is relative to the PAGE's dominant size, so a 9pt
    code listing on a 10pt page anchors nothing. Every one of its glyphs was
    then assigned to whichever body row was nearest, collapsing ten lines of
    code into one and sorting them by x:
    `L1234istinaap1U(grrnr:1riir5:1anta,...`
    """

    def _row(self, baseline, n, size, x0=100.0):
        out = []
        for i in range(n):
            gl = g(None, family="text", size=size, baseline=baseline,
                   x=x0 + i * 5.0, text="a")
            gl.rect = (gl.rect[0], baseline, gl.rect[0] + 4.0,
                       baseline + size)
            gl.matrix = (size, 0, 0, size, gl.rect[0], baseline)
            out.append(gl)
        return out

    def test_listing_rows_stay_separate(self):
        from docmodel_six import _group_lines
        body = (self._row(700.0, 40, 10.0) + self._row(688.0, 40, 10.0))
        listing = (self._row(600.0, 30, 9.0) + self._row(589.0, 30, 9.0)
                   + self._row(578.0, 30, 9.0))
        rows = _group_lines(body + listing)
        small = [r for r in rows if all(x.size == 9.0 for x in r)]
        assert len(small) == 3, f"{len(small)} rows for 3 listing lines"

    def test_scripts_still_join_their_base(self):
        """The fix must not turn every subscript into its own row."""
        from docmodel_six import _group_lines
        base = self._row(500.0, 10, 12.0)
        sub = self._row(497.0, 1, 8.0, x0=150.0)
        rows = _group_lines(base + sub)
        assert len(rows) == 1, "a subscript became its own row"


class TestWideRulesAreNotFractions:
    """A frame rule is not a fraction bar.

    The border of a code listing runs the width of the text block with code
    above and below it -- exactly a fraction's geometry. Merging those rows
    glued consecutive code lines together:
    `5 f2(x) = f(x,2)67 xVals, yVals = -5:0.1:5`.
    """

    def test_a_frame_width_rule_is_a_separator(self):
        from docmodel_six import RuleNode, _rule_role
        above = g(None, family="text", size=9.0, baseline=306.0, x=100.0,
                  text="a")
        below = g(None, family="text", size=9.0, baseline=294.0, x=100.0,
                  text="b")
        frame = RuleNode(id="r", page=1, rect=(72.0, 300.0, 540.0, 300.5))
        assert _rule_role(frame, [above, below], 9.0) == "separator"

    def test_a_real_fraction_bar_still_classifies(self):
        from docmodel_six import RuleNode, _rule_role
        num = g(None, family="text", size=12.0, baseline=602.78, x=252.0,
                text="1")
        den = g(None, family="text", size=12.0, baseline=588.70, x=252.0,
                text="2")
        bar = RuleNode(id="r", page=1, rect=(251.7, 598.2, 256.7, 598.2))
        assert _rule_role(bar, [num, den], 12.0) == "fraction"


class TestRowClusteringDoesNotDrift:
    """Cluster against a row's ANCHOR, not a running mean.

    A mean drifts as glyphs join: one 2.5pt below pulls it down, the next
    2.5pt below that still fits, and the chain walks from one line into the
    next.
    """

    def test_evenly_spaced_lines_stay_separate(self):
        from docmodel_six import _group_lines
        gl = []
        for row in range(6):
            base = 600.0 - row * 11.0
            for i in range(20):
                n = g(None, family="text", size=9.0, baseline=base,
                      x=100.0 + i * 5.0, text="a")
                n.rect = (n.rect[0], base, n.rect[0] + 4.0, base + 9.0)
                n.matrix = (9.0, 0, 0, 9.0, n.rect[0], base)
                gl.append(n)
        assert len(_group_lines(gl)) == 6


class TestGluedRelationsArePunctuation:
    """A relation with NO SPACE either side is punctuation, not mathematics.

    `a < b` is a comparison. `<omtext` is the start of an XML tag -- and this
    book sets its listings in small ROMAN, so the `<` arrives from the maths
    font because OT1 has no angle brackets. Projected as mathematics the
    listing became `$<$ omtext xml:id="foo" $>$`.
    """

    def _g(self, text, x, size=7.0, family="text", width=3.5):
        n = g(None, family=family, size=size, baseline=100.0, x=x, text=text)
        n.rect = (x, 100.0, x + width, 100.0 + size)
        n.matrix = (size, 0, 0, size, x, 100.0)
        return n

    def _line(self, glyphs):
        from docmodel_six import LineNode
        return LineNode(id="l", page=1,
                        rect=(glyphs[0].rect[0], 99.0,
                              glyphs[-1].rect[2], 108.0),
                        type="text", glyphs=glyphs)

    def test_tag_opener_stays_text(self):
        gl = [self._g("<", 100.0, family="math-symbol")]
        gl += [self._g(c, 103.5 + i * 3.5) for i, c in enumerate("omtext")]
        gl += [self._g(c, 124.5 + i * 3.5) for i, c in enumerate("  xmlid")]
        line = self._line(gl)
        assert all(sp.kind == "text" for sp in line.spans), \
            [(s.kind, "".join(x.text for x in s.glyphs)) for s in line.spans]

    def test_adjacent_relations_stay_text(self):
        """`><` between two tags is two relation glyphs side by side."""
        gl = [self._g(c, 100.0 + i * 3.5) for i, c in enumerate("OMOBJ")]
        gl.append(self._g(">", 117.5, family="math-symbol"))
        gl.append(self._g("<", 121.0, family="math-symbol"))
        gl += [self._g(c, 124.5 + i * 3.5) for i, c in enumerate("omOMS")]
        line = self._line(gl)
        assert all(sp.kind == "text" for sp in line.spans)

    def test_a_spaced_comparison_is_still_maths(self):
        """The whole point of the rule is the space."""
        a = self._g("a", 100.0, size=10.0, family="math-italic", width=5.0)
        lt = self._g("<", 112.0, size=10.0, family="math-symbol", width=5.0)
        b = self._g("b", 124.0, size=10.0, family="math-italic", width=5.0)
        line = self._line([a, lt, b])
        assert any(sp.kind == "math" for sp in line.spans)


class TestVerbatimLines:
    """A line set in a typewriter face is literal, not mathematics.

    Measured across the corpus: 1003 such lines in a Julia textbook (its code
    listings), 66 in a markup textbook, 1 in a Clifford-algebra text (an
    e-mail address in CMTT12). Each is content that must not be parsed as
    maths -- `array1[2n+1]` is code, not a subscripted product.
    """

    def _g(self, text, x, font, size=9.0, family="text"):
        n = g(None, family=family, size=size, baseline=100.0, x=x, text=text)
        n.rect = (x, 100.0, x + 5.0, 100.0 + size)
        n.matrix = (size, 0, 0, size, x, 100.0)
        n.fontname = font
        return n

    def _line(self, glyphs):
        from docmodel_six import LineNode
        return LineNode(id="l", page=1, rect=(0, 99, 400, 110),
                        type="text", glyphs=glyphs)

    def test_typewriter_line_is_verbatim(self):
        gl = [self._g(c, 100.0 + i * 5.0, "ABC+CMTT9")
              for i, c in enumerate("array1")]
        assert self._line(gl).verbatim

    def test_roman_line_is_not(self):
        gl = [self._g(c, 100.0 + i * 5.0, "ABC+CMR10")
              for i, c in enumerate("theorem")]
        assert not self._line(gl).verbatim

    def test_borrowed_punctuation_does_not_hide_the_face(self):
        """Judged on LETTERS: a listing's punctuation is borrowed from other
        fonts, and counting those would mask the monospace body."""
        gl = [self._g(c, 100.0 + i * 5.0, "ABC+CMTT9")
              for i, c in enumerate("xy")]
        gl += [self._g(c, 120.0 + j * 5.0, "ABC+CMMI7",
                       family="math-italic")
               for j, c in enumerate("<>=+-")]
        gl += [self._g(c, 150.0 + i * 5.0, "ABC+CMTT9")
               for i, c in enumerate("ab")]
        assert self._line(gl).verbatim

    def test_a_verbatim_line_yields_one_text_span(self):
        gl = [self._g(c, 100.0 + i * 5.0, "ABC+CMTT9")
              for i, c in enumerate("f(x)")]
        gl += [self._g("2", 125.0, "ABC+CMMI7", size=6.0,
                       family="math-italic")]
        spans = self._line(gl).spans
        assert len(spans) == 1 and spans[0].kind == "text", \
            [(s.kind, len(s.glyphs)) for s in spans]

    def test_too_few_letters_to_judge(self):
        gl = [self._g("x", 100.0, "ABC+CMTT9")]
        assert not self._line(gl).verbatim


class TestListingFrames:
    """A framed code listing is not mathematics and not a figure."""

    def test_a_vertical_rule_is_a_separator(self):
        """A frame edge draws a zero-width, line-high rule once PER LINE --
        76 on one page -- and each was an unmodelled rule that made every
        span on the page defer."""
        from docmodel_six import RuleNode, _rule_role
        edge = RuleNode(id="r", page=1, rect=(108.0, 300.0, 108.0, 311.0))
        assert _rule_role(edge, [], 10.0) == "separator"

    def test_separators_neither_compose_nor_block(self):
        import structure
        from docmodel_six import RuleNode
        a = g("alpha", family="math-italic", size=10.0, baseline=300.0,
              x=120.0)
        edge = RuleNode(id="r", page=1, rect=(108.0, 300.0, 108.0, 311.0),
                        role="separator")
        assert structure.to_tex([a], [edge]) == r"\alpha"

    def test_frame_marks_do_not_make_it_a_figure(self):
        """The per-line rules inflated the mark count, so the frame test
        stopped recognising a listing box as a frame."""
        from docmodel_six import _diagram_regions
        text = []
        for i in range(200):
            gl = g(None, family="text", size=9.0,
                   baseline=400.0 - (i // 20) * 11.0,
                   x=120.0 + (i % 20) * 6.0, text="a")
            gl.rect = (gl.rect[0], gl.rect[1], gl.rect[0] + 5.0,
                       gl.rect[1] + 9.0)
            text.append(gl)
        marks = [(108.0, 290.0 + i * 11.0, 108.0, 301.0 + i * 11.0)
                 for i in range(10)]                    # per-line edges
        marks += [(108.0, 285.0, 112.0, 289.0), (250.0, 285.0, 254.0, 289.0)]
        assert _diagram_regions(text, marks) == []


class TestMonospaceIsNeverMaths:
    def test_typewriter_glyph_forced_to_text(self):
        from docmodel_six import LineNode
        gl = []
        for i, c in enumerate("fermion"):
            n = g(None, family="text", size=10.9, baseline=373.2,
                  x=100.0 + i * 6.0, text=c)
            n.fontname = "ABC+NimbusMonL-Regu"
            n.rect = (n.rect[0], 373.2, n.rect[0] + 5.0, 384.0)
            gl.append(n)
        sub = g("s", family="math-italic", size=8.0, baseline=370.0,
                x=145.0)
        line = LineNode(id="l", page=1, rect=(99, 369, 160, 385),
                        type="text", glyphs=gl + [sub])
        mono_spans = [sp for sp in line.spans
                      if any(x.fontname.endswith("Regu") for x in sp.glyphs)]
        assert all(sp.kind == "text" for sp in mono_spans)


class TestColumnLayout:
    """A two-column page must not be read across the gutter.

    Measured on an IEEE-format paper: a table row in the left column and a
    listing line in the right arrived as one row, sorted together by x --
    `GPU code generation Yes No Yes Yes Yes 45 Computation bx(i, j, c)`.
    """

    def _row(self, x0, n, baseline, size=9.0):
        out = []
        for i in range(n):
            gl = g(None, family="text", size=size, baseline=baseline,
                   x=x0 + i * 5.0, text="a")
            gl.rect = (gl.rect[0], baseline, gl.rect[0] + 4.0, baseline + size)
            gl.matrix = (size, 0, 0, size, gl.rect[0], baseline)
            out.append(gl)
        return out

    def _two_column_rows(self):
        rows = []
        for k in range(12):
            y = 700.0 - k * 12.0
            rows.append(self._row(48.0, 40, y))
            rows.append(self._row(320.0, 40, y))
        return rows

    def test_edge_is_found(self):
        """The boundary must lie BETWEEN the columns -- that is the property
        that matters, not any particular coordinate."""
        from docmodel_six import _column_edge
        rows = self._two_column_rows()
        edge = _column_edge(rows, (0, 0, 612, 792))
        assert edge is not None
        left_end = max(g.rect[2] for g in rows[0])
        right_start = min(g.rect[0] for g in rows[1])
        assert left_end <= edge <= right_start, (left_end, edge, right_start)

    def test_single_column_has_no_edge(self):
        from docmodel_six import _column_edge
        rows = [self._row(48.0, 60, 700.0 - k * 12.0) for k in range(12)]
        assert _column_edge(rows, (0, 0, 612, 792)) is None

    def test_straddling_row_is_split(self):
        from docmodel_six import _column_edge, _split_at_columns
        rows = self._two_column_rows()
        merged = rows[0] + rows[1]
        edge = _column_edge(rows, (0, 0, 612, 792))
        out = _split_at_columns([merged], edge)
        assert len(out) == 2, "a row spanning both columns was not split"

    def test_full_width_row_is_left_whole(self):
        """A title or caption runs straight across and must stay one row."""
        from docmodel_six import _column_edge, _split_at_columns
        rows = self._two_column_rows()
        edge = _column_edge(rows, (0, 0, 612, 792))
        wide = self._row(48.0, 100, 740.0)          # crosses the boundary
        out = _split_at_columns([wide], edge)
        assert len(out) == 1, "a full-width row was split"


class TestSmallCapsStayOnTheirLine:
    """Small caps share the BASELINE of the word; only font and size differ.

    `\\textsc{Tiramisu}` is a 10pt `T` followed by 8pt uppercase letters in
    another font. With the row window scaled at 0.3em, the 10pt glyph's window
    was 3.0pt -- wider than the 2.887pt offset between two columns' baselines
    on that page -- so the `T` jumped to the other column's row while the 8pt
    letters stayed, splitting the word across two lines:

        not only does T
        IRAMISU introduce novel
    """

    def _g(self, text, x, baseline, size):
        n = g(None, family="text", size=size, baseline=baseline, x=x,
              text=text)
        n.rect = (x, baseline, x + 0.5 * size, baseline + size)
        n.matrix = (size, 0, 0, size, x, baseline)
        return n

    def test_small_caps_stay_with_their_word(self):
        from docmodel_six import _group_lines
        # the word, on one baseline, in two sizes
        word = [self._g("T", 100.0, 120.489, 10.0)]
        word += [self._g(c, 106.0 + i * 5.0, 120.489, 8.0)
                 for i, c in enumerate("IRAMISU")]
        # another column's line, 2.887pt away -- inside the old window
        other = [self._g(c, 330.0 + i * 5.0, 123.376, 10.0)
                 for i, c in enumerate("of the polyhedral model")]
        rows = _group_lines(word + other)
        for r in rows:
            texts = {x.text for x in r}
            if "T" in texts and any(x.size == 8.0 for x in r):
                assert len([x for x in r if x.size == 8.0]) == 7
                assert all(x.baseline == 120.489 for x in r), \
                    "the word was merged with the other column's line"
                return
        raise AssertionError("the word was split across rows")

    def test_columns_at_different_baselines_stay_apart(self):
        from docmodel_six import _group_lines
        left = [self._g(c, 100.0 + i * 5.0, 120.489, 10.0)
                for i, c in enumerate("left column")]
        right = [self._g(c, 330.0 + i * 5.0, 123.376, 10.0)
                 for i, c in enumerate("right column")]
        rows = _group_lines(left + right)
        assert len(rows) == 2, f"{len(rows)} rows for two offset columns"


class TestColumnsDoNotShareBaselines:
    """Two columns of the same paper sit on DIFFERENT baselines.

    Measured on one paper: 2.887pt apart on one page, 1.0pt on another. The
    row window must be tighter than the smaller of those, or the LARGER
    glyphs of a small-caps word reach the neighbouring column while the
    smaller ones stay, tearing the word at the font change:

        II. R          not only does T
        ELATED WORK    IRAMISU introduce
    """

    def _g(self, text, x, baseline, size):
        n = g(None, family="text", size=size, baseline=baseline, x=x,
              text=text)
        n.rect = (x, baseline, x + 0.5 * size, baseline + size)
        n.matrix = (size, 0, 0, size, x, baseline)
        return n

    def test_one_point_offset_keeps_columns_apart(self):
        """The tighter of the two measured offsets."""
        from docmodel_six import _group_lines
        heading = [self._g("I", 394.7, 660.135, 9.96),
                   self._g("I", 398.5, 660.135, 9.96),
                   self._g("R", 410.3, 660.135, 9.96)]
        heading += [self._g(c, 417.5 + i * 5.0, 660.135, 7.97)
                    for i, c in enumerate("ELATED")]
        left = [self._g(c, 59.0 + i * 5.0, 659.135, 9.96)
                for i, c in enumerate("In this paper we introduce")]
        rows = _group_lines(heading + left)
        for r in rows:
            base = {round(x.baseline, 3) for x in r}
            assert len(base) == 1, f"row spans baselines {base}"

    def test_small_caps_word_survives_a_near_column(self):
        from docmodel_six import _group_lines
        heading = [self._g("R", 410.3, 660.135, 9.96)]
        heading += [self._g(c, 417.5 + i * 5.0, 660.135, 7.97)
                    for i, c in enumerate("ELATED")]
        left = [self._g(c, 59.0 + i * 5.0, 659.135, 9.96)
                for i, c in enumerate("some other column text here")]
        rows = _group_lines(heading + left)
        for r in rows:
            if any(x.text == "R" for x in r):
                assert len(r) == 7, "the small-caps word was torn"
                return
        raise AssertionError("the heading row was not found")


class TestCaptionsAreNotAbsorbedByFigures:
    """A figure's LABEL sits inside it; a CAPTION is a line of the document.

    Absorbing one glyph of a caption drags the whole middle of that line into
    the region, where it is removed from the text flow. Measured: a caption
    came out as `Fig. 6: A heatma`, the rest lost inside the picture.
    """

    def _g(self, text, x, baseline, size=10.0):
        n = g(None, family="text", size=size, baseline=baseline, x=x,
              text=text)
        n.rect = (x, baseline, x + 5.0, baseline + size)
        n.matrix = (size, 0, 0, size, x, baseline)
        return n

    def test_caption_running_past_the_figure_is_left_out(self):
        from docmodel_six import _diagram_regions
        strokes = [(200.0 + i * 3.0, 600.0 + (i % 5) * 4.0,
                    204.0 + i * 3.0, 606.0 + (i % 5) * 4.0)
                   for i in range(40)]
        # a caption line spanning far wider than the figure
        caption = [self._g("x", 49.0 + i * 6.0, 574.0)
                   for i in range(85)]
        regions = _diagram_regions(caption, strokes)
        assert regions, "the figure was not detected"
        x0, y0, x1, y1 = regions[0]
        assert x0 > 100.0, f"the region swallowed the caption: {regions[0]}"

    def test_a_real_label_inside_the_figure_is_absorbed(self):
        from docmodel_six import _diagram_regions
        strokes = [(200.0 + i * 3.0, 600.0 + (i % 5) * 4.0,
                    204.0 + i * 3.0, 606.0 + (i % 5) * 4.0)
                   for i in range(40)]
        label = [self._g(c, 210.0 + i * 6.0, 596.0)
                 for i, c in enumerate("axis")]
        regions = _diagram_regions(label, strokes)
        assert regions
        assert regions[0][1] <= 596.0, "the label was not absorbed"


class TestBandReadingOrder:
    """A full-width element ENDS the two-column region above it.

    Sorting by (column, y) over the whole page ignores that, so a figure high
    in the right column of a LOWER band was emitted after every line of the
    left column: Figure 7's caption arrived two paragraphs late, exactly the
    height of the figure.
    """

    def _row(self, x0, x1, y, page=1):
        from docmodel_six import LineNode
        gl = []
        x = x0
        while x < x1:
            n = g(None, family="text", size=10.0, baseline=y, x=x, text="a")
            n.rect = (x, y, min(x + 5.0, x1), y + 10.0)
            n.matrix = (10.0, 0, 0, 10.0, x, y)
            gl.append(n)
            x += 5.0
        return LineNode(id=f"l{x0}-{y}", page=page,
                        rect=(x0, y, x1, y + 10.0), type="text", glyphs=gl)

    def test_full_width_row_closes_the_band(self):
        """Left column, right column, then a full-width caption, then the
        next band -- not all left columns followed by all right columns."""
        rows = [self._row(48, 300, 700), self._row(320, 563, 700),
                self._row(48, 563, 660),                 # full width
                self._row(48, 300, 600), self._row(320, 563, 600)]
        lefts = [r.rect[0] for r in rows]
        rights = [r.rect[2] for r in rows]
        tw = max(rights) - min(lefts)
        mid = 0.5 * (min(lefts) + max(rights))

        def col(ln):
            if (ln.rect[2] - ln.rect[0]) > 0.7 * tw:
                return 2
            return 0 if 0.5 * (ln.rect[0] + ln.rect[2]) < mid else 1

        assert [col(r) for r in rows] == [0, 1, 2, 0, 1]

    def test_a_wide_row_is_full_width(self):
        rows = [self._row(48, 300, 700), self._row(320, 563, 700),
                self._row(48, 563, 660)]
        wide = rows[2]
        tw = 563 - 48
        assert (wide.rect[2] - wide.rect[0]) > 0.7 * tw

    def test_a_column_row_is_not(self):
        row = self._row(48, 300, 700)
        tw = 563 - 48
        assert (row.rect[2] - row.rect[0]) <= 0.7 * tw


class TestStreamSeparatesPanels:
    """Two panels of a figure can share a baseline, size and font.

    Geometry cannot tell them apart -- scheduling commands beside the code
    they generate, both 8pt, both on baseline 487.79. The content stream can:
    it says they were emitted hundreds of positions apart and were never part
    of the same run. Sorting them by (column, y) interleaves them:

        1 // Scheduling commands for targeting 8 int i = i0*32+i1
    """

    def _g(self, text, x, baseline, stream, size=8.0):
        n = g(None, family="text", size=size, baseline=baseline, x=x,
              text=text)
        n.rect = (x, baseline, x + 4.0, baseline + size)
        n.matrix = (size, 0, 0, size, x, baseline)
        n.stream = stream
        return n

    def test_a_row_spanning_two_runs_is_split(self):
        """Both conditions: the run changes AND the page shows a space."""
        from docmodel_six import _split_by_stream
        left = [self._g(c, 60.0 + i * 5.0, 480.0, 100 + i)
                for i, c in enumerate("panelA")]
        right = [self._g(c, 320.0 + i * 5.0, 480.0, 900 + i)
                 for i, c in enumerate("panelB")]
        out = _split_by_stream([left + right])
        assert len(out) == 2, [len(r) for r in out]
        assert {x.stream for x in out[0]} != {x.stream for x in out[1]}

    def test_a_genuine_line_is_not_split(self):
        """Within a real line the producer emits glyphs consecutively."""
        from docmodel_six import _split_by_stream
        row = [self._g(c, 60.0 + i * 5.0, 480.0, 100 + i)
               for i, c in enumerate("one continuous line of text")]
        assert len(_split_by_stream([row])) == 1

    def test_rows_without_stream_data_are_untouched(self):
        from docmodel_six import _split_by_stream
        row = [self._g(c, 60.0 + i * 5.0, 480.0, -1)
               for i, c in enumerate("no stream")]
        assert len(_split_by_stream([row])) == 1

    def test_line_reports_its_earliest_stream_position(self):
        from docmodel_six import LineNode
        gl = [self._g("a", 60.0, 480.0, 500),
              self._g("b", 65.0, 480.0, 300),
              self._g("c", 70.0, 480.0, 400)]
        ln = LineNode(id="l", page=1, rect=(60, 480, 74, 488),
                      type="text", glyphs=gl)
        assert ln.stream == 300

    def test_a_stream_jump_without_a_gap_does_not_split(self):
        """A display equation legitimately jumps in the stream while staying
        one line. Splitting on that alone cost 16 extra crops."""
        from docmodel_six import _split_by_stream
        row = [self._g("a", 60.0, 480.0, 100), self._g("b", 64.5, 480.0, 900)]
        assert len(_split_by_stream([row])) == 1

    def test_a_gap_without_a_stream_jump_does_not_split(self):
        """A listing's line-number gutter is its own stream run but sits
        close to its code; splitting there cut the numbers off."""
        from docmodel_six import _split_by_stream
        row = [self._g("1", 60.0, 480.0, 100),
               self._g("x", 100.0, 480.0, 101)]
        assert len(_split_by_stream([row])) == 1

    def test_a_gutter_is_never_split_from_its_code(self):
        """A listing's line number and its code are ONE line, however far
        apart they sit and however separately they were emitted.

        Measured: a gutter 34pt from its code, emitted 1460 stream positions
        earlier, was split off -- five lines came out as bare numbers with
        their code in a fence of its own.
        """
        from docmodel_six import _split_by_stream
        num = self._g("26", 314.0, 204.0, 1418, size=4.98)
        num.fontname = "ABC+NimbusRomNo9L-Regu"
        code = []
        x = 353.0
        for i, c in enumerate("for (c in 0..3)"):
            gl = self._g(c, x, 204.0, 2878 + i, size=7.97)
            gl.fontname = "ABC+NimbusMonL-Regu"
            code.append(gl)
            x += 4.0
        assert len(_split_by_stream([[num] + code])) == 1

    def test_two_panels_are_still_split(self):
        """The gutter exception must not reopen the panel case: both sides
        of a panel boundary are monospace."""
        from docmodel_six import _split_by_stream
        left, right = [], []
        for i, c in enumerate("panelA"):
            gl = self._g(c, 60.0 + i * 5.0, 480.0, 100 + i)
            gl.fontname = "ABC+NimbusMonL-Regu"
            left.append(gl)
        for i, c in enumerate("panelB"):
            gl = self._g(c, 320.0 + i * 5.0, 480.0, 900 + i)
            gl.fontname = "ABC+NimbusMonL-Regu"
            right.append(gl)
        assert len(_split_by_stream([left + right])) == 2


class TestSpaceIsNotAnUnmappedGlyph:
    """Measured: 15 spaces in Times-Roman deferred every maths span in one
    paper -- 0% projected, with nothing wrong but the gaps between the
    symbols."""

    def test_a_named_space_projects(self):
        from docmodel_six import glyph_latex
        gl = g("space", family="text", size=10.0, baseline=100.0, x=50.0,
               text=" ")
        assert glyph_latex(gl) == " "

    def test_a_space_character_projects(self):
        from docmodel_six import glyph_latex
        gl = g(None, family="math-italic", size=10.0, baseline=100.0,
               x=50.0, text=" ")
        assert glyph_latex(gl) == " "


class TestSpanGapsAreReported:
    """A LaTeX space emits no glyph, so a glyph reader reports nothing about
    it. The measurement is reported instead, and the reading is left to a
    consumer that knows more -- TeX's own atom spacing and an align
    environment produce the same widths as `\\:` and `\\quad`, so the
    command cannot be recovered from the width.
    """

    def _pair(self, gap_pt, size=10.0):
        a = g("alpha", family="math-italic", size=size, baseline=100.0,
              x=50.0)
        a.rect = (50.0, 100.0, 55.0, 100.0 + size)
        b = g("beta", family="math-italic", size=size, baseline=100.0,
              x=55.0 + gap_pt)
        b.rect = (55.0 + gap_pt, 100.0, 60.0 + gap_pt, 100.0 + size)
        import docmodel_six as D
        return D.Span(id="s", kind="math",
                      rect=(50.0, 100.0, 60.0 + gap_pt, 110.0),
                      glyphs=[a, b], rules=[], line_size=size)

    def test_a_negative_gap_is_reported(self):
        """`\\!` measures -0.167 em."""
        from docmodel_six import span_gaps
        got = span_gaps(self._pair(-1.67))
        assert len(got) == 1 and got[0]["kind"] == "negative"
        assert got[0]["em"] == -0.167

    def test_a_wide_gap_is_reported(self):
        """`\\quad` measures +1.0 em."""
        from docmodel_six import span_gaps
        got = span_gaps(self._pair(10.0))
        assert got and got[0]["kind"] == "wide" and got[0]["em"] == 1.0

    def test_tex_table_spacing_IS_reported(self):
        """A binary operator's own 4mu is not information the author added --
        it is information TEX added, which is better. The space is evidence
        for the pair of atom classes that produced it, so it is reported with
        its class rather than skipped.

        This test asserted the opposite until 705. That was the third test
        this session to encode a limitation as a requirement.
        """
        from docmodel_six import span_gaps
        got = span_gaps(self._pair(2.22))
        assert len(got) == 1 and got[0]["tex_class"] == 2

    def test_a_gap_off_the_table_is_still_skipped(self):
        """0.35em is neither 4mu nor 5mu nor wide enough to matter."""
        from docmodel_six import span_gaps
        assert span_gaps(self._pair(3.5)) == []

    def test_abutting_glyphs_are_not_reported(self):
        from docmodel_six import span_gaps
        assert span_gaps(self._pair(0.0)) == []

    def test_the_entry_names_both_sides(self):
        from docmodel_six import span_gaps
        got = span_gaps(self._pair(10.0))[0]
        assert set(got) == {"after", "em", "pt", "left", "right", "kind",
                            "tex_class"}


class TestUnderscoreIsContent:
    """An underscore is drawn as a RULE, not a glyph.

    `took_*` reaches the model as a 3.14pt zero-height rule at the baseline
    followed by an asterisk. An unmodelled rule makes the whole span defer,
    so a word with an underscore in it came out as a crop.

    It is told from a fraction bar by HEIGHT: a bar sits on the maths axis,
    about a quarter em above the baseline; an underscore sits on or just
    below the baseline.
    """

    def _rule(self, y, x0=72.0, x1=75.2):
        from docmodel_six import RuleNode
        return RuleNode(id="r", page=1, rect=(x0, y, x1, y))

    def _glyph(self, x=75.2, baseline=638.2, size=10.0):
        n = g("asteriskmath", family="math-symbol", size=size,
              baseline=baseline, x=x)
        n.rect = (x, baseline, x + 5.0, baseline + size)
        return n

    def test_a_baseline_rule_is_an_underscore(self):
        from docmodel_six import _rule_role
        assert _rule_role(self._rule(638.4), [self._glyph()], 10.0) \
            == "underscore"

    def test_a_bar_on_the_maths_axis_is_not(self):
        """A quarter em above the baseline is a fraction bar's height."""
        from docmodel_six import _rule_role
        assert _rule_role(self._rule(640.9), [self._glyph()], 10.0) \
            != "underscore"

    def test_a_wide_rule_is_not_an_underscore(self):
        from docmodel_six import _rule_role
        wide = self._rule(638.4, x0=50.0, x1=250.0)
        assert _rule_role(wide, [self._glyph()], 10.0) != "underscore"

    def test_it_reaches_the_latex(self):
        import structure
        from docmodel_six import RuleNode
        r = RuleNode(id="r", page=1, rect=(72.0, 638.4, 75.2, 638.4),
                     role="underscore")
        out = structure.to_tex([self._glyph()], [r])
        assert out == r"\_\ast", out


class TestAccentsRejoinTheirBase:
    """An accent is emitted BESIDE its base, not on its baseline.

    `\\widetilde{O}` reaches the page as the accent at stream 2635 and the
    `O` at 2636 -- adjacent in the stream, 2.5pt apart in baseline, which is
    past the row window. So the accent landed in a row of its own and the
    composition never happened: 703 `tildewide` and 130 `hatwide` on one
    paper, every one a crop.

    Widening the window cannot fix it: 2.5pt is also the distance to a
    script on the line above.
    """

    def _g(self, name, x0, x1, baseline, stream, size=9.96, kind="atom"):
        from texmap import TexToken
        n = g(name, family="math-extension" if kind == "accent"
              else "math-italic", size=size, baseline=baseline, x=x0)
        n.rect = (x0, baseline, x1, baseline + size)
        n.stream = stream
        n.tex = TexToken(r"\widetilde" if kind == "accent" else "O",
                         kind, None, "corpus")
        return n

    def test_an_accent_joins_its_stream_neighbour(self):
        from docmodel_six import _rejoin_accents
        acc = self._g("tildewide", 165.2, 170.7, 94.65, 2635, kind="accent")
        base = self._g("O", 163.2, 170.8, 92.13, 2636)
        rows = _rejoin_accents([[acc], [base]])
        assert len(rows) == 1 and len(rows[0]) == 2

    def test_it_must_overlap_the_base_in_x(self):
        """An accent sits OVER its base; a glyph elsewhere on the line is not
        its base however close in the stream."""
        from docmodel_six import _rejoin_accents
        acc = self._g("tildewide", 165.2, 170.7, 94.65, 2635, kind="accent")
        far = self._g("O", 300.0, 308.0, 92.13, 2636)
        rows = _rejoin_accents([[acc], [far]])
        assert len(rows) == 2

    def test_it_must_sit_above_the_base(self):
        from docmodel_six import _rejoin_accents
        acc = self._g("tildewide", 165.2, 170.7, 88.0, 2635, kind="accent")
        base = self._g("O", 163.2, 170.8, 92.13, 2636)
        assert len(_rejoin_accents([[acc], [base]])) == 2

    def test_an_ordinary_glyph_is_not_moved(self):
        from docmodel_six import _rejoin_accents
        a = self._g("x", 165.2, 170.7, 94.65, 2635)
        b = self._g("O", 163.2, 170.8, 92.13, 2636)
        assert len(_rejoin_accents([[a], [b]])) == 2

    def test_geometry_answers_when_the_stream_cannot(self):
        """A wide accent carries EMPTY TEXT, so the stream index -- keyed on
        position and text -- never matched it: 503 `tildewide` on one paper
        reached this branch. And a producer may emit the accent several
        positions from its base: `tildewide` at stream 2337 whose base `U`
        was neither 2336 nor 2338."""
        from docmodel_six import _rejoin_accents
        acc = self._g("tildewide", 165.2, 170.7, 94.65, -1, kind="accent")
        base = self._g("O", 163.2, 170.8, 92.13, -1)
        rows = _rejoin_accents([[acc], [base]])
        assert len(rows) == 1 and len(rows[0]) == 2

    def test_a_far_stream_neighbour_still_resolves(self):
        from docmodel_six import _rejoin_accents
        acc = self._g("tildewide", 221.3, 227.3, 138.94, 2337, kind="accent")
        base = self._g("U", 219.7, 227.2, 136.30, 2500)
        rows = _rejoin_accents([[acc], [base]])
        assert len(rows) == 1

    def test_a_base_too_far_below_is_not_its_base(self):
        """The accent sits just above its base, not a line away."""
        from docmodel_six import _rejoin_accents
        acc = self._g("tildewide", 165.2, 170.7, 130.0, -1, kind="accent")
        base = self._g("O", 163.2, 170.8, 92.13, -1)
        assert len(_rejoin_accents([[acc], [base]])) == 2


class TestDelimiterExtenders:
    """`vextendsingle` is U+23D0 VERTICAL LINE EXTENSION -- not a character.

    It is the middle section of a scalable bar, so `\\left| ... \\right|`
    reaches the page as a COLUMN of overlapping pieces at one x. Every piece
    was deferred on its own: 690 on a single paper, the largest class left
    in an 11,716-crop corpus list.

    Measured: three pieces at x=214.0, boxes 10pt tall stepping 6pt,
    together spanning y 290.1..312.1.
    """

    def _ext(self, x0, y0, name="vextendsingle", size=9.96):
        n = g(name, family="math-extension", size=size, baseline=y0, x=x0)
        n.rect = (x0, y0, x0 + 3.4, y0 + 10.0)
        return n

    def test_a_stack_becomes_one_delimiter(self):
        from docmodel_six import _merge_extenders
        stack = [self._ext(214.0, 302.1), self._ext(214.0, 296.1),
                 self._ext(214.0, 290.1)]
        out = _merge_extenders(stack)
        assert len(out) == 1

    def test_it_keeps_the_full_extent(self):
        """The extent is what tells a later pass what the delimiter spans."""
        from docmodel_six import _merge_extenders
        stack = [self._ext(214.0, 302.1), self._ext(214.0, 296.1),
                 self._ext(214.0, 290.1)]
        d = _merge_extenders(stack)[0]
        assert d.rect[1] == 290.1 and d.rect[3] == 312.1

    def test_it_projects_as_a_bar(self):
        from docmodel_six import _merge_extenders, glyph_latex
        d = _merge_extenders([self._ext(214.0, 302.1),
                              self._ext(214.0, 296.1)])[0]
        assert glyph_latex(d) == "|"

    def test_two_columns_are_two_delimiters(self):
        """A left and a right bar of the same construct."""
        from docmodel_six import _merge_extenders
        both = [self._ext(214.0, 296.1), self._ext(214.0, 290.1),
                self._ext(468.7, 296.1), self._ext(468.7, 290.1)]
        assert len(_merge_extenders(both)) == 2

    def test_a_gap_in_the_column_starts_a_new_delimiter(self):
        """Two separate bars in one column, not one tall one."""
        from docmodel_six import _merge_extenders
        apart = [self._ext(214.0, 400.0), self._ext(214.0, 300.0)]
        assert len(_merge_extenders(apart)) == 2

    def test_ordinary_glyphs_are_untouched(self):
        from docmodel_six import _merge_extenders
        a = g("alpha", family="math-italic", size=10.0, baseline=300.0,
              x=100.0)
        assert _merge_extenders([a]) == [a]

    def test_a_double_bar_extender(self):
        from docmodel_six import _merge_extenders, glyph_latex
        d = _merge_extenders([self._ext(214.0, 296.1, "vextenddouble"),
                              self._ext(214.0, 290.1, "vextenddouble")])[0]
        assert glyph_latex(d) == r"\|"


class TestEnclosureOverlays:
    """`\\copyright` in Computer Modern is TWO glyphs.

    A ring from the MATHS SYMBOL font with a `c` from the TEXT font inside
    it. Measured on a journal front page:

        circlecopyrt  CMSY7  x=[177.6, 185.6]
        c             CMR7   x=[179.8, 183.4]

    Two fonts, so the pair lands in two different SPANS -- one maths, one
    text -- and no pass working inside a span can ever see them together.
    Output before: `2025. (cid:2)c The Author(s)`.
    """

    def _g(self, name, text, x0, x1, family, baseline=664.4, size=6.97):
        n = g(name, family=family, size=size, baseline=baseline, x=x0,
              text=text)
        n.rect = (x0, baseline, x1, baseline + size)
        return n

    def _pair(self):
        ring = self._g("circlecopyrt", "(cid:2)", 177.6, 185.6,
                       "math-symbol")
        c = self._g(None, "c", 179.8, 183.4, "text", baseline=664.62)
        return [ring, c]

    def test_the_pair_composes(self):
        from docmodel_six import _merge_enclosures
        out = _merge_enclosures(self._pair())
        assert len(out) == 1 and out[0].tex.latex == "©"

    def test_the_result_is_text_not_maths(self):
        """Left in the maths family it came out as `$©$` in a copyright
        line."""
        from docmodel_six import _merge_enclosures
        assert _merge_enclosures(self._pair())[0].family == "text"

    def test_a_glyph_outside_the_ring_is_not_enclosed(self):
        from docmodel_six import _merge_enclosures
        ring = self._g("circlecopyrt", "(cid:2)", 177.6, 185.6,
                       "math-symbol")
        far = self._g(None, "c", 200.0, 204.0, "text")
        assert len(_merge_enclosures([ring, far])) == 2

    def test_a_different_letter_is_not_a_copyright(self):
        from docmodel_six import _merge_enclosures
        ring = self._g("circlecopyrt", "(cid:2)", 177.6, 185.6,
                       "math-symbol")
        z = self._g(None, "z", 179.8, 183.4, "text")
        assert len(_merge_enclosures([ring, z])) == 2

    def test_ordinary_glyphs_are_untouched(self):
        from docmodel_six import _merge_enclosures
        a = self._g(None, "a", 100.0, 105.0, "text")
        b = self._g(None, "b", 105.0, 110.0, "text")
        assert _merge_enclosures([a, b]) == [a, b]


class TestLogLikeOperatorNames:
    """TeX sets `\\sup`, `\\min`, `\\lim` in UPRIGHT ROMAN.

    They arrive as ordinary letters with nothing marking them as one token.
    Read letter by letter they became `\\mathrm{m}\\mathrm{in}`, and a
    neighbouring glyph then attached to one letter as a script:
    `\\sup` came out as `\\mathrm{s}_{<}\\mathrm{u}_{i}\\mathrm{p}_{-}`.

    This is a GROUPING failure, not a glyph-identity one -- the letters were
    read correctly every time.
    """

    def _run(self, text, size=10.0, baseline=700.0, x0=100.0, w=5.0):
        out = []
        x = x0
        for ch in text:
            n = g(None, family="text", size=size, baseline=baseline, x=x,
                  text=ch)
            n.rect = (x, baseline, x + w, baseline + size)
            out.append(n)
            x += w
        return out

    def test_a_run_spelling_min_becomes_one_token(self):
        from docmodel_six import _merge_operator_names
        out = _merge_operator_names(self._run("min"))
        assert len(out) == 1 and out[0].tex.latex == r"\min"

    def test_the_longest_name_wins(self):
        """`limsup` is not `lim` followed by `sup`."""
        from docmodel_six import _merge_operator_names
        out = _merge_operator_names(self._run("limsup"))
        assert len(out) == 1 and out[0].tex.latex == r"\limsup"

    def test_a_near_miss_is_left_alone(self):
        """`supp` is a variable name. Turning it into an operator would be
        the confident wrong answer this project refuses."""
        from docmodel_six import _merge_operator_names
        assert len(_merge_operator_names(self._run("supp"))) == 4

    def test_a_gap_breaks_the_run(self):
        from docmodel_six import _merge_operator_names
        gl = self._run("min")
        gl[2].rect = (gl[2].rect[0] + 6.0, gl[2].rect[1],
                      gl[2].rect[2] + 6.0, gl[2].rect[3])
        assert len(_merge_operator_names(gl)) == 3

    def test_a_size_change_breaks_the_run(self):
        from docmodel_six import _merge_operator_names
        gl = self._run("min")
        gl[2].size = 7.0
        assert len(_merge_operator_names(gl)) == 3

    def test_italic_letters_are_not_an_operator(self):
        """`min` in maths italic is three variables m, i, n."""
        from docmodel_six import _merge_operator_names
        gl = self._run("min")
        for x in gl:
            x.family = "math-italic"
        assert len(_merge_operator_names(gl)) == 3

    def test_the_merged_token_keeps_the_full_extent(self):
        from docmodel_six import _merge_operator_names
        out = _merge_operator_names(self._run("sup"))[0]
        assert out.rect[0] == 100.0 and out.rect[2] == 115.0


class TestOperatorRunsAreGroupedByLine:
    """The pass walks a SEQUENCE; it is handed a whole PAGE.

    Sorting a page's upright glyphs by x alone interleaves lines. Measured on
    72.pdf, the `s`,`u`,`p` of a `\\sup` are adjacent within their line --
    baselines all 427.74, sizes all 10.91, gaps 0.00 -- and NOT adjacent in
    the page-wide x-order. Every precondition the pass tests was satisfied;
    the ordering never presented the run, which is why it fired zero times
    corpus-wide while the table itself was correct.
    """

    def _run(self, text, baseline, x0, size=10.0, w=5.0):
        out = []
        x = x0
        for ch in text:
            n = g(None, family="text", size=size, baseline=baseline, x=x,
                  text=ch)
            n.rect = (x, baseline, x + w, baseline + size)
            out.append(n)
            x += w
        return out

    def test_a_run_interleaved_by_another_line_still_merges(self):
        """The other line's glyphs fall between the letters in x-order."""
        from docmodel_six import _merge_operator_names
        line_a = self._run("sup", baseline=427.7, x0=100.0)
        line_b = self._run("xyz", baseline=400.0, x0=102.0)
        out = _merge_operator_names(line_a + line_b)
        merged = [x for x in out if x.tex.latex == r"\sup"]
        assert len(merged) == 1

    def test_letters_on_different_lines_do_not_form_a_run(self):
        """`s` on one line and `up` on the next is not `\\sup`."""
        from docmodel_six import _merge_operator_names
        gl = self._run("s", baseline=427.7, x0=100.0) \
            + self._run("up", baseline=400.0, x0=105.0)
        assert all(x.tex.latex != r"\sup" for x in _merge_operator_names(gl))

    def test_the_merged_token_is_maths_not_text(self):
        """Left in the text family it came out as `\\text{\\max}`, which
        renders the command literally."""
        from docmodel_six import _merge_operator_names
        out = _merge_operator_names(self._run("max", baseline=400.0,
                                              x0=100.0))
        assert out[0].family == "math-symbol"


class TestStreamLineMerge:
    """The producer's own line structure, merged into the rows.

    `_line_bands` reads the y boundaries between the producer's lines from
    the content stream; `_merge_stream_lines` joins rows that fall between
    the same pair. A fraction's numerator, rule and denominator are three y
    values and ONE line, which baseline clustering cannot recover.

    The pass is correct and is NOT CALLED. Enabling it took 91.pdf from 72
    rows to 21 against 22 line returns -- and took display blocks from 817
    to 98, crops from 548 to 1303, and projection from ~88% to 62.4%,
    because `_attach_scripts` cannot consume a whole display line at once.
    Attachment has to be fixed first.
    """

    def _row(self, baseline, x0=100.0, n=2, size=10.0):
        out = []
        for i in range(n):
            g_ = g("alpha", family="math-italic", size=size,
                   baseline=baseline, x=x0 + i * 5.0)
            g_.rect = (x0 + i * 5.0, baseline, x0 + i * 5.0 + 5.0,
                       baseline + size)
            out.append(g_)
        return out

    def test_rows_inside_one_band_merge(self):
        """A numerator, a baseline and a denominator are ONE line."""
        from docmodel_six import _merge_stream_lines
        rows = [self._row(706.0), self._row(700.0), self._row(694.0)]
        out = _merge_stream_lines(rows, [690.0])
        assert len(out) == 1 and len(out[0]) == 6

    def test_rows_across_a_boundary_stay_apart(self):
        from docmodel_six import _merge_stream_lines
        rows = [self._row(706.0), self._row(680.0)]
        assert len(_merge_stream_lines(rows, [690.0])) == 2

    def test_no_bands_changes_nothing(self):
        """dvips places absolutely (703), so its stream yields no bands and
        the geometric clustering must survive untouched."""
        from docmodel_six import _merge_stream_lines
        rows = [self._row(706.0), self._row(700.0)]
        assert _merge_stream_lines(rows, []) == rows

    def test_it_only_ever_joins(self):
        """It must never split a row that clustering produced."""
        from docmodel_six import _merge_stream_lines
        rows = [self._row(706.0, n=3), self._row(700.0, n=3)]
        out = _merge_stream_lines(rows, [690.0])
        assert sum(len(r) for r in out) == 6 and len(out) <= len(rows)

    def test_the_merged_row_is_in_x_order(self):
        from docmodel_six import _merge_stream_lines
        rows = [self._row(700.0, x0=200.0), self._row(706.0, x0=100.0)]
        out = _merge_stream_lines(rows, [690.0])[0]
        assert [gg.rect[0] for gg in out] == sorted(gg.rect[0] for gg in out)


class TestAWideFractionBar:
    r"""735 -- TeX sets the fraction rule as wide as the WIDER of numerator
    and denominator, so a long denominator makes a long bar. The guard that
    stops a code listing's border being read as a fraction was an em count,
    `> 12 em`, and wzlxjtu-045's

        \frac{1}{\sum_{i=1}^{n} I\{D_i=1, M_i=0, T_i=1\}}

    sets a 160.2pt bar in 12pt type -- 13.35 em. It failed by 16pt, was
    called a separator, and with no bar there is no fraction: the numerator,
    the denominator and the head of the equation stayed three separate bands
    and one two-row display came apart into nine pieces.

    A listing border is told from a fraction bar by the same rule TeX drew it
    with: one of the two groups REACHES BOTH ENDS of the bar. Code inside a
    frame is inset from both margins and reaches neither.
    """

    def _rule(self, x0, x1, y):
        from docmodel_six import RuleNode
        return RuleNode(id="r", page=1, rect=(x0, y, x1, y))

    def _row(self, baseline, x0, x1, size=12.0, n=20):
        step = (x1 - x0) / max(n - 1, 1)
        return [g(None, family="math-italic", size=size, baseline=baseline,
                  x=x0 + i * step, text="o") for i in range(n)]

    def test_a_long_denominator_still_makes_a_fraction(self):
        from docmodel_six import _rule_role
        bar = self._rule(188.4, 348.7, 672.6)        # 160.2pt, 13.35 em
        num = self._row(677.2, 265.0, 272.0, n=1)    # a lone `1`, centred
        den = self._row(663.0, 188.4, 348.7)         # reaches both ends
        assert _rule_role(bar, num + den, 12.0) == "fraction"

    def test_a_listing_border_is_still_a_separator(self):
        from docmodel_six import _rule_role
        # the frame runs the block; the code inside is inset from both margins
        bar = self._rule(85.0, 510.0, 672.6)
        above = self._row(677.2, 110.0, 300.0)
        below = self._row(663.0, 110.0, 280.0)
        assert _rule_role(bar, above + below, 12.0) == "separator"


class TestABandIsOffRowMaterialNotJustSmallType:
    r"""767 -- a display-style fraction sets its parts at TEXT size.

    733 places a band of scripts on the row holding their bases, by stream,
    and asks "is this a band?" with `max(size) < 0.95 * span_pt`.
    `\frac{1}{2}` beside a 9.96pt row draws its `1` and `2` at 9.96pt, so a
    band carrying a fraction fails that test and 733 never looks at it.

    wzlxjtu-031's eighth display arrived as

        band   s m | s-1 m+1 | 1 2 | 2s 2 | s m+1
        row    \partial C - e^{\rho}(C - g (-1, m+1)C

    -- every script of the equation on a line of its own, the row emitted
    without them, and the band as a second block. The fraction RULE is what
    says a full-size glyph is a numerator and not a term of the row.
    """

    SPAN = 9.9626

    def _g(self, x, baseline, size):
        return g("x", size=size, baseline=baseline, x=x)

    def _bar(self, x0, x1, y, role="fraction"):
        from docmodel_six import RuleNode
        return RuleNode(id="r", page=1, rect=(x0, y, x1, y), role=role)

    def _off(self, grp, rules):
        from docmodel_six import _off_row_band
        return _off_row_band(grp, rules, self.SPAN)

    def test_a_band_of_scripts_is_one(self):
        assert self._off([self._g(100.0, 230.0, 6.97),
                          self._g(110.0, 216.0, 6.97)], []) is True

    def test_a_fraction_part_at_text_size_does_not_disqualify_it(self):
        """031's band: fifteen 6.97pt scripts and the `1` and `2` of a half,
        both at 9.96pt, one above the bar's axis and one below."""
        bar = self._bar(118.0, 124.0, 223.0)
        grp = [self._g(100.0, 230.0, 6.97),
               self._g(119.0, 230.0, self.SPAN),      # the 1, above the axis
               self._g(119.0, 216.5, self.SPAN)]      # the 2, below it
        assert self._off(grp, [bar]) is True

    def test_a_full_size_glyph_with_no_bar_over_it_is_a_row(self):
        """Without a rule saying otherwise, a full-size glyph is a term of
        the row and this band is a row. That is the guard 733 had."""
        assert self._off([self._g(100.0, 230.0, 6.97),
                          self._g(119.0, 230.0, self.SPAN)], []) is False

    def test_a_glyph_on_the_bar_s_own_axis_is_not_a_fraction_part(self):
        """A term standing BESIDE the fraction shares the row's baseline,
        which is the bar's axis. Only what is displaced is a part of it."""
        bar = self._bar(118.0, 124.0, 223.0)
        beside = self._g(119.0, 223.0, self.SPAN)
        assert self._off([beside], [bar]) is False

    def test_a_glyph_outside_the_bar_s_x_range_is_not_its_part(self):
        bar = self._bar(118.0, 124.0, 223.0)
        assert self._off([self._g(200.0, 230.0, self.SPAN)], [bar]) is False

    def test_an_overline_is_not_a_fraction_bar(self):
        """Only a rule `_rule_role` called a fraction licenses a part."""
        bar = self._bar(118.0, 124.0, 223.0, "overline")
        assert self._off([self._g(119.0, 230.0, self.SPAN)], [bar]) is False


class TestAScriptIsNotATextLineRunningAcrossTheBar:
    r"""768 -- a display's superscripts share the numerator's baseline.

    `_is_own_row` tells a numerator from a line of text passing over the bar
    by counting what else sits on the numerator's baseline outside the bar.
    wzlxjtu-015 sets

        S^{(W)}_{ct}=4\int d^5x\sqrt{\gamma}
            [\tfrac12\sigma^2+\tfrac34(\phi^0)^2-\tfrac{1}{16}(\phi^3)^2 ...]

    whose numerators `1` and `3` sit at baseline 190.38 -- and so do the
    exponents of `\sigma^2` and `(\phi^0)^2`. Those exponents are outside the
    bars and have no bar of their own, so the count was never zero: two
    fraction bars were classified `overline`, the span then carried an
    unaccounted rule, and the whole display refused.

    An overline's base is part of a RUNNING TEXT LINE, and a running text
    line is not set in script type.
    """

    SIZE = 12.0
    BAR = (210.10, 215.95)
    AXIS = 185.30

    def _rule(self, x0=None, x1=None):
        from docmodel_six import RuleNode
        x0 = self.BAR[0] if x0 is None else x0
        x1 = self.BAR[1] if x1 is None else x1
        return RuleNode(id="r", page=1, rect=(x0, self.AXIS, x1, self.AXIS))

    def _g(self, x, baseline, size=None):
        return g("one", size=size or self.SIZE, baseline=baseline, x=x)

    def _parts(self):
        """The `1` over the `2`, both inside the bar."""
        return [self._g(210.10, 190.38), self._g(210.10, 174.09)]

    def _role(self, extra):
        from docmodel_six import _rule_role
        r = self._rule()
        return _rule_role(r, self._parts() + extra, self.SIZE, [r])

    def test_a_superscript_on_that_baseline_does_not_demote_the_bar(self):
        """8.4pt at 12pt type: an exponent, 40pt to the right of the bar."""
        assert self._role([self._g(250.0, 190.38, 8.4)]) == "fraction"

    def test_a_full_size_glyph_on_that_baseline_still_does(self):
        """The guard this test protects: a line of text running across the
        bar is set in the surrounding type, and then the bar is an accent."""
        assert self._role([self._g(250.0, 190.38)]) != "fraction"

    def test_with_nothing_beside_it_the_bar_is_a_fraction(self):
        assert self._role([]) == "fraction"


class TestASingleItalicLetterOnADisplayLineIsAVariable:
    r"""775 — `_tight` is calibrated against a word space, and a display line
    has no words to measure one from.

    Obertelli & Sagawa page 673 sets `n + e^+ ⇌ p + \bar{\nu}_e`. `_word_gap`
    on that line measures 1.42pt — the kerning between letters — so `_tight`'s
    threshold comes out at 0.50pt, while TeX's space around a binary operator
    is 2.5–4.1pt. Every variable on the line failed it.

    The `e` was rescued anyway (its `^+` proves its base is maths); `n` and
    `p` carry no script, so they stayed prose and were emitted `\text{n}`,
    `\text{p}` — upright, where the page sets them italic, in a book whose
    maths Latin letters ARE Times-Italic. One display, two spellings.
    """

    SP = 2.8          # TeX's space around a binary operator, at 10pt

    #: the glyph NAME matters: `_solid` refuses to absorb a run into a maths
    #: run that cannot project, so the operator needs a name it can be read by.
    NAMES = {"+": "plus", "=": "equal"}

    def _g(self, text, x, *, fam, size=10.0, font="QTJSUC+Times-Italic10"):
        n = g(self.NAMES.get(text, text), family=fam, size=size,
              baseline=100.0, x=x, text=text)
        n.fontname = font
        n.rect = (x, 100.0, x + 5.0, 110.0)
        return n

    def _line(self, glyphs, type_="formula"):
        from docmodel_six import LineNode
        return LineNode(id="l", page=1, type=type_, glyphs=glyphs,
                        rect=(0, 95, 400, 115))

    def _reaction(self):
        """`n + p` — an italic letter, an operator, an italic letter."""
        x = 0.0
        out = []
        for text, fam in (("n", "text"), ("+", "math-symbol"), ("p", "text")):
            font = ("JAAHIM+MTSYN10" if fam != "text"
                    else "QTJSUC+Times-Italic10")
            out.append(self._g(text, x, fam=fam, font=font))
            x += 5.0 + self.SP
        return out

    def test_the_variables_join_the_mathematics(self):
        spans = self._line(self._reaction()).spans
        assert [s.kind for s in spans] == ["math"], \
            [(s.kind, "".join(g.text for g in s.glyphs)) for s in spans]

    def test_a_word_beside_the_mathematics_is_still_prose(self):
        r"""One letter, not a run: `and` is three and no relaxation here can
        reach it."""
        gl = self._reaction()
        x = 40.0
        for c in "and":
            gl.append(self._g(c, x, fam="text"))
            x += 5.0
        kinds = [s.kind for s in self._line(gl).spans]
        assert "text" in kinds, kinds

    def test_a_prose_line_is_not_a_display(self):
        r"""The relaxation applies only where there are no WORDS. A sentence
        with an italic letter in it keeps that letter as prose."""
        gl = []
        x = 0.0
        for c in "for":
            gl.append(self._g(c, x, fam="text")); x += 5.0
        x += 8.0
        gl.append(self._g("x", x, fam="text")); x += 5.0 + self.SP
        gl.append(self._g("=", x, fam="math-symbol", font="JAAHIM+MTSYN10"))
        x += 5.0 + self.SP
        for c in "and":
            gl.append(self._g(c, x, fam="text")); x += 5.0
        kinds = [s.kind for s in self._line(gl).spans]
        assert kinds.count("text") >= 2, kinds

    def test_an_upright_letter_is_not_swept_in_by_this_rule(self):
        r"""The rule is about ITALIC letters — that is what italic MEANS in
        mathematics. An upright one is an operator name or prose, and the
        existing `_tight` test still governs it."""
        gl = self._reaction()
        gl[0] = self._g("n", 0.0, fam="text", font="QGCLFC+Times-Roman10")
        kinds = [s.kind for s in self._line(gl).spans]
        assert "text" in kinds, kinds


class TestAFlippedMatrixIsNotARotation:
    r"""778 — 2002.06055 draws its blackboard letters from a font pdfminer
    cannot resolve (`fontname` is the literal "unknown") with a FLIPPED text
    matrix, (1, 0, 0, -1, x, y).

    Two things follow from that matrix and both were wrong. pdfminer computes
    `size` 0.120 and a box 0.16pt tall while the advance is 8.160; and it
    reports `upright` False, which sent the glyph to the ROTATED pipeline —
    where a stamp or a margin note belongs, not a symbol in a formula.

    The author wrote `(\Hilb, \cotimes, \fieldc)`. It came out
    `(\mathrm{Hilb}, \hat{\otimes}, )`: a symbol dropped between a comma and
    a bracket, with nothing to show it had gone.
    """

    def _char(self, matrix, size=0.12, adv=8.16, x=202.44, base=618.12):
        from pdfminer.layout import LTChar
        return {"matrix": matrix, "size": size, "adv": adv,
                "rect": (x, base, x + adv, base + 0.16)}

    def test_rotation_lives_in_b_and_c(self):
        """A 90-degree stamp has them NON-zero, and must stay refused — that
        is what keeps `arXiv:0805.0311v3` out of the prose."""
        stamp = (0.0, 1.0, -1.0, 0.0, 30.0, 700.0)
        assert not (abs(stamp[1]) < 1e-6 and abs(stamp[2]) < 1e-6)

    def test_a_vertical_flip_has_neither(self):
        """(1, 0, 0, -1) reflects the glyph's own y axis: the text still
        reads left to right."""
        flip = (1.0, 0.0, 0.0, -1.0, 202.44, 618.12)
        assert abs(flip[1]) < 1e-6 and abs(flip[2]) < 1e-6

    def test_the_flipped_glyph_reaches_the_reading(self):
        """End to end on the page it was found on."""
        import docmodel_six as D
        pdf = "/home/wkolbe/pdfdrill-library/2002.06055/2002.06055.pdf"
        if not os.path.exists(pdf):
            pytest.skip("library PDF not present")
        doc = D.build(pdf, range(30, 31))
        line = next(ln for pg in doc for ln in pg.lines
                    if "Hilb" in D._run_text(ln.glyphs))
        assert not line.rotated
        assert any(g.fontname == "unknown" for g in line.glyphs), \
            D._run_text(line.glyphs)[:60]

    def test_its_size_is_repaired_from_the_page(self):
        r"""Nothing advances sixty-eight times its own height. The
        contradiction is inside the glyph; the page supplies the replacement
        and the matrix supplies the baseline."""
        import docmodel_six as D
        pdf = "/home/wkolbe/pdfdrill-library/2002.06055/2002.06055.pdf"
        if not os.path.exists(pdf):
            pytest.skip("library PDF not present")
        doc = D.build(pdf, range(30, 31))
        odd = [g for pg in doc for ln in pg.lines for g in ln.glyphs
               if g.fontname == "unknown"]
        assert odd, "the flipped glyphs are not in any line"
        for g in odd:
            assert g.size > 1.0, (g.text, g.size)
            assert g.rect[3] - g.rect[1] > 1.0, (g.text, g.rect)


class TestACodeListingIsNotABandOfScripts:
    r"""780 — 733 places a band of scripts onto the row holding their bases,
    and asks whether a row IS such a band by size alone: anything under
    0.95 of the page's dominant size qualifies.

    A listing is set smaller than the body — `\ttfamily\tiny` is the ordinary
    choice — so on a 10pt page every 6pt line of code qualified, and 733
    dissolved it, placing its glyphs per-glyph onto whatever rows the stream
    pointed at. 2604.22294 sets 25 `lstlisting` blocks that way; page 19 came
    out as 14 lines where the page has 28, every other line break gone and
    the spaces with it:

        ## Ordering and Retrieval Questions- The schema should not contain…

    In a listing a line break is CONTENT.
    """

    SPAN = 10.0

    def _g(self, text, x, size, font):
        n = g(None, family="text", size=size, baseline=300.0, x=x, text=text)
        n.fontname = font
        n.rect = (x, 300.0, x + 0.5 * size, 300.0 + size)
        return n

    def _row(self, font, size=6.0):
        return [self._g(c, 100.0 + 3.0 * i, size, font)
                for i, c in enumerate("def f(x):")]

    def _is_band(self, row):
        from docmodel_six import _off_row_band
        return _off_row_band(row, [], self.SPAN)

    def test_a_typewriter_row_is_never_a_band(self):
        assert self._is_band(self._row("AAAAAA+CMTT10")) is False

    def test_however_small_it_is(self):
        """`\tiny` inside a 10pt page is the ordinary case, not an oddity."""
        assert self._is_band(self._row("AAAAAA+CMTT10", size=4.0)) is False

    def test_a_proportional_row_of_that_size_is_still_a_band(self):
        """The guard is the FACE, not the size — 733 keeps working for the
        script bands it was written for."""
        assert self._is_band(self._row("AAAAAA+CMR10")) is True

    def test_one_monospace_glyph_is_enough_to_refuse_the_row(self):
        r"""A script inside code is still code."""
        row = self._row("AAAAAA+CMR10")
        row[3] = self._g("x", 109.0, 6.0, "AAAAAA+CMTT10")
        assert self._is_band(row) is False

    def test_the_listing_survives_end_to_end(self):
        import docmodel_six as D
        pdf = "/home/wkolbe/pdfdrill-library/2604.22294/2604.22294.pdf"
        if not os.path.exists(pdf):
            pytest.skip("library PDF not present")
        doc = D.build(pdf, range(18, 19))
        verbatim = [ln for pg in doc for ln in pg.lines if ln.verbatim]
        assert len(verbatim) >= 25, len(verbatim)
        joined = [ln for ln in verbatim
                  if len({round(x.baseline, 2) for x in ln.glyphs}) > 1]
        assert not joined, "two rows of the listing merged into one line"
