r"""The PDF's own glyph census — the second opinion MathPix cannot see.

679. Eight of the nineteen unrenderable published rows are MathPix glyph
DECOMPOSITIONS: a symbol it could not name, emitted as CJK radicals. The
typesetter already recorded what those glyphs are, in the font `/Encoding`,
and this reads it. Measured on mielke-geometrodynamics: `匕` is `Ł`
(`/Lslash`), `十` is a literal `+`, and FO0431's `\jmath` AND `」` are the
SAME glyph, `/floorright`, guessed two different wrong ways.
"""
import pytest

from pdfdrill import glyphcensus as gc


def _g(char, name=None, font="ABCDEF+Times", size=10.0, x=0.0, line=1):
    return gc.Glyph(char=char, name=name, font=font, size=size, x=x, line=line)


# ------------------------------------------------------------------ geometry

def test_a_mathpix_region_converts_to_points_at_250_dpi():
    """654 — MathPix renders the CropBox at 250 dpi; PDF user space is 72."""
    x0, y0, x1, y1 = gc.region_to_points(
        {"top_left_x": 250, "top_left_y": 500, "width": 250, "height": 125})
    assert (x0, y0) == (72.0, 144.0)
    assert (x1, y1) == (144.0, 180.0)


# ------------------------------------------------------- what a glyph reports

def test_an_unmapped_glyph_reports_its_NAME_not_its_cid():
    """A name is specific where a character is absent. `(cid:8)` tells a
    reader nothing; `/floorright` tells them it is the interior product."""
    g = _g("(cid:8)", name="floorright")
    assert g.unmapped is True
    assert g.token == "/floorright"


def test_a_mapped_glyph_reports_its_character():
    g = _g("Ł")
    assert g.unmapped is False
    assert g.token == "Ł"


def test_an_unmapped_glyph_the_font_does_not_name_still_reports_honestly():
    """A font with no `/Differences` entry for the code leaves the name None.
    The census says `(cid:8)` rather than inventing one."""
    g = _g("(cid:8)", name=None)
    assert g.unmapped is True and g.token == "(cid:8)"


def test_the_census_line_is_the_reading_order():
    glyphs = [_g("B", x=20.0, line=1), _g("A", x=10.0, line=1),
              _g("C", x=5.0, line=40)]
    assert gc.as_line(sorted(glyphs, key=lambda g: (g.line, g.x))) == "A B C"


def test_unmapped_names_are_distinct_and_sorted():
    glyphs = [_g("(cid:8)", name="floorright"), _g("(cid:8)", name="floorright"),
              _g("(cid:2)", name="angbracketleft"), _g("x")]
    assert gc.unmapped_names(glyphs) == ["angbracketleft", "floorright"]


# ----------------------------------------------- the untrustworthy-font class

def test_a_symbolic_font_declaring_a_text_encoding_is_named_as_suspect():
    r"""The dangerous shape: `WinAnsi` with no `/ToUnicode` over symbol
    glyphs yields PLAUSIBLE BUT WRONG characters, which is worse than
    `(cid:N)`. mielke carries 15 of these (of 230) and they are absent from
    every page measured — but a caller must be able to distrust them."""
    names = ["JNIBFE+NfpfqxAdvSPRING-R", "JNIBHK+KwydhtAdvP4C4E74",
             "LNEOIM+QfldvyMTSYN", "SQJWRA+CwxshvTimes-Roman"]
    assert gc.suspect_fonts(names) == ["JNIBFE+NfpfqxAdvSPRING-R",
                                       "JNIBHK+KwydhtAdvP4C4E74"]


# --------------------------------------------------- the contradiction check

ALNUM = "AGDLtau0R"


def _census(text):
    return [_g(c, x=i * 5.0) for i, c in enumerate(text)]


def test_prose_replacing_mathematics_is_caught():
    r"""The defect this check exists for. The ink gate accepted a proposal
    that replaced mielke EQ0378's mathematics with a sentence about the
    Pontryagin index, because the ink distance fell 106 -> 10. Ink distance
    measures how MUCH ink a rendering makes, not whether it is the same ink."""
    why = gc.contradicts("preserve the term Pontryagin index for the "
                         "classification of real associated vector bundles",
                         _census(ALNUM), own_region=True)
    assert why and "absent from the reading" in why


def test_a_faithful_reading_is_not_caught():
    """The control."""
    assert gc.contradicts(r"\Lambda A G D L t a u 0 R $",
                          _census(ALNUM), own_region=True) is None


def test_latex_markup_the_glyphs_cannot_carry_is_not_held_against_a_reading():
    r"""LaTeX and glyphs are different alphabets: a faithful reading adds
    `\frac`, `^`, `_` and braces that no glyph carries. Only the glyphs the
    PDF actually PLACES are required to appear."""
    assert gc.contradicts(r"\frac{A}{G}^{D}_{L}\,t\,a\,u\,0\,R",
                          _census(ALNUM), own_region=True) is None


def test_a_host_line_region_is_refused_rather_than_misjudged():
    r"""679, found by the module's own first run. An inline Formula has no
    region, so a caller reaches for its HOST LINE's — a whole line of prose.
    mielke FO0431's host-line census holds 92 glyphs, 84 literal, because the
    line reads "covariant Lie derivative on M with respect to an arbitrary
    vector field" around the formula. Judged against that, MathPix's correct
    8-character reading is "missing" 49 of 84 glyphs — a confident false
    refusal. `own_region=False` declines instead."""
    prose = _census("covariantLiederivativeonMwithrespect")
    assert gc.contradicts(r"\mathrm{Ł}_{\xi}", prose, own_region=False) is None
    # and with the wrong scope asserted, it WOULD have refused — which is
    # exactly why the parameter has no default
    assert gc.contradicts(r"\mathrm{Ł}_{\xi}", prose, own_region=True)


def test_too_few_glyphs_to_judge_declines():
    """A region holding one or two glyphs carries no evidence worth
    refusing on."""
    assert gc.contradicts("anything at all", _census("AB"), own_region=True) is None


def test_an_unmapped_glyph_is_never_required_to_appear():
    r"""`(cid:8)` is not a character a reading can contain, and `/floorright`
    is the evidence for `\rfloor`, not a literal to match."""
    glyphs = _census(ALNUM) + [_g("(cid:8)", name="floorright", x=99.0)]
    assert gc.contradicts(r"A G D L t a u 0 R \rfloor", glyphs,
                          own_region=True) is None


def test_own_region_has_no_default_so_declining_is_deliberate():
    with pytest.raises(TypeError):
        gc.contradicts("x", _census(ALNUM))
