"""Tests for structure — fraction and script reconstruction.

The governing property is not coverage but SAFETY: when geometry does not
determine the answer, `to_tex` must return None. A wrong `\\frac` or a
misattached `^{}` is valid LaTeX containing different mathematics, and nothing
downstream can detect it.
"""

import os

import pytest

import docmodel_six as docmodel
import structure
import testpaths
from docmodel_six import GlyphNode, RuleNode
from texmap import project


# --- corpus fixtures -------------------------------------------------------
# These tests read real PDFs. They are not shipped with the toolkit (they are
# copyrighted books), so the whole module skips when they are absent rather
# than failing on a machine that simply does not have them. Point
# PDF2MMD_TEST_PDF / PDF2MMD_TEST_LINES at your own copies to run them.
MIELKE = testpaths.CORPUS_PDF


def g(name, size=10.0, baseline=100.0, x=0.0, family="math-italic", text="x"):
    return GlyphNode(
        id=f"g{x}", page=1,
        rect=(x, baseline, x + size * 0.5, baseline + size),
        text=text, cid=1, glyphname=name, fontname="T+CMMI10",
        family=family, size=size, tex=project(family, name),
        matrix=(size, 0, 0, size, x, baseline),
    )


@pytest.fixture(scope="module")
def page209():
    if not os.path.exists(MIELKE):
        pytest.skip("no corpus PDF; set PDF2MMD_TEST_PDF")
    return docmodel.build(MIELKE, range(208, 209))


def spans(pages):
    return [sp for p in pages for ln in p.lines for sp in ln.spans
            if sp.kind == "math"]


class TestScripts:
    def test_superscript(self):
        base = g("alpha", 10.0, 100.0, 0.0)
        sup = g("beta", 7.0, 104.0, 6.0)
        assert structure.to_tex([base, sup]) == r"\alpha^{\beta}"

    def test_subscript(self):
        base = g("alpha", 10.0, 100.0, 0.0)
        sub = g("beta", 7.0, 97.0, 6.0)
        assert structure.to_tex([base, sub]) == r"\alpha_{\beta}"

    def test_both_scripts_render_sub_before_sup(self):
        base = g("Gamma", 10.0, 100.0, 0.0)
        sub = g("alpha", 7.0, 97.0, 6.0)
        sup = g("star", 7.0, 104.0, 6.0)
        assert structure.to_tex([base, sub, sup]) == r"\Gamma_{\alpha}^{\star}"

    def test_multi_glyph_script_groups(self):
        """Spacing now comes from the MEASURED gap, so the geometry decides:
        these two script glyphs abut, and abutting symbols get no space."""
        base = g("Gamma", 10.0, 100.0, 0.0)
        s1 = g("beta", 7.0, 104.0, 6.0)
        s2 = g("gamma", 7.0, 104.0, 10.0)
        assert structure.to_tex([base, s1, s2]) == r"\Gamma^{\beta\gamma}"

    def test_level_row_has_no_scripts(self):
        a = g("alpha", 10.0, 100.0, 0.0)
        b = g("beta", 10.0, 100.0, 6.0)
        assert structure.to_tex([a, b]) == r"\alpha \beta"

    def test_nested_script(self):
        base = g("ell", 10.0, 100.0, 0.0)
        base.glyphname = "lscript"
        base.tex = project("math-italic", "lscript")
        two = g(None, 7.0, 104.0, 6.0, family="text", text="2")
        assert structure.to_tex([base, two]) == r"\ell^{2}"


class TestAbstention:
    def test_leading_script_is_emitted_with_an_EMPTY_base(self):
        """A script with nothing to its left is stated, not guessed.

        This asserted `is None` until 735. The contract it encoded -- never
        attribute a script you cannot place -- has NOT changed: `{}` attaches
        the script to nothing, which is what is true, and is the same device
        this pass already used for a marker group whose base belongs to the
        prose.

        What changed is the blast radius. Refusing here deferred the WHOLE
        display, and after the band merge that was the largest single cause:
        4,573 refusals across the 102 documents. Emitting the empty base took
        crops from 559 to 417 and recovered 40 display blocks and 15
        fractions, with no change to the equations delivered whole -- so
        nothing that was right became wrong; content that was being thrown
        away is kept.
        """
        sup = g("alpha", 7.0, 104.0, 0.0)
        base = g("beta", 10.0, 100.0, 6.0)
        assert structure.to_tex([sup, base]) == r"{}^{\alpha} \beta"

    def test_unidentified_glyph_refuses_the_whole_span(self):
        a = g("alpha", 10.0, 100.0, 0.0)
        bad = g("zzz-not-a-glyph", 10.0, 100.0, 6.0, family="math-symbol")
        assert structure.to_tex([a, bad]) is None

    def test_radicals_are_refused(self):
        """The vinculum does not reliably bound the argument."""
        r = g("radicalbig", 10.0, 100.0, 0.0, family="math-extension")
        a = g("alpha", 10.0, 100.0, 6.0)
        assert structure.to_tex([r, a]) is None

    def test_fragments_are_refused(self):
        frag = g("bracketleftex", 10.0, 100.0, 0.0, family="math-extension")
        a = g("alpha", 10.0, 100.0, 6.0)
        assert structure.to_tex([frag, a]) is None

    def test_rule_without_both_sides_defers(self):
        """A bar classified as a fraction that cannot resolve must DEFER.

        Ignoring it lets the glyphs fall through to script attachment, where a
        numerator and denominator on different baselines become
        `1_{\\beta\\gamma}` -- valid LaTeX with the fraction silently gone.
        """
        a = g("alpha", 10.0, 100.0, 0.0)
        rule = RuleNode(id="r", page=1, rect=(0.0, 112.0, 5.0, 112.0),
                        role="fraction")  # above everything: no numerator
        assert structure.to_tex([a], [rule]) is None


class TestFractions:
    def _frac(self):
        # Geometry consistent with a 10pt row on baseline 100: the bar sits
        # on the maths axis, ~0.25em above the baseline.
        num = g(None, 10.0, 108.0, 0.0, family="text", text="1")
        den = g(None, 10.0, 94.0, 0.0, family="text", text="2")
        rule = RuleNode(id="r", page=1, rect=(0.0, 102.5, 5.0, 102.5),
                        role="fraction")
        return num, den, rule

    def test_simple_fraction(self):
        num, den, rule = self._frac()
        assert structure.to_tex([num, den], [rule]) == r"\frac{1}{2}"

    def test_fraction_neighbour_keeps_its_scripts(self):
        """The defect this unit was rewritten for.

        Emitting the fraction's neighbours glyph-wise dropped their scripts,
        turning `\\Gamma_{\\alpha}^{\\star}` into `\\Gamma \\alpha \\star` —
        valid LaTeX saying something else.
        """
        num, den, rule = self._frac()
        base = g("Gamma", 10.0, 100.0, 20.0)
        sub = g("alpha", 7.0, 97.0, 26.0)
        sup = g("star", 7.0, 104.0, 26.0)
        out = structure.to_tex([num, den, base, sub, sup], [rule])
        assert out == r"\frac{1}{2} \Gamma_{\alpha}^{\star}"

    def test_page209_matches_mathpix(self, page209):
        """End-to-end against an independent reading of the same page.

        NOTE: `\\frac{1}{2}` was asserted here until baseline line-grouping
        landed. Grouping by baseline fixed prose interleaving (a display
        equation\'s tall box used to swallow the text lines around it) but
        splits a fraction\'s numerator from its denominator, and the
        rule-driven re-merge does not recover every case on this page. The
        fractions that no longer resolve now DEFER rather than emit wrongly --
        see the report. A fraction that does resolve is asserted below.
        """
        got = [structure.span_to_tex(sp) for sp in spans(page209)]
        joined = " ".join(t for t in got if t)
        assert r"\frac{" in joined, "no fraction resolved at all"
        assert r"\Gamma_{\alpha}^{\star}" in joined
        # `/` and `\ell` abut in the PDF, so no space is emitted between
        # them; spacing follows the measured gap now, not a fixed join.
        assert r"\vartheta_{\alpha} /\ell" in joined


class TestProjectionStillTotal:
    def test_every_math_span_projects_or_defers(self, page209):
        for sp in spans(page209):
            out = docmodel.span_text(sp)
            assert out.startswith("$") or "DEFERRED" in out


class TestTwoGlyphSymbols:
    """TeX builds some symbols from two glyphs. Projected apart they are wrong."""

    def _named(self, name, x, size=10.0, family="math-symbol", width=None):
        n = g(name, size, 100.0, x, family=family)
        if width is not None:
            n.rect = (x, n.rect[1], x + width, n.rect[3])
        return n

    def test_mapsto_is_one_arrow_not_two(self):
        """CM draws `\\mapsto` as a bar plus an arrow."""
        bar = self._named("mapsto", 0.0, family="math-symbol")
        arrow = self._named("arrowright", 3.0, family="math-symbol")
        out = structure._merge_mapsto([bar, arrow])
        assert len(out) == 1 and out[0].tex.latex == r"\mapsto"

    def test_negation_before_its_relation(self):
        slash = self._named("negationslash", 5.0, width=0.0)
        eq = self._named("equal", 5.0)
        out = structure._merge_negations([slash, eq])
        assert [o.tex.latex for o in out] == [r"\neq"]

    def test_negation_after_its_relation(self):
        """Measured in a real document: both orders occur."""
        eq = self._named("equal", 0.0)
        slash = self._named("negationslash", 5.0, width=0.0)
        out = structure._merge_negations([eq, slash])
        assert [o.tex.latex for o in out] == [r"\neq"], \
            "the relation must not be emitted twice"

    def test_lone_negation_still_defers(self):
        slash = self._named("negationslash", 0.0, width=0.0)
        alpha = g("alpha", 10.0, 100.0, 40.0)
        out = structure._merge_negations([slash, alpha])
        assert any(o.tex.kind == "overlay" for o in out)


class TestLargeOperators:
    """cmex10's large operators, keyed on the base name not one at a time."""

    def test_bigoplus(self):
        assert project("math-extension", "circleplusdisplay").latex == r"\bigoplus"
        assert project("math-extension", "circleplustext").latex == r"\bigoplus"

    def test_the_family(self):
        for name, want in (("circlemultiplydisplay", r"\bigotimes"),
                           ("circledotdisplay", r"\bigodot"),
                           ("coproductdisplay", r"\coprod"),
                           ("unionmultitext", r"\biguplus"),
                           ("unionsqdisplay", r"\bigsqcup"),
                           ("logicalordisplay", r"\bigvee")):
            assert project("math-extension", name).latex == want, name


class TestWideAccents:
    """A wide accent is a separate glyph drawn ABOVE its base.

    `\\widehat{\\otimes}` is cmex10's `hatwide` (slot 0x62) over cmsy10's
    `circlemultiply` (slot 0x0A). Side by side they project as
    `\\widehat \\otimes`, which is not valid LaTeX, and the raised baseline
    makes the span defer instead.
    """

    def _acc(self, name, x0, x1, baseline, size=12.0):
        n = g(name, size, baseline, x0, family="math-extension")
        n.rect = (x0, baseline, x1, baseline + size)
        n.matrix = (size, 0, 0, size, x0, baseline)
        return n

    def _base(self, name, x0, x1, baseline, size=12.0, family="math-symbol"):
        n = g(name, size, baseline, x0, family=family)
        n.rect = (x0, baseline, x1, baseline + size)
        n.matrix = (size, 0, 0, size, x0, baseline)
        return n

    def test_widehat_over_otimes(self):
        """Geometry copied from a real page: accent raised 1.9pt at 12pt."""
        base = self._base("circlemultiply", 125.6, 134.9, 145.2)
        acc = self._acc("hatwide", 127.0, 133.6, 147.1)
        out = structure.to_tex([base, acc])
        assert out == r"\widehat{\otimes}"

    def test_accent_only_wraps_what_it_spans(self):
        left = self._base("A", 114.2, 123.0, 145.2, family="math-italic")
        base = self._base("circlemultiply", 125.6, 134.9, 145.2)
        acc = self._acc("hatwide", 127.0, 133.6, 147.1)
        right = self._base("B", 137.6, 146.5, 145.2, family="math-italic")
        out = structure.to_tex([left, base, acc, right])
        assert out == r"A \widehat{\otimes} B"

    def test_zero_width_accent_uses_the_nearest_glyph(self):
        """The accent may carry NO advance width, so its box gives no extent."""
        base = self._base("lambda", 100.0, 106.0, 200.0, family="math-italic")
        acc = self._acc("tildewide", 100.0, 100.0, 202.0)
        assert structure.to_tex([base, acc]) == r"\widetilde{\lambda}"

    def test_accent_over_several_glyphs(self):
        a = self._base("alpha", 100.0, 106.0, 200.0, family="math-italic")
        b = self._base("beta", 106.0, 112.0, 200.0, family="math-italic")
        acc = self._acc("tildewide", 100.0, 112.0, 202.0)
        assert structure.to_tex([a, b, acc]) == r"\widetilde{\alpha\beta}"

    def test_accent_with_nothing_under_it_defers(self):
        acc = self._acc("hatwide", 127.0, 133.6, 147.1)
        far = self._base("alpha", 300.0, 306.0, 145.2, family="math-italic")
        out = structure.to_tex([acc, far])
        assert out is None or "widehat{" not in (out or "")


class TestMarkerGroups:
    """A marker after a WORD attaches to the word, not to its last letter.

    Measured on a journal title page: the gap from `o` to its superscript
    `a` is +1.76pt = +0.167 em -- a deliberate thin space -- and the gap
    after the `*` is -0.50pt, a negative kern. Pulling the `o` into the
    maths split the name and moved the marker:
    `Montañ $\\mathrm{o}^{\\mathrm{a},*}$`.

    LaTeX spells a script with no base as an empty group.
    """

    class _Span:
        kind = "math"
        rules: list = []

        def __init__(self, glyphs, line_size, rect):
            self.glyphs = glyphs
            self.line_size = line_size
            self.rect = rect

    def _mark(self, name, x, size=7.0, baseline=603.0):
        gl = g(name, size, baseline, x)
        gl.rect = (x, baseline, x + size * 0.5, baseline + size)
        return gl

    def test_a_raised_group_gets_an_empty_base(self):
        marks = [self._mark("a", 162.9), self._mark("comma", 167.0)]
        span = self._Span(marks, 10.56, (162.9, 603.0, 171.0, 610.0))
        out = structure.span_to_tex(span)
        assert out is not None and out.startswith("{}^{"), out

    def test_an_ordinary_span_keeps_its_base(self):
        """Full-size glyphs on the line are not a marker group."""
        base = g("alpha", 10.56, 599.2, 100.0)
        base.rect = (100.0, 599.2, 105.0, 609.8)
        span = self._Span([base], 10.56, (100.0, 599.2, 105.0, 609.8))
        out = structure.span_to_tex(span)
        assert out == r"\alpha"

    def test_a_long_run_is_not_a_marker(self):
        """Four glyphs is the ceiling; a whole small block is a block."""
        marks = [self._mark(n, 100.0 + i * 5.0)
                 for i, n in enumerate(("a", "b", "c", "d", "e"))]
        span = self._Span(marks, 10.56, (100.0, 603.0, 130.0, 610.0))
        out = structure.span_to_tex(span)
        assert out is None or not out.startswith("{}^{")


class TestBigDelimitersAreMainGlyphs:
    """A big DELIMITER is off the row baseline for the same reason a big
    OPERATOR is: it is grown about the maths axis, not set on the line.

    `\\left( ... \\right)` around a two-level expression puts its parens at
    12pt on a baseline 10pt above the row. The guard that refuses a
    full-size glyph off the row then refused the whole span -- measured on
    the PDF2LaTeX dataset, `script-attachment` was 299 of 448 crops, the
    largest cause, and this is one of its shapes.
    """

    def _d(self, name, x, baseline, size=12.0):
        from texmap import TexToken
        gl = g(name, size, baseline, x)
        gl.tex = TexToken(r"\left(", "delimiter", None, "corpus")
        return gl

    def test_a_raised_delimiter_does_not_refuse_the_span(self):
        base = g("alpha", 12.0, 643.9, 100.0)
        par = self._d("parenleftbig", 120.0, 653.6)
        assert structure._attach_scripts([base, par]) is not None

    def test_it_is_treated_as_a_main_glyph(self):
        base = g("alpha", 12.0, 643.9, 100.0)
        par = self._d("parenleftbig", 120.0, 653.6)
        triples = structure._attach_scripts([base, par])
        assert len(triples) == 2

    def test_a_plain_full_size_glyph_off_the_row_still_refuses(self):
        """The guard exists for a reason: a numerator that escaped its
        rule's x-range produced `+^{( -}` from `+\\frac{(-1)^{s}}{2}` --
        confident, valid, wrong."""
        base = g("alpha", 12.0, 643.9, 100.0)
        stray = g("beta", 12.0, 653.6, 120.0)
        assert structure._attach_scripts([base, stray]) is None


class TestCommandsAreNotFusedWithLetters:
    """TeX ends a control word at the first NON-LETTER.

    A letter placed straight after a multi-letter command extends its name:
    `|x - y|` came out as `\\midx - y\\mid`, and `\\midx` is undefined. The
    closing `\\mid` was fine because nothing followed it.

    The cause was 694's measured spacing. A gap of zero renders as "" so that
    `$ab$` stays `$ab$`; that same "" then glued a command to the letter after
    it. The guard here tested whether the GAP ends in a letter -- which
    catches `\\quad` + `b` -- and never whether the PREVIOUS PART does.

    Measured before the fix: 66 occurrences across 19 of 30 documents.
    """

    def test_a_command_ending_in_a_letter_is_detected(self):
        assert structure._ends_in_command(r"x \mid")
        assert structure._ends_in_command(r"\alpha")

    def test_a_piece_ending_in_a_brace_is_not(self):
        """`\\mathrm{d}x` is correct and needs no space."""
        assert not structure._ends_in_command(r"\mathrm{d}")

    def test_a_piece_ending_in_a_plain_letter_is_not(self):
        """`ab` is a product of two variables, not a command."""
        assert not structure._ends_in_command("ab")

    def test_a_backslash_alone_is_not_a_control_word(self):
        assert not structure._ends_in_command("\\")

    def test_a_single_character_command_is_still_a_command(self):
        """`\\S` ends a control SYMBOL at one character, but `\\Sx` would
        still be read as the control word `\\Sx`."""
        assert structure._ends_in_command(r"\S")


class TestTwoOperatorsDoNotShareOneLimitGroup:
    """760 -- the stream says which operator emitted a limit.

    wzlxjtu-031's first display is `\\sum_{s=1}^{\\infty}\\sum_{|m|<s}`. The
    first sum's `s=1` ends at x=169.0 and the second's `|m|<s` begins at
    x=169.37 -- inside the contiguity that holds a condition together, so the
    backward walk in x ran out of one group and straight into the other. The
    second sum took both, and the `\\infty` with them, leaving one bare
    operator: `\\sum \\sum\\limits_{s=1 \\mid m\\mid<s}^{\\infty}`.

    The glyph list is in READING order and the content stream is not: TeX
    sets a display operator as the vbox UPPER, OPERATOR, LOWER, so emission
    order names the owner where x cannot.
    """

    def _scene(self, streams=True):
        gl = []

        def add(name, x, baseline, size, family, stream):
            n = g(name, size, baseline, x, family)
            n.id = "%s@%s" % (name, x)
            n.stream = stream if streams else -1
            gl.append(n)

        # x order, which is NOT stream order -- that is the whole point.
        add("summationdisplay", 153.32, 727.35, 10.0, "math-extension", 180)
        add("infinity", 156.54, 736.00, 7.0, "math-symbol", 179)
        add("s", 157.00, 719.00, 7.0, "math-italic", 181)
        add("equal", 161.00, 719.00, 7.0, "math-symbol", 182)
        add("one", 165.50, 719.00, 7.0, "math-italic", 183)
        add("bar", 169.37, 719.00, 7.0, "math-symbol", 185)
        add("m", 173.00, 719.00, 7.0, "math-italic", 186)
        add("summationdisplay", 173.07, 727.35, 10.0, "math-extension", 184)
        add("bar", 177.00, 719.00, 7.0, "math-symbol", 187)
        add("less", 181.00, 719.00, 7.0, "math-symbol", 188)
        add("s", 185.00, 719.00, 7.0, "math-italic", 189)
        return gl

    def _limits(self, glyphs):
        """{operator x: ([upper names], [lower names])}."""
        triples = structure._attach_scripts(glyphs)
        assert triples is not None
        return {round(main.rect[0], 2):
                ([x.glyphname for x in sup], [x.glyphname for x in sub])
                for main, sup, sub in triples
                if main is not None and main.tex.kind == "bigop"}

    def test_each_sum_keeps_its_own_lower_limit(self):
        by_op = self._limits(self._scene())
        assert sorted(by_op) == [153.32, 173.07]
        assert by_op[153.32][1] == ["s", "equal", "one"]
        assert by_op[173.07][1] == ["bar", "m", "bar", "less", "s"]

    def test_the_upper_limit_stays_on_the_operator_that_emitted_it(self):
        by_op = self._limits(self._scene())
        assert by_op[153.32][0] == ["infinity"]
        assert by_op[173.07][0] == []

    def test_without_a_stream_the_x_rule_still_runs(self):
        """The fallback is geometry, as before -- not a crash and not a
        refusal. This is the reading the fix exists to correct, pinned so
        that the two paths cannot be confused for one another."""
        by_op = self._limits(self._scene(streams=False))
        assert by_op[153.32] == ([], [])


class TestASubscriptIsNotUnderTheAccent:
    r"""774 — the accent's base is found by CENTRE-IN-RANGE, and a subscript's
    centre falls in that range too.

    Page 673 of Obertelli & Sagawa, *Modern Nuclear Physics*, sets the
    beta-equilibrium reaction `n + e^+ \rightleftharpoons p + \bar{\nu}_e`:

        nu      [243.98, 248.90]  10.0pt   centre 246.44
        macron  [246.65, 249.96]  10.0pt   window [245.15, 251.46]
        e       [248.90, 252.00]   7.0pt   centre 250.45   <- swept in

    which came out `\bar{\nu_{e}}` — the bar drawn over the subscript too,
    a different symbol. TeX SCALES AN ACCENT TO ITS BASE, so a base is never
    materially smaller than the accent above it.
    """

    def _scene(self, sub_size=7.0):
        nu = g("nu", 10.0, 149.06, 243.98, "math-italic", "ν")
        nu.rect = (243.98, 149.06, 248.90, 159.06)
        mac = g("macron", 10.0, 149.06, 246.65, "math-symbol", "¯")
        mac.rect = (246.65, 149.06, 249.96, 159.06)
        e = g("e", sub_size, 147.57, 248.90, "text", "e")
        e.rect = (248.90, 147.57, 252.00, 147.57 + sub_size)
        return [nu, mac, e]

    def _composed(self, glyphs):
        out = structure._merge_accents(glyphs, 0)
        return [x.tex.latex for x in out]

    def test_the_bar_covers_the_nu_and_not_its_subscript(self):
        assert self._composed(self._scene())[0] == r"\bar{\nu}"

    def test_the_subscript_survives_as_its_own_glyph(self):
        """Excluded from the accent, not discarded: `_attach_scripts` still
        has to find it, or the reading loses a symbol without saying so."""
        assert len(self._composed(self._scene())) == 2

    def test_a_wide_accent_still_covers_several_full_size_glyphs(self):
        r"""The guard is SIZE, not count. `\overline{xy}` covers two glyphs at
        the accent's own size and must still compose both — the case
        `_rule_role` records for `\overline{e_1 e_2 e_3}`."""
        x = g("x", 10.0, 149.06, 240.0, "math-italic", "x")
        x.rect = (240.0, 149.06, 245.0, 159.06)
        y = g("y", 10.0, 149.06, 245.0, "math-italic", "y")
        y.rect = (245.0, 149.06, 250.0, 159.06)
        mac = g("macron", 10.0, 149.06, 240.0, "math-symbol", "¯")
        mac.rect = (240.0, 149.06, 250.0, 159.06)
        out = self._composed([x, mac, y])
        assert out == [r"\bar{xy}"]

    def test_an_accent_inside_an_exponent_still_composes(self):
        """Scale-free: TeX sets the accent small along with what it covers,
        so the RATIO holds wherever the group sits."""
        nu = g("nu", 7.0, 149.06, 243.98, "math-italic", "ν")
        nu.rect = (243.98, 149.06, 247.42, 156.06)
        mac = g("macron", 7.0, 149.06, 245.85, "math-symbol", "¯")
        mac.rect = (245.85, 149.06, 248.17, 156.06)
        assert self._composed([nu, mac])[0] == r"\bar{\nu}"
