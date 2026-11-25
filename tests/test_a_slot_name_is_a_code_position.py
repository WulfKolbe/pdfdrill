r"""MathTime Professional 2 names its slots by POSITION, not by symbol.

T-0163. `lib:3c16fac66fdd` p370 sets its mathematics in MT2MIT, MT2SYT,
MT2EXA and MT2BMIT, and 55 glyphs came through with no character while the
page typed 0 maths lines where MathPix types 2.

The names looked meaningless — `NUL`, `SOH`, `STX`, `SI`, `DC2`, `DC3`, `ESC`,
`c141` — and the same name appears in two fonts for two different symbols
(`SI` is MT2SYT cid 2 AND MT2MIT cid 9). They are ASCII CONTROL NAMES, so each
one IS its code position, and MTPro2 uses TeX's own maths encodings, which
`texmap` already carries for Computer Modern: mt2mi = OML (cmmi), mt2sy = OMS
(cmsy), mt2ex = OMX (cmex), mt2bmi = bold OML. The trailing t/s/f is the
optical size (coordinator, 2026-11-25; pctex.com/mtpro2.html, mtp2otf on CTAN).

MEASURED, p370, judge inkdrill a176dda --route glyph:

    main (no MT2 rule)         0.0103
    the family rule ALONE      0.2439     <- a 24-fold regression
    family rule + this table   0.0065

which is why the two land together: the family rule alone turns "text with the
wrong characters" into "MATHS with the wrong characters", the judge renders the
LaTeX, and the content was `X`.
"""
import pytest
from pdfreader import texmap as T
from pdfreader.docmodel_six import _spell_glyph


#: (font, slot name, cid, the TeX name, the character) — every one verified
#: against the glyph's own rendered outline (work/run-files/t0163/shapetest.py).
VERIFIED = [
    ("MT2SYT", "SI",  2, "bullet",         "•"),   # a filled disc
    ("MT2SYT", "NUL", 5, "minus",          "−"),   # a solid bar, aspect 0.08
    ("MT2SYT", "STX", 6, "multiply",       "×"),   # two crossing diagonals
    ("MT2SYT", "SOH", 8, "periodcentered", "·"),   # a disc, see the test below
    ("MT2MIT", "SI",  9, "epsilon1",       "ϵ"),   # a lunate epsilon
    ("MT2EXA", "DC2", 8, "parenleftbigg",  "("),   # a tall paren, bulging left
    ("MT2EXA", "DC3", 9, "parenrightbigg", ")"),   # its exact mirror
    ("MT2BMIT", "ESC", 2, "sigma",         "σ"),   # a top tail over a bowl
]


@pytest.mark.parametrize("font,slot,cid,texname,char", VERIFIED)
def test_a_control_name_resolves_through_tex_s_encoding(font, slot, cid, texname, char):
    assert T.mtpro2_glyph_name(font, slot, cid) == texname
    assert _spell_glyph(f"(cid:{cid})", slot, cid, font) == char


def test_the_same_name_in_two_fonts_is_two_symbols():
    """`SI` is position 15 in both, and position 15 differs by ENCODING.

    This is why the resolver needs the font and why a name-keyed table could
    never have worked.
    """
    assert T.mtpro2_glyph_name("MT2SYT", "SI", 2) == "bullet"      # OMS 15
    assert T.mtpro2_glyph_name("MT2MIT", "SI", 9) == "epsilon1"    # OML 15


def test_shape_alone_could_not_have_separated_these_two():
    """bullet and periodcentered are the SAME outline at different sizes.

    MT2SYT cid 2 and cid 8 render byte-identically — 1798 and 1804 ink cells of
    2304 at 48x48, normalised to each glyph's own box. That is what fired the
    pre-registered kill on shape-as-the-source: the POSITION separates them,
    and shape only verifies.
    """
    assert T.mtpro2_glyph_name("MT2SYT", "SI", 2) == "bullet"
    assert T.mtpro2_glyph_name("MT2SYT", "SOH", 8) == "periodcentered"


def test_a_position_outside_the_encoding_stays_unread():
    """`c141` is position 141, past CMMI's table. MTPro2's extension range is
    not something this table claims to know, so the glyph keeps its `(cid:N)`
    — a defect someone can see, never a guessed symbol in a formula.

    It is unread on BOTH MT2 documents, which is the cross-check holding.
    """
    assert T.mtpro2_glyph_name("MT2MIT", "c141", 7) == ""
    assert _spell_glyph("(cid:7)", "c141", 7, "MT2MIT") == "(cid:7)"


def test_the_family_is_the_tex_encoding_s_family():
    for f, fam in (("MT2MIT", "math-italic"), ("MT2BMIT", "math-italic"),
                   ("MT2MIS", "math-italic"), ("MT2SYT", "math-symbol"),
                   ("MT2SYF", "math-symbol"), ("MT2EXA", "math-extension")):
        assert T.family_of(f) == fam, f
    assert T.family_of("Times-Roman2") == "text"


def test_nothing_else_is_disturbed():
    """The rule fires ONLY where the font gave no character, so a glyph the
    PDF does describe keeps what the PDF says.

    That matters beyond CM: on the second MT2 document the OMS encoding would
    name code `p` `radical` and code `2` `element`, while those fonts'
    ToUnicode says 'p' and '2' — 865 glyphs on 12 pages. Whether the encoding
    or the ToUnicode is right there is a SEPARATE question with its own gate;
    this change does not touch them.
    """
    assert _spell_glyph("p", "p", 112, "MT2SYT") == "p"
    assert _spell_glyph("2", "two", 50, "MT2SYT") == "2"
    assert _spell_glyph("(cid:11)", "alpha", 11, "CMMI10") == "α"
    assert _spell_glyph("x", "x", 120, "Times-Roman") == "x"
