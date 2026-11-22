r"""A big operator's raise comes from what the glyph IS, not what it is called.

T-0156, under the owner's rule of 2026-11-22 — fix at the lowest level.

`_group_lines` groups by BASELINE, never by box overlap, and corrects a big
operator's maths-axis raise first (750: `summationdisplay` 0.95 em,
`integraldisplay` 1.36 em, measured over 60 documents). Without that
correction the operator keeps its raised baseline and the grouper files it
with the row ABOVE.

THE CORRECTION WAS KEYED ON THE GLYPH NAME, and a subset font's names lie.
`TUJKXG+Gdvdkgesint10` on lib:6d90e8d27b8b p174 carries no ToUnicode, so
pdfminer names its glyphs after whatever a fallback encoding puts at each
code: the integrals are called `acute` and `circumflex`. `texmap` already
overrides that from the cid — the reader KNOWS the glyph is `\int` — while
this raise table still saw an accent and answered 0.00 em. Measured, before:

    L5   h=76  "…liefert:"  holding  $\int \int$     <- the display's integrals
    L6   h=53  \[ x dx = -t dt , also … \]           <- no integral at all
    L10  h=76  "(b) …liefert:"  holding $\int \int$
    L11        $e^{-x}$ dx = \sin t dt , …           <- no integral at all

and the same page's L14/L15 is the control: there the integrals stayed with
their display, so the defect is not "integrals are dropped".

BOTH CUTS ARE `\int`, AND ONLY THE WIDTH SEPARATES THEM. A `largesymbols`
font keeps a display and a text cut of one symbol. The font is embedded
(Type 1C, FontFile3) and its own widths are 472 and 556 per 1000 em; the
drawn glyphs reproduce that exactly (4.53 and 5.33 at 9.6 pt), and the wider
one sits 1.36 em above its display's baseline on ALL SEVEN occurrences —
517.87 over 504.79, 419.71 over 406.75, 332.95 over 319.87.

A FIRST VERSION KEYED THE RAISE ON THE MAPPED LaTeX and lowered the TEXT cut
too, turning `x(t) = c(t^2+1) = ct^2 + c` into
`x(t) =\int\!c(t^{2}+1) = ct\!\int^{2}+c`. That is why the rule compares
widths instead, and why one width alone answers 0.0.
"""
import pytest

from pdfreader import docmodel_six as dm
from pdfreader import texmap

ESINT = "TUJKXG+Gdvdkgesint10"
DISPLAY_CUT, TEXT_CUT = 0.555, 0.472


def test_the_wider_cut_is_the_display_one():
    assert texmap.esint_raise(ESINT, DISPLAY_CUT, (TEXT_CUT, DISPLAY_CUT)) == 1.36


def test_the_narrower_cut_is_not_raised():
    """The regression the first version caused: a text integral pushed down
    into the display below it."""
    assert texmap.esint_raise(ESINT, TEXT_CUT, (TEXT_CUT, DISPLAY_CUT)) == 0.0


def test_one_cut_alone_is_not_evidence_of_which_it_is():
    assert texmap.esint_raise(ESINT, TEXT_CUT, (TEXT_CUT,)) == 0.0
    assert texmap.esint_raise(ESINT, DISPLAY_CUT, (DISPLAY_CUT,)) == 0.0


def test_another_font_gets_no_answer_from_here():
    assert texmap.esint_raise("ABCDEF+CMEX10", DISPLAY_CUT,
                              (TEXT_CUT, DISPLAY_CUT)) is None
    assert texmap.esint_raise(None, DISPLAY_CUT, ()) is None


def test_a_named_display_operator_keeps_its_measured_raise():
    assert dm._bigop_raise("summationdisplay") == 0.95
    assert dm._bigop_raise("integraldisplay") == 1.36
    assert dm._bigop_raise("productdisplay") == 0.95       # ...display default


def test_a_named_text_operator_is_not_raised():
    assert dm._bigop_raise("summationtext") == 0.0
    assert dm._bigop_raise("integraltext") == 0.0


def test_a_letter_operator_is_not_raised():
    r"""`\cos`, `\max` sit on the ordinary baseline (750)."""
    assert dm._bigop_raise("c") == 0.0
    assert dm._bigop_raise(None) == 0.0


def test_a_wrongly_named_glyph_is_raised_by_its_font_not_its_name():
    """The whole point: `circumflex` in an esint font is an integral."""
    got = dm._bigop_raise("circumflex", r"\int", "math-extension",
                          ESINT, DISPLAY_CUT, (TEXT_CUT, DISPLAY_CUT))
    assert got == 1.36


def test_a_real_accent_is_still_an_accent():
    """The same name in a TEXT font must not pick up an operator's raise."""
    got = dm._bigop_raise("circumflex", r"\hat", "text",
                          "ABCDEF+CMR10", 0.5, ())
    assert got == 0.0


@pytest.mark.parametrize("name", ["summationdisplay", "integraldisplay"])
def test_the_measured_constants_are_unchanged(name):
    """750 measured these over 60 documents; this task did not re-measure
    them and must not have moved them."""
    assert dm._BIGOP_RAISE[name] == {"summationdisplay": 0.95,
                                     "integraldisplay": 1.36}[name]
