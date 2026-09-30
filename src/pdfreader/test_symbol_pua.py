"""787 — the Symbol font's Private Use slots.

Word and Acrobat write the Symbol font's glyphs into Unicode's Private Use
Area: the PDF's ToUnicode maps the glyph at byte 0x65 to U+F065, not to ε.

The reader's standing rule is that a PUA codepoint is a font's internal slot,
means nothing outside its document, and is therefore dropped and reported. That
is right in general and wrong for exactly one case: when the font NAMES itself
`Symbol`, its byte layout is the published Adobe Symbol encoding and the slot
has a documented meaning. The rule is not relaxed — it is given the one piece
of evidence that settles it.

Found by random sampling of the library with the pdf2mmd chain alone.
WRAP_tolerance_design_and_kinematic_calibration deferred 97 of its 205 maths
spans; 61 were these slots — U+F065 (ε) 22 times, U+F071 (θ) 15, U+F064 (δ) 15,
then μ, σ, ρ, φ, −, {, ∈. `pdffonts` lists a CID TrueType named `Symbol`.
"""
import texmap


def tex(ch, font="Symbol"):
    return texmap.project("math-italic", ch, -1, font).latex


def test_the_greek_letters_the_sample_actually_lost():
    assert tex("") == "\\epsilon"      # byte 0x65, 22 occurrences
    assert tex("") == "\\theta"        # byte 0x71, 15
    assert tex("") == "\\delta"        # byte 0x64, 15
    assert tex("") == "\\mu"
    assert tex("") == "\\sigma"
    assert tex("") == "\\rho"
    assert tex("") == "\\phi"


def test_the_operators_and_punctuation():
    assert tex("") == "-"
    assert tex("") == "\\{"
    assert tex("") == "\\in"
    assert tex("") == "\\partial"
    assert tex("") == "\\int"
    assert tex("") == "\\infty"


def test_it_is_gated_on_the_font_name():
    """A private slot in ANY OTHER font is still a private slot: the number is
    that font's own, and reading it through Symbol's table would invent a
    character. This is the whole reason the general rule exists."""
    assert tex("", "TimesNewRomanPSMT") is None
    assert tex("", "ABCDEE+Calibri") is None
    assert tex("", None) is None
    assert tex("", "") is None


def test_a_subset_prefix_is_still_the_symbol_font():
    """PDF font subsetting prepends a six-letter tag; `ABCDEE+SymbolMT` is
    Symbol and dropping it would miss most real documents."""
    assert tex("", "ABCDEE+Symbol") == "\\epsilon"
    assert tex("", "ABCDEE+SymbolMT") == "\\epsilon"
    assert tex("", "SymbolMT") == "\\epsilon"


def test_a_font_merely_CONTAINING_the_word_is_not_Symbol():
    """`MnSymbol` and `LMMathSymbols` are whole maths families with their own
    layouts; matching them here would rewrite their glyphs as Greek."""
    assert tex("", "MnSymbol") is None
    assert tex("", "LMMathSymbols10") is None


def test_the_delimiter_ASSEMBLY_PIECES_stay_refused():
    """0xE6..0xEF and 0xF3..0xFE are the top/middle/bottom/extension fragments
    of tall parentheses, brackets, braces and integrals. None is a character,
    and emitting one drops a bracket shard into the middle of an equation —
    the same judgement that keeps U+239C unmapped in 786."""
    for byte in (0xE6, 0xE7, 0xE8, 0xEC, 0xEF, 0xF3, 0xF5, 0xF9, 0xFE):
        assert tex(chr(0xF000 + byte)) is None, hex(byte)


def test_only_the_symbol_byte_range_is_claimed():
    """The encoding is one byte wide, so 0xF100 and up are some other font's
    business even when the font is Symbol."""
    assert tex("") is None
    assert tex("") is None


def test_the_answer_says_where_it_came_from():
    t = texmap.project("math-italic", "", -1, "Symbol")
    assert t.latex == "\\epsilon"
    assert t.confidence == "symbol-font"


def test_an_ordinary_glyph_name_is_untouched():
    """The gate must not shadow the normal path for the same font."""
    assert texmap.project("math-italic", "alpha", -1, "Symbol").latex == "\\alpha"
    assert texmap.project("math-symbol", "equal", -1, "Symbol").latex == "="
