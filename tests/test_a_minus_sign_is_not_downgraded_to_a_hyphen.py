r"""The maths preference recovers an identity; it must not spend one.

`_glyph_text` prefers `g.tex.latex` for a maths-family glyph, because fonts
like TeX-matha, CMSY and CMMI MISNAME their slots under StandardEncoding --
`f` for `{`, `;` for `,`, `0` for a prime -- and the field carries the
correction.

Where `g.text` is ALREADY the right character, there is no identity to
recover, and the field can only be equal or worse. U+2212 MINUS SIGN is the
case that bites: `_UNI_LATEX[0x2212]` is `"-"`, so a minus glyph whose text
is `−` reads as an ASCII hyphen.

Measured on board page 0864 p4 (the judged page is page 2 of the extract):
exactly two leaf lines differ between the reader before b7996491 and after,
both of them `−` -> `-`, and the page's paired glyphs fall 3929 -> 3922,
residual 0.1659 -> 0.1676. That was the one row of the ninth state's seven
that pdfdrill caused.

Two earlier guesses at that row are refuted and kept in
`test_a_cm_prime_renders_a_full_size_symbol.py`: it is not the prime, and a
diagnostic revert of the `\text{-}` hyphen entry leaves the page at 0.1676.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader.docmodel_six import GlyphNode, _glyph_text  # noqa: E402
from pdfreader.texmap import TexToken  # noqa: E402


def _g(text, latex, fontname="QRZVWS+CMSY10", family="math-symbol"):
    return GlyphNode(id="g", page=1, rect=(0.0, 0.0, 5.0, 5.0), text=text,
                     cid=0, glyphname=None, fontname=fontname, family=family,
                     size=10.0, tex=TexToken(latex, "atom", None, "corpus"))


def test_a_minus_sign_stays_a_minus_sign():
    assert _glyph_text(_g("−", "-")) == "−"


def test_a_misnamed_slot_whose_fallback_is_not_ascii_still_takes_it():
    """TeX-matha's StandardEncoding fallback is not always ASCII: it reports
    `\u201c` for `=`. So that font is asked by NAME, not by character --
    26 such glyphs on lib:c9daf79960c3 p68, which the character test alone
    would have thrown away (0.0147 -> 0.0153)."""
    assert _glyph_text(_g("\u201c", "=", "TeX-matha12")) == "="
    assert _glyph_text(_g("\u00d1", r"\rightarrow", "TeX-matha12")) == r"\rightarrow"


def test_a_misnamed_slot_still_takes_its_correction():
    """The reason the preference exists, unchanged."""
    assert _glyph_text(_g("f", r"\{")) == r"\{"
    assert _glyph_text(_g(";", ",", "ABCDEF+CMMI10", "math-italic")) == ","
    assert _glyph_text(_g("X", r"\mathcal{X}")) == r"\mathcal{X}"
    assert _glyph_text(_g("p", "(", "TeX-matha12")) == "("


def test_a_cid_placeholder_is_still_replaced():
    assert _glyph_text(_g("(cid:205)", r"\sum")) == r"\sum"
