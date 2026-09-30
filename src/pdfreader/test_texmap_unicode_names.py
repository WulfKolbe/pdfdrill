"""786 — a codepoint the font STATES, that nothing asked for.

A glyph named `uni1D6FC` or `u1D719` carries its identity in its own name: the
font is stating the Unicode codepoint. `unicode_latex` decodes exactly that and
already knew 22 of the 32 characters in the Mathematical Italic Greek run — but
`project()` never called it for such names, so none of them ever reached a
caller. Every one came back as `unmapped-glyph`, and a single unmapped glyph
defers the whole maths span it sits in.

Found by random sampling of the library with the pdf2mmd chain alone:
2405.08011v1 deferred 9 of its 42 spans, and 3 of those were `u1D719` and
`uni210E` — one phi and one italic h.

This is not the "abstain rather than guess" case the module is built around.
Abstaining is right where the identity is NOT stated: a nameless glyph, an
untrusted font name, a CID with no table. Here the font said which character it
is. Refusing that is not caution, it is discarding evidence.
"""
import texmap


#: The Mathematical Italic Greek run: alpha (U+1D6FC) through varpi (U+1D71B).
GREEK_RUN = range(0x1D6FC, 0x1D71C)


def test_every_character_of_the_greek_italic_run_projects():
    """22 of the 32 were decodable all along and unreachable; 7 more were
    missing outright because `_alphanumeric` stopped at omega."""
    missing = [cp for cp in GREEK_RUN
               if not texmap.project("math-italic", "uni%04X" % cp).latex]
    assert missing == [], ["U+%04X" % cp for cp in missing]


def test_the_variant_letters_that_close_the_run():
    """`_alphanumeric` indexed a 25-name list and returned None past omega, so
    partial-differential and the five variant letters after it were lost."""
    want = {0x1D715: "\\partial", 0x1D716: "\\epsilon", 0x1D717: "\\vartheta",
            0x1D718: "\\varkappa", 0x1D719: "\\phi", 0x1D71A: "\\varrho",
            0x1D71B: "\\varpi"}
    got = {cp: texmap.project("math-italic", "uni%04X" % cp).latex
           for cp in want}
    assert got == want


def test_both_name_forms_are_accepted():
    """A font writes either `uniXXXX` or `uXXXXX`; they are the same claim."""
    assert (texmap.project("math-italic", "u1D719").latex
            == texmap.project("math-italic", "uni1D719").latex
            == "\\phi")


def test_the_letterlike_symbols_outside_the_alphanumeric_blocks():
    """U+210E/210F/2118 are not in a Mathematical Alphanumeric block, so
    `_alphanumeric` cannot reach them, and `chr(cp).isalnum()` is false."""
    assert texmap.project("math-italic", "uni210E").latex == "h"
    assert texmap.project("math-italic", "uni210F").latex == "\\hbar"
    assert texmap.project("math-italic", "uni2118").latex == "\\wp"


def test_a_postscript_name_still_goes_through_the_family_tables():
    """The codepoint path must not shadow the tables it sits in front of."""
    assert texmap.project("math-italic", "alpha").latex == "\\alpha"
    assert texmap.project("math-italic", "partialdiff").latex == "\\partial"
    assert texmap.project("math-symbol", "equal").latex == "="
    assert texmap.project("math-symbol", "asteriskmath").latex == "\\ast"


def test_a_name_that_states_no_codepoint_is_still_refused():
    """The change widens what counts as STATED; it does not start guessing."""
    assert texmap.project("math-italic", "uniZZZZ").latex is None
    assert texmap.project("math-italic", "notaglyphname").latex is None
    assert texmap.project("math-italic", None).latex is None


def test_the_answer_is_marked_as_coming_from_the_codepoint():
    """Provenance: a reader must be able to tell a codepoint decode from a
    corpus-verified table entry."""
    t = texmap.project("math-italic", "uni1D6FC")
    assert t.latex == "\\alpha"
    assert t.confidence == "unicode"


# ── the measured majority ───────────────────────────────────────────────────

def test_ascii_punctuation_named_by_codepoint():
    """ASCII PUNCTUATION IS NOT ALPHANUMERIC, and that one word cost more than
    every exotic symbol combined. `unicode_latex` ended with
    `ch.isalnum() and cp < 0x2000`, so a font naming its comma `uni002C`
    produced nothing and deferred the whole span around it. In the 10-document
    sample that was 3,028 commas and 847 full stops — 57% of all
    unmapped-glyph occurrences, against 338 for the entire Greek run."""
    for name, want in [("uni002C", ","), ("uni002E", "."), ("uni002F", "/"),
                       ("uni003D", "="), ("uni0028", "("), ("uni005D", "]")]:
        assert texmap.project("math-italic", name).latex == want, name


def test_the_characters_latex_reserves_are_escaped_not_passed_through():
    """A bare `{` from a codepoint name opens a group that never closes."""
    assert texmap.project("math-italic", "uni007B").latex == "\\{"
    assert texmap.project("math-italic", "uni007D").latex == "\\}"
    assert texmap.project("math-italic", "uni0025").latex == "\\%"
    assert texmap.project("math-italic", "uni005F").latex == "\\_"


def test_a_character_needing_a_text_mode_command_is_still_refused():
    """`^`, `~` and `\\` each need a command as a literal glyph, and guessing
    which is how a superscript becomes a stray accent."""
    for name in ("uni005E", "uni007E", "uni005C"):
        assert texmap.project("math-italic", name).latex is None, name


def test_double_struck_letters():
    """482 occurrences of ℂ and 214 of ℝ deferred their spans in the sample."""
    assert texmap.project("math-italic", "uni2102").latex == "\\mathbb{C}"
    assert texmap.project("math-italic", "uni211D").latex == "\\mathbb{R}"
    assert texmap.project("math-italic", "uni2124").latex == "\\mathbb{Z}"


def test_a_delimiter_PIECE_is_not_a_character():
    """U+239C is the EXTENSION of a tall parenthesis, not a glyph anyone
    writes. It belongs to the assembly pass; mapping it would emit a stray
    bracket fragment into the maths."""
    assert texmap.project("math-italic", "uni239C").latex is None
