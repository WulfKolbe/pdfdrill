r"""A TeX-math glyph is what the font draws, not what StandardEncoding calls it.

lib:c9daf79960c3 p68 would not compile: "Missing }". Its TeX-matha12 glyphs
arrive under StandardEncoding names -- `p` `q` `r` `s` `braceleft` -- while the
font draws `(` `)` `[` `]` and a brace that must be escaped. `build()` already
corrects the identity through `tex_slot`, so the glyph carries both: `text='p'`
and `tex.latex='('`. 67 glyphs on that page disagree.

`_glyph_text` returned `g.text` for every glyph that is not pdfminer's `(cid:N)`
placeholder, so it wrote the StandardEncoding letter and threw the correction
away -- which is how a line acquires an unbalanced brace.

THE RULE IS NARROW, and deliberately so: only a MATHS-family glyph prefers its
`tex.latex`. For a text glyph `g.text` stays the answer, because the name-keyed
tables abstain on perfectly readable text (a CID-keyed Libertinus page has no
glyph names at all) and preferring the field there would replace `\alpha` with a
raw character and lose nothing but accuracy.

The three slots added with it were verified the way `_TEX_SLOTS` demands --
rendered out of the document at 600 dpi and looked at. The strip reads
`) [ 1 / p ] ~=`, which places cid 114 at `[`, cid 123 at `/`, cid 115 at `]`.
The same render shows slot 187 drawing `~=`, NOT `gtrless` as mathabx.dcl lists
it, so 187 stays out.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader import texmap


class _G:
    def __init__(self, text, latex, family):
        self.text = text
        self.family = family
        self.tex = texmap.TexToken(latex, "atom", None, "corpus")


def test_a_maths_glyph_prefers_its_corrected_identity():
    assert dm._glyph_text(_G("p", "(", "math-symbol")) == "("
    assert dm._glyph_text(_G("P", r"\in", "math-symbol")) == r"\in"
    assert dm._glyph_text(_G("{", r"\{", "math-symbol")) == r"\{"


def test_a_text_glyph_keeps_the_character_the_pdf_decoded():
    """The narrow half. A text glyph's own character is the answer, and a page
    whose font states no glyph names reads correctly because of it."""
    assert dm._glyph_text(_G("T", None, "text")) == "T"
    assert dm._glyph_text(_G("ffi", None, "text-cm")) == "ffi"
    # even where a table could answer, a text glyph is not overridden
    assert dm._glyph_text(_G("-", r"\text{-}", "text-cm")) == "-"


def test_the_three_slots_that_were_rendered_and_looked_at():
    assert texmap.tex_slot("OERUOW+TeX-matha12", 114) == "bracketleft"
    assert texmap.tex_slot("OERUOW+TeX-matha12", 115) == "bracketright"
    assert texmap.tex_slot("OERUOW+TeX-matha12", 123) == "slash"
    for name, want in (("bracketleft", "["), ("bracketright", "]"), ("slash", "/")):
        assert texmap.project("math-symbol", name, -1, "TeX-matha12").latex == want


def test_slot_187_stays_out_because_the_font_draws_something_else():
    """mathabx.dcl lists 187 as gtrless; this font draws a similar-equals
    there, and the render shows it. A table is not evidence."""
    assert texmap.tex_slot("OERUOW+TeX-matha12", 187) != "gtrless"


def test_the_three_mathabx_names_no_longer_abstain():
    for dcl, want in (("in", r"\in"), ("rightarrow", r"\rightarrow"),
                      ("mapstochar", r"\mapsto")):
        got = texmap._MATHABX_TEX.get(dcl)
        assert got is not None, "%s still abstains" % dcl
        assert texmap.project("math-symbol", got, -1, "TeX-matha12").latex == want
