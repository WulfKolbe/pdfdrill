r"""A glyph with no character but a STANDARD NAME is read from its name.

B6, item 1. On the 21 born pages of board75, 95 glyphs (excluding `space`) came
through with no character. 20 of them carry a name the Adobe Glyph List defines:

    10x alpha (CMMI10/CMMI9)   ->  α
     7x macron (CMR10/CMR9)    ->  ¯
     2x asteriskmath (CMSY6)   ->  ∗
     1x minus (CMSY9)          ->  −

We already pass `glyphname` into `_spell_glyph` and pdfminer already ships the
list (4281 entries). The reading emitted `(cid:11)` while holding the word
`alpha`.

THE NAME IS ONLY CONSULTED WHEN THERE IS NO CHARACTER, and that limit is the
point. `_spell_glyph`'s rule 3 measured what happens if you prefer the name or
the code in general: across ten documents 620 glyphs decode to a non-Latin
character on a printable ASCII code and NEARLY ALL ARE CORRECT -- TeX's quotes,
CMSY's `p` -> U+221A, `2` -> U+2208. Preferring the name would have broken
every one. So this fills a hole; it never overrules the font.
"""
from pdfreader.docmodel_six import _spell_glyph


def test_a_cid_token_with_an_agl_name_is_read():
    assert _spell_glyph("(cid:11)", "alpha", 11) == "α"
    assert _spell_glyph("(cid:3)", "asteriskmath", 3) == "∗"
    assert _spell_glyph("(cid:0)", "minus", 0) == "−"


def test_a_replacement_character_with_an_agl_name_is_read():
    assert _spell_glyph("�", "macron", 22) == "¯"


def test_empty_text_with_an_agl_name_is_read():
    assert _spell_glyph("", "alpha", 11) == "α"


def test_a_suffixed_name_is_read_from_its_base():
    """`alpha.1` is an alpha; a subset names variants that way."""
    assert _spell_glyph("(cid:11)", "alpha.1", 11) == "α"


def test_the_font_is_never_overruled():
    """THE GUARD. A real character wins over any name — rule 3's measurement."""
    assert _spell_glyph("x", "alpha", 11) == "x"
    assert _spell_glyph("√", "p", 112) == "√"      # CMSY's p is √
    assert _spell_glyph("∈", "two", 50) == "∈"     # CMSY's 2 is ∈


def test_a_name_outside_the_list_abstains():
    """TeX's extensible pieces are not characters and must stay unread."""
    for name in ("barex", "summationdisplay.1", "radicalbig",
                 "bracketleftbig", "SI"):
        assert _spell_glyph("(cid:12)", name, 12) == "(cid:12)"


def test_a_space_is_not_disturbed():
    assert _spell_glyph(" ", "space", 32) == " "
