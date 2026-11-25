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


def test_a_name_in_neither_table_abstains():
    """A name no table knows must stay unread.

    MathType's slot "names" are ASCII control mnemonics standing for slot
    numbers — 55 instances on the board (SI 23, NUL 11, STX 6, DC2 4, DC3 4,
    SOH 3, ESC 1, c141 3) — and T-0163 owns them by SHAPE, not by name. A WIDE
    accent spans an expression, so `^` is not what the page shows and the span
    is the information.
    """
    for name in ("SI", "NUL", "STX", "DC2", "c141", "hatwide", "tildewide"):
        assert _spell_glyph("(cid:12)", name, 12) == "(cid:12)"


def test_a_whole_symbol_at_a_display_size_is_read():
    """CHANGED DELIBERATELY by B6 items 2+3.

    This test used to assert that `radicalbig`, `bracketleftbig` and
    `summationdisplay.1` abstained, on the reading that they were "extensible
    pieces". Measured, they are not: 55 of the board's 75 characterless glyphs
    stand ALONE, and `bracketleftbig` is a whole `[` drawn large. The curated
    TeX table knows them and the glyph reader now shares it.
    """
    assert _spell_glyph("(cid:12)", "radicalbig", 12) == "√"
    assert _spell_glyph("(cid:12)", "bracketleftbig", 12) == "["
    assert _spell_glyph("(cid:12)", "summationdisplay.1", 12) == "∑"
    assert _spell_glyph("(cid:12)", "angbracketleft", 12) == "⟨"


def test_a_fragment_of_a_symbol_is_not_a_character():
    """`barex` abstains, and THE BOARD DECIDED IT, not the principle.

    `barex` is the repeated MIDDLE of a tall bar. The TeX table strips a
    trailing `ex`, so it resolved `barex` -> `bar` -> `|`: long the chars
    reader's answer, and sharing one table put it in front of the board, where
    a bar of three stacked pieces reads `|||`.

    MEASURED on 1805.01788 p3, which carries 12 of them, judge inkdrill
    a176dda, --route glyph:

        main                      0.0166
        with the `ex` strip       0.0190     +0.0023
        without the `ex` strip    0.0166     the whole regression

    So the strip's `ex` branch is removed. `big`/`Big`/`bigg`/`Bigg`/`small`
    stay — `parenrightBig` IS a `)` at a display size — and the table's own
    rule had said as much all along: `pennytop`/`pennyedge` are deliberately
    unmapped because "no character stands in for a fragment of a picture"
    (902). A bar's middle is such a fragment.

    THE COST, stated because it looks like a regression and is not: those 12
    glyphs are `(cid:N)` again in 1805's markdown, so its unread count RISES.
    The gap was always there, masked by a wrong character; e8bdca56 is what
    makes it visible instead of hidden behind REACHED.
    """
    assert _spell_glyph("(cid:12)", "barex", 12) == "(cid:12)"
    assert _spell_glyph("(cid:12)", "bar", 12) == "|"          # the base IS one
    assert _spell_glyph("(cid:12)", "parenrightBig", 12) == ")"  # size, not piece
