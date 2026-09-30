"""828 — `\\w` does not match a hyphen, and a TeX family is as likely to write
`Fourier-Math-Extension` as `XCharterMathEX`.

Cahiers GUTenberg 51 (2008) is set in Fourier-GUTenberg — Utopia text with the
Fourier maths fonts — and ships three of them:

    Fourier-Math-Symbols      Fourier-Math-Letters      Fourier-Math-Extension

Every one fell through to "text", so the document's entire maths font layer was
read with the text tables. `integraldisplay` is a display integral; it projects
to `\\int` under math-extension and to nothing under text, and came out of the
reader as `(cid:110)`.

The second half is an alias. Computer Modern calls the angle bracket
`angbracketleft`; Fourier, Utopia and every Type 1 following the Adobe glyph
list call it `angleleft`, and only the CM name was in the table. This is a
paper about XML and MathML, so ⟨tag⟩ notation is on nearly every page: once the
fonts were classified correctly, 77 of the 93 remaining deferrals were those
two names, and one unmapped glyph defers the whole span it sits in.

Measured on that document, pdf2mmd only:

    maths spans recognised   107 -> 180     (73 were being read as prose)
    projected                 92 -> 164
    deferred                  15 ->  16

Checked against MathPix on the same file, which is the reason this is worth
having: the paid route reads the same document with the same two failures.
"""
import texmap


def fam(name):
    return texmap.family_of("ABCDEF+" + name)


def test_the_fourier_maths_fonts():
    assert fam("Fourier-Math-Symbols") == "math-symbol"
    assert fam("Fourier-Math-Letters") == "math-italic"
    assert fam("Fourier-Math-Extension") == "math-extension"


def test_every_separator_a_font_name_uses():
    """`-`, `_`, a space, or nothing at all."""
    for sep in ("-", "_", " ", ""):
        assert fam(f"Something Math{sep}Extension".replace(" Math", "Math")) \
            == "math-extension", sep
        assert fam(f"XMath{sep}Symbols") == "math-symbol", sep


def test_the_unseparated_names_still_work():
    """The rule this widens was added for `XCharterMathMI`; widening it must
    not cost the case it was written for."""
    assert fam("XCharterMathMI") == "math-italic"
    assert fam("XCharterMathSY") == "math-symbol"
    assert fam("XCharterMathEX") == "math-extension"


def test_a_text_font_is_still_text():
    """The rule must not claim a font merely because its name has letters in
    common — these are the families that share this document with Fourier."""
    for n in ("Utopia-Regular", "Utopia-Titling", "Utopia-RegularSC",
              "fourier-orns", "LMTypewriter10-Regular", "cah-gut"):
        assert fam(n) == "text", n


def test_the_display_integral_projects_once_the_font_is_maths():
    """The whole point: the glyph was always named correctly, and only the
    family stood between it and its LaTeX."""
    f = fam("Fourier-Math-Extension")
    assert texmap.project(f, "integraldisplay").latex == "\\int"
    assert texmap.project(f, "summationdisplay").latex == "\\sum"
    assert texmap.project("text", "integraldisplay").latex is None


def test_the_angle_bracket_under_both_names():
    """Same glyph, two naming traditions. 77 of 93 deferrals were this."""
    assert texmap.project("math-symbol", "angleleft").latex == "\\langle"
    assert texmap.project("math-symbol", "angleright").latex == "\\rangle"
    assert texmap.project("math-symbol", "angbracketleft").latex == "\\langle"
    assert texmap.project("math-symbol", "angbracketright").latex == "\\rangle"
