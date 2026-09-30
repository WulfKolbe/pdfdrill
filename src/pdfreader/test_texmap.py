"""Tests for texmap.project — glyph identity -> LaTeX token.

Each test names one property. The corpus counts in CR-2 were produced by
replaying an inventory, which measures coverage but asserts nothing; these
assert behaviour.
"""

import pytest

import texmap
from texmap import UNKNOWN, project


class TestFamilySelectsTheAlphabet:
    """The same glyph name means four different things in four families.

    This is the property a flat name->LaTeX table gets wrong, so it is tested
    first and directly.
    """

    def test_capital_c_in_each_family(self):
        assert project("math-italic", "C").latex == "C"
        assert project("ams-symbol", "C").latex == r"\mathbb{C}"
        assert project("script", "C").latex == r"\mathcal{C}"
        assert project("fraktur", "C").latex == r"\mathfrak{C}"

    def test_cmsy_capitals_are_calligraphic_not_roman(self):
        """In CMSY the Latin capitals ARE the calligraphic alphabet."""
        assert project("math-symbol", "A").latex == r"\mathcal{A}"

    def test_packages_are_reported(self):
        assert project("ams-symbol", "square").package == "amssymb"
        assert project("fraktur", "g").package == "amsfonts"
        assert project("math-italic", "alpha").package is None

    def test_unknown_family_is_unknown(self):
        assert project("text", "a") == UNKNOWN
        assert project("no-such-family", "alpha") == UNKNOWN


class TestGreekAndVariants:
    def test_plain_greek(self):
        assert project("math-italic", "alpha").latex == r"\alpha"
        assert project("math-italic", "omega").latex == r"\omega"

    def test_variant_names_carry_the_var_prefix(self):
        assert project("math-italic", "theta1").latex == r"\vartheta"
        assert project("math-italic", "epsilon1").latex == r"\varepsilon"
        assert project("math-italic", "rho1").latex == r"\varrho"

    def test_named_latin_symbols(self):
        assert project("math-italic", "lscript").latex == r"\ell"
        assert project("math-italic", "star").latex == r"\star"
        assert project("math-italic", "partialdiff").latex == r"\partial"

    def test_mielke_page_209_symbols(self):
        """The two glyphs that arrived as (cid:7)/(cid:4) before the fork."""
        assert project("math-italic", "star").latex == r"\star"
        assert project("math-italic", "lscript").latex == r"\ell"


class TestSizedDelimiters:
    """The SIZE command is encoded in the glyph name, not in the geometry."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("parenleftbig", r"\bigl("),
            ("parenrightbig", r"\bigr)"),
            ("parenleftBig", r"\Bigl("),
            ("parenleftbigg", r"\biggl("),
            ("parenleftBigg", r"\Biggl("),
            ("bracketleftbig", r"\bigl["),
            ("bracketrightbigg", r"\biggr]"),
            ("braceleftBig", r"\Bigl\{"),
            ("angbracketleftbig", r"\bigl\langle"),
        ],
    )
    def test_size_and_side(self, name, expected):
        t = project("math-extension", name)
        assert t.latex == expected
        assert t.kind == "delimiter"

    def test_sideless_delimiter_takes_no_lr_variant(self):
        """`\\bigl/` is a syntax error: / is a symbol, not a fence."""
        t = project("math-extension", "slashbig")
        assert t.latex == r"\big/"
        assert t.kind == "delimiter"
        assert project("math-extension", "slashbigg").latex == r"\bigg/"


class TestFragmentsAreNotTokens:
    """An extensible delimiter is several glyphs and ONE LaTeX token.

    Emitting a piece on its own would produce syntactically valid but wrong
    LaTeX, which is worse than emitting nothing.
    """

    @pytest.mark.parametrize(
        "name",
        [
            "bracketlefttp", "bracketleftex", "bracketleftbt",
            "bracketrighttp", "bracketrightex", "bracketrightbt",
            "braceleftmid", "bracerightmid", "braceex",
            "bracehtipdownleft", "bracehtipupright", "vextendsingle",
        ],
    )
    def test_piece_yields_no_latex(self, name):
        t = project("math-extension", name)
        assert t.kind == "fragment"
        assert t.latex is None, "a fragment must never project alone"


class TestBigOperators:
    def test_display_and_text_both_map(self):
        assert project("math-extension", "summationdisplay").latex == r"\sum"
        assert project("math-extension", "summationtext").latex == r"\sum"
        assert project("math-extension", "integraldisplay").latex == r"\int"
        assert project("math-extension", "contintegraldisplay").latex == r"\oint"

    def test_kind_is_bigop(self):
        assert project("math-extension", "productdisplay").kind == "bigop"


class TestRuleDependent:
    def test_radical_sign_is_flagged_rule_dependent(self):
        """`radicalbig` is the SIGN. Its vinculum is a rule, so the extent of
        the argument is not knowable from this glyph alone."""
        for name in ("radicalbig", "radicalBig", "radicalbigg", "radicalBigg"):
            t = project("math-extension", name)
            assert t.latex == r"\sqrt"
            assert t.kind == "rule", "caller must consult rule geometry"


class TestAccents:
    def test_wide_accents(self):
        assert project("math-extension", "tildewide").latex == r"\widetilde"
        assert project("math-extension", "tildewidest").latex == r"\widetilde"
        assert project("math-extension", "hatwide").latex == r"\widehat"
        assert project("math-extension", "hatwide").kind == "accent"

    def test_symbol_accents_are_marked_accent_not_atom(self):
        for name in ("circumflex", "tilde", "caron", "macron", "dieresis"):
            assert project("math-symbol", name).kind == "accent"

    def test_vector_is_an_accent(self):
        assert project("math-italic", "vector").kind == "accent"


class TestAbstention:
    """Guarantee G2: an unverified mapping must never reach LaTeX output."""

    @pytest.mark.parametrize(
        "family,name",
        [
            # circlecopyrt was here until 706. It was refused as unverified for
        # months; RENDERED at 600dpi from a journal front page it is
        # unmistakable -- the ring of a copyright sign with a `c` from the
        # TEXT font inside it. Abstention was right until someone looked.
            ("ams-symbol", "anticlockwise"),
            ("ams-symbol", "epsiloninv"),
            ("ams-symbol", "triangleinv"),
        ],
    )
    def test_unverified_names_yield_no_latex(self, family, name):
        t = project(family, name)
        assert t.latex is None
        assert t.confidence == "unverified"

    def test_missing_glyphname_is_unknown(self):
        assert project("math-italic", None) == UNKNOWN
        assert project("math-italic", "") == UNKNOWN

    def test_projection_is_total(self):
        """G3: every input yields a TexToken. No exception, no None return."""
        for family in ("math-italic", "math-symbol", "math-extension",
                       "ams-symbol", "script", "fraktur", "text", ""):
            for name in ("alpha", "zzz-not-a-glyph", "A", "bracketleftex", None):
                t = project(family, name)
                assert t is not None
                assert hasattr(t, "latex") and hasattr(t, "kind")

    def test_unknown_is_distinguishable_from_fragment(self):
        """Both have latex None but mean different things to the caller:
        a fragment will be merged, an unknown must keep its blob."""
        assert project("math-extension", "bracketleftex").kind == "fragment"
        assert project("math-extension", "zzz").kind == "unknown"


class TestNamesFoundInALargeCorpus:
    """Names that a 1962-page linear-algebra text turned up in bulk.

    Each was previously UNKNOWN and deferred to a crop. The counts are the
    occurrences in that one book, which is why they were worth adding.
    """

    def test_latticetop_is_the_transpose(self):
        """cmsy10 0x3E. 3738 occurrences: `A^{\\top}`, not a lattice."""
        assert project("math-symbol", "latticetop").latex == r"\top"

    def test_openbullet_is_composition(self):
        """cmsy10 0x0E, 1011 occurrences: `f \\circ g`."""
        assert project("math-symbol", "openbullet").latex == r"\circ"

    def test_extensible_double_bar_is_a_fragment(self):
        """1258 occurrences: a piece of a built-up `\\|`, never a token."""
        t = project("math-extension", "vextenddouble")
        assert t.kind == "fragment" and t.latex is None

    def test_musical_symbols_live_in_the_italic_font(self):
        for name, want in (("flat", r"\flat"), ("sharp", r"\sharp"),
                           ("natural", r"\natural")):
            assert project("math-italic", name).latex == want, name

    def test_order_relations(self):
        for name, want in (("follows", r"\succ"),
                           ("followsequal", r"\succeq"),
                           ("precedesequal", r"\preceq")):
            assert project("math-symbol", name).latex == want, name

    def test_wide_accent_in_an_ams_font_is_still_an_accent(self):
        t = project("ams-symbol", "hatwide")
        assert t.latex == r"\widehat" and t.kind == "accent"

    def test_msam_corner_marks_still_abstain(self):
        """Which command these are has not been verified."""
        for name in ("rightanglese", "rightanglesw"):
            assert project("ams-symbol", name).latex is None, name


class TestGreekLivesInTheRomanFont:
    """TeX sets UPPERCASE Greek in the roman TEXT font, not the maths font.

    In OT1 `\\Gamma` is cmr slot 0x00, so the glyph arrives from CMR12 with
    family "text-cm". Classifying by font alone left `\\Gamma^{+}(\\Phi)` sitting
    in a prose span, where a non-ASCII letter projects to nothing -- the whole
    span deferred to a crop, on every page that names a Clifford group.
    """

    def test_uppercase_greek_from_any_font(self):
        from texmap import greek_latex
        for name, want in (("Gamma", r"\Gamma"), ("Phi", r"\Phi"),
                           ("Omega", r"\Omega"), ("Lambda", r"\Lambda")):
            assert greek_latex(name) == want, name

    def test_lowercase_and_variants_too(self):
        from texmap import greek_latex
        assert greek_latex("alpha") == r"\alpha"
        assert greek_latex("theta1") == r"\vartheta"

    def test_non_greek_names_are_not_claimed(self):
        from texmap import greek_latex
        for name in ("star", "lscript", "A", "circlemultiply", None, ""):
            assert greek_latex(name) is None, name


class TestGreekGlyphsAreMaths:
    def test_greek_in_a_text_font_counts_as_maths(self):
        from docmodel_six import GlyphNode
        from texmap import project
        n = GlyphNode(id="g", page=1, rect=(0, 0, 8, 12), text="\u0393",
                      cid=0, glyphname="Gamma", fontname="ABC+CMR12",
                      family="text-cm", size=12.0,
                      tex=project("text-cm", "Gamma"))
        assert n.is_math, "a Greek letter is maths whatever font carries it"

    def test_it_projects_to_the_command(self):
        from docmodel_six import GlyphNode, glyph_latex
        from texmap import project
        n = GlyphNode(id="g", page=1, rect=(0, 0, 8, 12), text="\u0393",
                      cid=0, glyphname="Gamma", fontname="ABC+CMR12",
                      family="text-cm", size=12.0,
                      tex=project("text-cm", "Gamma"))
        assert glyph_latex(n) == r"\Gamma"


class TestAccentSizesAndSlantedRelations:
    """Names found by inventorying a 531-page InDesign book."""

    def test_all_three_accent_sizes(self):
        """cmex10 carries each wide accent in three sizes. Only the base name
        was listed, so `hatwider` deferred whole spans."""
        for name in ("hatwide", "hatwider", "hatwidest"):
            assert project("math-extension", name).latex == r"\widehat", name
        for name in ("tildewide", "tildewider", "tildewidest"):
            assert project("math-extension", name).latex == r"\widetilde", name

    def test_slanted_order_relations(self):
        assert project("ams-symbol", "lessorequalslant").latex == r"\leqslant"
        assert project("ams-symbol", "greaterorequalslant").latex == r"\geqslant"

    def test_radical_sizes_are_all_rules(self):
        """Every radical size needs COMPOSITION with its vinculum, so each
        must report kind 'rule' rather than emitting a bare `\\sqrt`."""
        for name in ("radical", "radicalbig", "radicalBig", "radicalbigg",
                     "radicalBigg"):
            t = project("math-extension", name)
            assert t.kind == "rule", (name, t.kind)


class TestMonospaceDetection:
    def test_tex_typewriter_faces(self):
        from texmap import is_monospace
        for name in ("CMTT10", "ABC+CMTT9", "CMSLTT10", "CMITT10"):
            assert is_monospace(name), name

    def test_common_mono_faces(self):
        from texmap import is_monospace
        for name in ("Courier", "Courier-Bold", "Consolas", "Inconsolata",
                     "DejaVuSansMono", "Menlo"):
            assert is_monospace(name), name

    def test_proportional_faces_are_not(self):
        from texmap import is_monospace
        for name in ("CMR10", "CMMI7", "CMBX12", "Times-Roman", "Helvetica"):
            assert not is_monospace(name), name


class TestMeasuredMonospace:
    """Names carry no reliable signal.

    Measured on one journal page: `lmt-regular` is Latin Modern Typewriter
    (91% of glyphs share one advance ratio) while `t1-uni-regular` sets the
    listings and is PROPORTIONAL (25%). Nothing in either name says so.
    """

    def _samples(self, font, ratios, chars):
        out = []
        for i in range(200):
            out.append((f"ABC+{font}", ratios[i % len(ratios)] * 10.0, 10.0,
                        chars[i % len(chars)]))
        return out

    def test_a_uniform_face_is_monospace(self):
        from texmap import measure_monospace
        s = self._samples("lmt-regular", [0.525] * 9 + [0.344],
                          "abcdefghijklmnop")
        assert "lmt-regular" in measure_monospace(s)

    def test_a_proportional_face_is_not(self):
        from texmap import measure_monospace
        s = self._samples("t1-uni-regular", [0.556, 0.611, 0.278, 0.333],
                          "abcdefghijklmnop")
        assert "t1-uni-regular" not in measure_monospace(s)

    def test_a_font_used_only_for_spaces_is_not(self):
        """Uniform by accident: 517 glyphs, all of them spaces."""
        from texmap import measure_monospace
        s = [("ABC+LMRoman10", 3.33, 10.0, " ")] * 200
        assert "LMRoman10" not in measure_monospace(s)

    def test_a_digits_and_symbols_font_is_not(self):
        """Measured: CMR8 is 0.930 uniform with only 4 letters among its 17
        characters -- uniform by accident. Uniformity alone cannot tell it
        from a real typewriter face at 0.920; the alphabet can."""
        from texmap import measure_monospace
        s = self._samples("CMR8", [0.5], "()+012345678=dmo")
        assert "CMR8" not in measure_monospace(s)

    def test_measurement_overrides_the_name(self):
        from texmap import is_monospace, set_measured_monospace
        try:
            set_measured_monospace({"t1-uni-regular"})
            assert is_monospace("ABC+t1-uni-regular")
        finally:
            set_measured_monospace(set())


class TestUnicodeNamedGlyphs:
    """A publisher's maths font names glyphs by CODEPOINT.

    STIXMath emits `u1D460` and `uni2032` where Computer Modern emits `s` and
    `prime`. Measured across three journal papers, that dialect was the
    single largest cause of deferral -- 48 glyphs of one document's
    mathematics with nothing wrong but the name.
    """

    def test_codepoint_is_read_from_the_name(self):
        from texmap import codepoint_of
        assert codepoint_of("u1D460") == 0x1D460
        assert codepoint_of("uni2032") == 0x2032

    def test_a_variant_suffix_is_tolerated(self):
        """`uni2032.var` is how a font names a second design of one
        character."""
        from texmap import codepoint_of
        assert codepoint_of("uni2032.var") == 0x2032

    def test_a_postscript_name_is_not_a_codepoint(self):
        from texmap import codepoint_of
        assert codepoint_of("alpha") is None
        assert codepoint_of("space") is None

    def test_mathematical_italic_letters_decompose(self):
        """U+1D460 is MATHEMATICAL ITALIC SMALL S; maths italic is already
        the default, so the letter alone is right."""
        from texmap import unicode_latex
        assert unicode_latex("u1D460") == "s"
        assert unicode_latex("u1D454") == "g"

    def test_mathematical_italic_greek_decomposes(self):
        from texmap import unicode_latex
        assert unicode_latex("u1D708") == r"\nu"
        assert unicode_latex("u1D6FF") == r"\delta"

    def test_styled_alphabets_keep_their_style(self):
        from texmap import unicode_latex
        assert unicode_latex("u1D538") == r"\mathbb{A}"
        assert unicode_latex("u1D49C") == r"\mathcal{A}"
        assert unicode_latex("u1D400") == r"\mathbf{A}"

    def test_ordinary_maths_operators(self):
        from texmap import unicode_latex
        assert unicode_latex("uni2032") == r"\prime"
        assert unicode_latex("uni2264") == r"\leq"
        assert unicode_latex("uni2208") == r"\in"

    def test_an_unknown_codepoint_defers(self):
        from texmap import unicode_latex
        assert unicode_latex("uniE000") is None      # private use area


class TestMathSpacing:
    """A LaTeX space emits NO GLYPH.

    Measured on a table of all thirteen forms compiled with pdflatex: every
    one is a pure advance of the current point, and the advances are
    quantised in em -- 3mu is 1/6, 4mu is 2/9, 5mu is 5/18, quad is 1, qquad
    is 2. `\\!` is NEGATIVE, -1/6 em.

    Recovering the COMMAND from the width is a different matter, and two
    measurements said no: TeX inserts spacing automatically by atom class (a
    binary operator takes 4mu either side, a relation 5mu), and an align
    environment leaves an em or more before its relation. Mapping every band
    produced 48.8 spacing commands per 1000 tokens on a real paper -- far
    more than any author writes -- and `\\quad` fired on alignment gaps.
    What survives is what geometry alone can settle.
    """

    def test_a_negative_gap_is_an_explicit_kern(self):
        from texmap import math_space
        assert math_space(-0.167) == r"\!"

    def test_abutting_glyphs_get_no_space(self):
        """`$ab$` must not become `$a b$`."""
        from texmap import math_space
        assert math_space(0.0) == ""
        assert math_space(0.05) == ""

    def test_an_ordinary_gap_is_an_ordinary_space(self):
        from texmap import math_space
        assert math_space(0.167) == " "
        assert math_space(0.333) == " "

    def test_automatic_spacing_is_not_reported_as_a_command(self):
        """4mu and 5mu are what TeX puts round a binary operator and a
        relation; emitting `\\:`/`\\;` there would double the spacing on
        recompile."""
        from texmap import math_space
        assert math_space(0.222) == " "
        assert math_space(0.278) == " "

    def test_an_alignment_gap_is_not_a_quad(self):
        from texmap import math_space
        assert math_space(1.0) == " "
        assert math_space(2.0) == " "


class TestLatinModernIsMaths:
    """Latin Modern is Computer Modern's successor and what every
    lualatex/xelatex document ships. Its maths fonts fell through to "text",
    so none of their glyph names were projected -- measured, 81 of the small
    crops in one corpus pass were LM `prime`, `element`, `lscript` and
    `asteriskmath`, every one of which the table already knew under its
    Computer Modern name.
    """

    def test_lm_maths_italic(self):
        from texmap import family_of
        assert family_of("ABC+LMMathItalic8-Regular") == "math-italic"

    def test_lm_maths_symbols(self):
        from texmap import family_of
        assert family_of("ABC+LMMathSymbols8-Regular") == "math-symbol"

    def test_lm_maths_extension(self):
        from texmap import family_of
        assert family_of("ABC+LMMathExtension10-Regular") == "math-extension"

    def test_lm_text_faces_stay_text(self):
        from texmap import family_of
        assert family_of("ABC+LMRoman10-Regular") == "text-cm"
        assert family_of("ABC+LMSans10-Regular") == "text-cm"

    def test_the_names_now_project(self):
        from texmap import family_of, project
        for name, want in (("prime", r"\prime"), ("element", r"\in"),
                           ("asteriskmath", r"\ast")):
            fam = family_of("LMMathSymbols8-Regular")
            assert project(fam, name).latex == want, name
        assert project(family_of("LMMathItalic8-Regular"),
                       "lscript").latex == r"\ell"


class TestAmsNamesFromTheCorpus:
    """The commonest AMS glyph names the table did not carry, found by a
    corpus pass over small crops."""

    def test_defines_was_identified_by_rendering(self):
        """Rendered at 500dpi out of a real page: a triangle over an equals
        sign. Not inferred from the name."""
        from texmap import project
        assert project("ams-symbol", "defines").latex == r"\triangleq"

    def test_the_similar_relations(self):
        from texmap import project
        assert project("ams-symbol", "lessorsimilar").latex == r"\lesssim"
        assert project("ams-symbol", "greaterorsimilar").latex == r"\gtrsim"

    def test_a_vendor_symbol_font_reaches_the_ams_names(self):
        """MathTime's MTSYN carries AMS names alongside the CMSY set, and
        refusing them there sent a symbol the table knows to a crop."""
        from texmap import family_of, project
        fam = family_of("MTSYN")
        assert fam == "math-symbol"
        assert project(fam, "subsetsqequal").latex == r"\sqsubseteq"

    def test_an_unknown_name_still_defers(self):
        from texmap import project
        assert project("ams-symbol", "notarealglyph").latex is None


class TestVendorMathsFonts:
    """A publisher's or package's maths font supplies its own punctuation.

    Found by working the user's 11,716-crop list: three arXiv papers whose
    failures were almost entirely brackets and operators that the plain
    table already knew, refused because of the FONT they came from.
    """

    def test_mnsymbol_is_a_maths_font(self):
        """Unknown, it fell through to text: 3721 failures on one 476-page
        paper, 3239 of them a single glyph."""
        from texmap import family_of
        assert family_of("ABC+MnSymbol7") == "math-symbol"
        assert family_of("ABC+MnSymbol10") == "math-symbol"

    def test_minute_is_a_prime(self):
        """Verified by rendering `f'` at 500dpi, not inferred."""
        from texmap import project
        assert project("math-symbol", "minute").latex == r"\prime"

    def test_a_maths_font_supplies_its_brackets(self):
        """12333 parentheses from MnSymbol10 on one paper."""
        from texmap import project
        assert project("math-symbol", "parenleft").latex == "("
        assert project("math-symbol", "parenright").latex == ")"

    def test_a_variant_suffix_is_a_design_not_a_character(self):
        """`parenright.alt1` is a second design of the same bracket; 1464 of
        them were refused for carrying the suffix."""
        from texmap import project
        assert project("math-symbol", "parenright.alt1").latex == ")"
        assert project("math-symbol", "parenleft.alt1").latex == "("

    def test_a_fraktur_font_supplies_its_brackets(self):
        """A formula set in Euler emits its parentheses from EUFM10, not from
        the maths font beside it: 1200 failures on one paper."""
        from texmap import family_of, project
        fam = family_of("EUFM10")
        assert fam == "fraktur"
        assert project(fam, "parenleft").latex == "("
        assert project(fam, "equal").latex == "="

    def test_a_fraktur_letter_is_still_fraktur(self):
        from texmap import project
        assert project("fraktur", "A").latex == r"\mathfrak{A}"

    def test_a_script_letter_is_still_script(self):
        from texmap import project
        assert project("script", "B").latex == r"\mathcal{B}"

    def test_an_unknown_name_still_defers(self):
        from texmap import project
        assert project("math-symbol", "notarealglyphname").latex is None


class TestTexSpacingTableInverted:
    """TeX's spacing table, read BACKWARDS.

    TeX inserts space between two atoms as a function of their CLASSES, from
    a fixed 8x8 table with four values: 0, thin 3mu, medium 4mu, thick 5mu.

    Read forwards that is a nuisance -- 694 measured that an author's `\\:`
    and a binary operator's automatic 4mu are the same width, and concluded
    the classes were unrecoverable.

    Read backwards it is a SIGNAL: the space TeX inserted is evidence for the
    pair of classes that produced it. Measured on one paper, 1887 gaps: 81.3%
    land on the four table values. Baker, Sexton & Sorge (DAS 2010) use this
    to tell a calligraphic `R` used as a RELATION from one used as a letter.
    """

    def test_the_four_classes(self):
        from texmap import space_class
        assert space_class(0.0) == 0
        assert space_class(0.167) == 1
        assert space_class(0.222) == 2
        assert space_class(0.278) == 3

    def test_a_gap_off_the_table_is_not_a_class(self):
        """An author's `\\quad`, an alignment, or a word space."""
        from texmap import space_class
        assert space_class(1.0) is None
        assert space_class(0.5) is None

    def test_thick_space_means_a_relation(self):
        """Every pair producing a thick space has Rel on one side."""
        from texmap import class_pairs
        pairs = class_pairs(3)
        assert pairs
        assert all("Rel" in p for p in pairs), pairs

    def test_medium_space_means_a_binary_operator(self):
        from texmap import class_pairs
        pairs = class_pairs(2)
        assert pairs
        assert all("Bin" in p or "Inner" in p for p in pairs), pairs

    def test_the_inverse_is_not_unique(self):
        """A constraint, not an answer: it narrows 64 pairs to a handful."""
        from texmap import class_pairs
        assert 1 < len(class_pairs(3)) < 12
        assert 1 < len(class_pairs(2)) < 12

    def test_impossible_pairs_are_absent(self):
        """A `*` in the table: TeX converts one atom first, so the pair
        never occurs."""
        from texmap import class_pairs
        for space in (0, 1, 2, 3):
            assert ("Bin", "Bin") not in class_pairs(space)
            assert ("Bin", "Rel") not in class_pairs(space)


class TestFontsWithNoEncoding:
    """Most TeX maths fonts carry NO /Encoding, so pdfminer falls back to
    StandardEncoding and the fork reports that fallback as the font's own
    name. Rendered from 1.pdf at 500dpi, exact glyph boxes side by side:

        TeX-matha10  cid 16  ->  "quotedblleft"  really  =
        TeX-matha10  cid 18  ->  "quotedblbase"  really  ~
        TeX-matha10  cid 24  ->  "perthousand"   really  !=
        TeX-matha10  cid 80  ->  "P"             really  in
        TeX-matha10  cid 82  ->  "R"             really  notin
        TeX-matha10  cid 112 ->  "p"             really  (
        TeX-matha10  cid 113 ->  "q"             really  )

    The CID is right; only the NAME is wrong. Before the fork there was no
    name and the span deferred, which was correct -- the fork turned an
    abstention into a confident wrong answer, reading
    `\\pi^{*}(\\omega_{0})` as `\\pi^{*}p\\omega_{0}q`.
    """

    def test_a_latin_letter_in_a_symbol_font_is_the_fallback(self):
        from texmap import untrusted_name
        assert untrusted_name("ABC+TeX-matha10", "p")
        assert untrusted_name("ABC+CMEX10", "R")

    def test_a_text_punctuation_name_in_a_symbol_font_too(self):
        from texmap import untrusted_name
        assert untrusted_name("ABC+TeX-matha10", "quotedblleft")
        assert untrusted_name("ABC+TeX-matha10", "perthousand")

    def test_a_letter_in_a_font_that_HAS_letters_is_trusted(self):
        """CMMI carries the maths italic alphabet at its ASCII slots, so `p`
        there really is `p`. Distrusting it would break every variable."""
        from texmap import untrusted_name
        assert not untrusted_name("ABC+CMMI10", "p")
        assert not untrusted_name("ABC+CMSY10", "A")

    def test_a_real_symbol_name_is_trusted(self):
        from texmap import untrusted_name
        assert not untrusted_name("ABC+CMEX10", "summationdisplay")

    def test_the_verified_slots(self):
        """Only slots rendered and read off the page are in the table."""
        from texmap import tex_slot
        assert tex_slot("ABC+TeX-matha10", 112) == "parenleft"
        assert tex_slot("ABC+TeX-matha10", 80) == "element"
        assert tex_slot("ABC+TeX-matha7", 82) == "notelement"

    def test_an_unverified_slot_yields_nothing(self):
        """Abstention, not a guess -- the bug being fixed here was a guess."""
        from texmap import tex_slot
        assert tex_slot("ABC+TeX-matha10", 99) is None
        assert tex_slot("ABC+CMMI10", 112) is None

    def test_the_tex_maths_fonts_are_maths(self):
        from texmap import family_of
        assert family_of("ABC+TeX-matha10") == "math-symbol"
        assert family_of("ABC+TeX-mathx10") == "math-extension"


class TestLimitPlacementIsATable:
    """Which operators take limits is DECLARED, never inferred.

    The table is amsopn.sty's own: `\\qopname\\relax m{...}` for movable
    limits, `o{...}` for ordinary. It is here as a test because the wrong
    half of it is plausible -- `\\dim`, `\\ker`, `\\deg`, `\\hom` and `\\arg`
    are short upright operator names that take a subscript, exactly like
    `\\max`, and LaTeX puts their scripts BESIDE them. Reading them as limit
    operators makes a pass claim the preceding term's scripts.
    """

    def test_the_movable_limit_operators(self):
        for name in ("max", "min", "sup", "inf", "lim", "liminf", "limsup",
                     "det", "gcd", "Pr", "injlim", "projlim", "varlimsup"):
            assert texmap.takes_limits("\\\\" + name), name

    def test_the_ones_that_only_look_like_them(self):
        for name in ("dim", "hom", "ker", "deg", "arg"):
            assert not texmap.takes_limits("\\\\" + name), name

    def test_ordinary_function_names_never_take_limits(self):
        for name in ("sin", "cos", "tan", "log", "ln", "exp", "tanh", "sinh"):
            assert not texmap.takes_limits("\\\\" + name), name

    def test_sum_class_takes_limits_only_in_DISPLAY_size(self):
        assert texmap.takes_limits(None, "summationdisplay")
        assert texmap.takes_limits(None, "productdisplay")
        # the same operator set in text style puts its limits beside it
        assert not texmap.takes_limits(None, "summationtext")

    def test_integrals_do_NOT_take_limits_above_and_below(self):
        """`\\int` is \\nolimits by default, even in display style.

        Measured on the corpus, where the scripts actually sit:
        summationdisplay 140 under / 59 beside, productdisplay 59 / 11,
        integraldisplay 2 under / 21 beside.
        """
        assert not texmap.takes_limits(None, "integraldisplay")
        assert not texmap.takes_limits(None, "contourintegraldisplay")

    def test_the_two_classes_do_not_overlap(self):
        assert not (texmap.LIMIT_OPERATORS
                    & texmap.LARGE_OPERATORS_DISPLAY)
        assert not (texmap.LARGE_OPERATORS_DISPLAY
                    & texmap.LARGE_OPERATORS_TEXT)


# --- 737: the doublestroke font ----------------------------------------------

def test_dsrom_is_a_maths_family_not_text():
    """`dsrom12` is the `dsfont` package's font and every glyph of it is
    double-struck. Read as TEXT, its `one` -- the IDENTITY MATRIX -- became an
    ordinary `1` and the symbol stopped being itself: eight times in
    wzlxjtu-026, against a gold that writes `\\mathds{1}` eight times."""
    assert texmap.family_of("UTBNOO+dsrom12") == "doublestroke"
    assert texmap.family_of("ABCDEF+dsrom10") == "doublestroke"


def test_doublestroke_projects_to_mathds_not_mathbb():
    r"""NOT `\mathbb`. amssymb's blackboard alphabet is msbm's, which carries
    A-Z and no digits -- msbm's `1` slot is `\nVdash`, so `\mathbb{1}`
    TYPESETS THE LOGIC SYMBOL U+22AE, "does not force". Verified by compiling
    it: `$\mathbb{1}$` under amssymb comes back out of the PDF as U+22AE.
    That is what MathPix emits here, nine times over this corpus."""
    t = texmap.project("doublestroke", "one")
    assert t.latex == r"\mathds{1}"
    assert t.package == "dsfont"


def test_doublestroke_letters_too():
    assert texmap.project("doublestroke", "R").latex == r"\mathds{R}"


def test_a_doublestroke_glyph_is_mathematics():
    """Left out of MATH_FAMILIES its glyphs land in TEXT spans, which carry no
    LaTeX -- so the one `\\mathds{1}` of wzlxjtu-026 that sits in an inline
    formula rather than a display was dropped without trace."""
    import docmodel_six
    assert "doublestroke" in docmodel_six.MATH_FAMILIES


class TestTheHorizontalHarpoonPair:
    r"""771 — the AMS font names a harpoon by its BARBS, LaTeX by its heads.

    1609.05293 page 11 sets `Cost(Q^{left} ⇌^{op} Q^{right})` from
    GDXIPD+MSAM10 cid 10, whose embedded glyph name is `harpoonleftright`.
    Read as a name it says left-then-right; rendered at 12x it is a top bar
    with a RIGHT arrowhead over a bottom bar with a LEFT one, which is
    `\rightleftharpoons`. The name and the macro read backwards from each
    other, so this pair is settled by the rendering and pinned here.

    Unmapped, the glyph reached the markdown as `(cid:10)` and took its span
    with it — on a document MathPix reads correctly.
    """

    def test_harpoonleftright_is_rightleftharpoons(self):
        assert texmap.project("math-symbol", "harpoonleftright").latex \
            == r"\rightleftharpoons"

    def test_harpoonrightleft_is_the_other_one(self):
        assert texmap.project("math-symbol", "harpoonrightleft").latex \
            == r"\leftrightharpoons"

    def test_the_vertical_harpoons_are_unchanged(self):
        """The four already mapped, which the name reads the same way round."""
        for name, want in (("harpoonupright", r"\upharpoonright"),
                           ("harpoonupleft", r"\upharpoonleft"),
                           ("harpoondownright", r"\downharpoonright"),
                           ("harpoondownleft", r"\downharpoonleft")):
            assert texmap.project("math-symbol", name).latex == want

    def test_it_is_mathematics_not_an_unknown(self):
        t = texmap.project("math-symbol", "harpoonleftright")
        assert t.kind != "unknown" and t.latex is not None


class TestTheSubstituteFontsSpellItalicShort:
    r"""776 — `is_italic` decides whether a text-font letter on a display line
    is a VARIABLE (775), so a name it does not recognise costs every variable
    in that document.

    Surveyed over the 7,376 distinct font names in the library, it refused 29
    genuinely italic ones. URW's Nimbus faces are what Ghostscript and pdftex
    substitute with, so they appear in anything that does not ship its own:

        NimbusRomNo9L-ReguItal        483 documents
        NimbusRomNo9L-MediItal        121
        NimbusRomNo9L-Regu-Slant_167   35
        StandardSymL-Slant_167         33

    `ReguItal` carries neither the word "italic" nor a hyphen before "Ital",
    which is what the old pattern required.
    """

    def test_the_urw_substitutes_are_italic(self):
        for name in ("AAAAAA+NimbusRomNo9L-ReguItal",
                     "AAAAAA+NimbusRomNo9L-MediItal",
                     "AAAAAA+NimbusSanL-ReguItal",
                     "AAAAAA+URWPalladioL-BoldItal"):
            assert texmap.is_italic(name), name

    def test_a_slanted_instance_is_italic_here(self):
        """`Slant_167` is a slanted instance: italic for every purpose this
        flag is used for."""
        for name in ("AAAAAA+NimbusRomNo9L-Regu-Slant_167",
                     "AAAAAA+StandardSymL-Slant_167",
                     "AAAAAA+LMRomanSlant10-Regular"):
            assert texmap.is_italic(name), name

    def test_an_oblique_monospace_is_italic(self):
        assert texmap.is_italic("AAAAAA+NimbusMonL-ReguObli")

    def test_the_upright_faces_are_still_upright(self):
        """The opposite error would put prose into mathematics. Checked over
        every name in the library: no upright one matches."""
        for name in ("AAAAAA+NimbusRomNo9L-Regu", "AAAAAA+Times-Roman",
                     "AAAAAA+SFRM1000", "AAAAAA+CMR10",
                     "AAAAAA+NimbusRomNo9L-Medi", "AAAAAA+Helvetica-Bold"):
            assert not texmap.is_italic(name), name

    def test_a_weight_suffix_does_not_make_it_upright(self):
        r"""`LMMathItalic10-Regular` is italic; `-Regular` is its WEIGHT."""
        assert texmap.is_italic("AAAAAA+LMMathItalic10-Regular")


class TestTheMathabxDeclarationFileNamesItsOwnSlots:
    r"""779 — `MATHABX` is `mathabx.dcl` read out, 573 (font, slot) → name
    pairs, and it was consulted only by `texpackages` — to decide which
    packages a PREAMBLE needs. Nothing ever asked it what a CID means.

    So the two documents it was built from still lost their mathematics:
    31 of the corpus's crops, all `unmapped-glyph`, all in wzlxjtu-001 and
    -002, the AAAI templates that load the package. `matha` slot 0xA4 comes
    back from pdfminer as `dcaron`; the package declares it `leq`.
    """

    def test_the_slot_lookup_finds_the_declared_name(self):
        for cid, want in ((164, "leq"), (165, "geq")):
            assert texmap.mathabx_slot("AAAAAA+TeX-matha10", cid) == want

    def test_it_knows_the_three_fonts(self):
        assert texmap.mathabx_slot("AAAAAA+TeX-mathx10", 7) == "vert"
        assert texmap.mathabx_slot("AAAAAA+TeX-mathb10", 5) == "square"

    def test_a_font_it_does_not_cover_gets_nothing(self):
        assert texmap.mathabx_slot("AAAAAA+CMMI10", 164) is None

    def test_a_slot_the_package_does_not_declare_gets_nothing(self):
        r"""`mathabx.dcl` declares neither matha 112 nor 113, and they occur
        73 times each. Abstaining there is the point."""
        assert texmap.mathabx_slot("AAAAAA+TeX-matha10", 112) is None

    def test_the_name_maps_onto_this_table_s_own_glyph_name(self):
        """Not to LaTeX directly — so kind, package registration and the
        dialect comparison keep working from one place."""
        assert texmap.mathabx_tex("leq") == "lessequal"
        assert texmap.project("math-symbol", "lessequal").latex == r"\leq"

    def test_an_undeclared_name_abstains_rather_than_guessing(self):
        r"""`"\\" + name` would emit `\coasterisk` for slots nobody has
        verified. A name absent here leaves the glyph unmapped and the span
        defers exactly as before."""
        assert texmap.mathabx_tex("coasterisk") is None
        assert texmap.mathabx_tex(None) is None

    def test_the_rendered_table_still_outranks_the_declaration(self):
        r"""`tex_slot` was verified by rendering each slot at 500dpi, which
        outranks a declaration file."""
        assert texmap.tex_slot("AAAAAA+TeX-matha10", 112) == "parenleft"


class TestMonospaceNamesFromTheFontCensus:
    """781n — measured over 18,685 distinct `/BaseFont` names from the
    6,101 PDFs of the IUST object corpus (arXiv 1812.09961), which is a
    font-dictionary census rather than the 102 documents we own.

    The old rule anchored `mono` at the END of a name, so it caught
    `LiberationMono` and missed `Monospace821BT-Roman` -- 98 occurrences,
    the commonest typewriter name in that sample.
    """

    def test_the_names_the_end_anchor_missed(self):
        for name in ("Monospace821BT-Roman", "Monospace821BT-Italic",
                     "Gen.Monospac821-BT", "DroidSansMono-Slant_213",
                     "FiraMono-Regular-Identity-H", "TheSansMonoLF"):
            assert texmap.is_monospace(name), name

    def test_lmodern_typewriter(self):
        """What `lmodern` makes \\ttfamily, so any modern LaTeX listing."""
        for name in ("LMTypewriter10-Regular", "LMTypewriter9-Regular",
                     "LMTypewriter10-Dark", "UMTypewriter",
                     "LucidaSans-Typewriter", "P22Typewriter"):
            assert texmap.is_monospace(name), name

    def test_monotype_is_a_foundry_not_a_pitch(self):
        """MonotypeCorsiva is a SCRIPT face. 4 names, 5 occurrences in the
        census -- small, but the exclusion costs nothing and the false
        positive would be silent."""
        for name in ("MonotypeCorsiva", "MonotypeCorsiva,Italic",
                     "AAvaMA+MonotypeCorsiva"):
            assert not texmap.is_monospace(name), name

    def test_lm_mono_proportional_is_not_fixed_pitch(self):
        """`LMMonoProp10` says Mono and is proportional."""
        for name in ("LMMonoProp10-Regular", "LMMonoProp10-Oblique",
                     "LMMonoPropLt10-Regular"):
            assert not texmap.is_monospace(name), name

    def test_the_ones_that_already_worked_still_do(self):
        for name in ("LiberationMono", "DejaVuSansMono", "CMTT10",
                     "SFTT0800", "Courier-Bold", "NimbusMonL-Regu",
                     "LMMono10-Regular", "LuxiMono"):
            assert texmap.is_monospace(name), name

    def test_prose_faces_are_still_refused(self):
        for name in ("NimbusRomNo9L-Regu", "Times-Roman", "SFRM1000",
                     "CMR10", "Helvetica", "DejaVuSans"):
            assert not texmap.is_monospace(name), name
