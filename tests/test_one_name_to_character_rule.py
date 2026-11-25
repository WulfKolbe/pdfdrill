r"""One name-to-character rule, imported by both readers, not copied.

B6 item 1b. pdfdrill has two text paths and each had its own name table:

    the glyph reader   docmodel_six._spell_glyph  -> texmap.agl_char (f458f7df)
    the chars reader   cid_glyphs.glyph_name_to_char -> _GLYPH_BASE, hand-written

`_resolve_glyph` did its job: it named `CMR10 cid 22` correctly as `macron`
from the STANDARD CM encoding, and then `glyph_name_to_char` answered "" for
it, because the curated table did not list it. 145 `(cid:N)` tokens reached
users' markdown on five board pages with the name in hand; 19 of 0864 p4's 54
were that one glyph.

MEASURED, `pdfdrill md`, installed entry point: 0864 p4 54 -> 1, and its
verdict "text: 54 unread" -> "text: 1 unread".
"""
import pytest
from pdfdrill import cid_glyphs as C
from pdfreader.texmap import agl_char


# (font, cid, name the CM encoding gives, character it must become)
CM_CASES = [
    ("CMR10", 22, "macron", "¯"),
    ("CMMI10", 11, "alpha", "α"),
    ("CMMI10", 28, "tau", "τ"),
    ("CMSY10", 18, "reflexsubset", "⊆"),
    ("CMR10", 1, "Delta", "∆"),
]


@pytest.mark.parametrize("font,cid,name,want", CM_CASES)
def test_the_cm_chain_reaches_a_character(font, cid, name, want):
    """Name from the encoding, character from the one shared rule."""
    assert C.cm_names(font).get(cid) == name
    assert C.glyph_name_to_char(name) == want


def test_both_readers_use_the_same_rule():
    from pdfreader import docmodel_six as D
    assert D._agl_char is agl_char, "the glyph reader must not hold a copy"


def test_a_piece_of_a_big_symbol_is_not_a_character():
    """`texmap.agl_char` abstains for TeX's extensible pieces and MathType's
    slot names — inventing a character is worse than a visible gap."""
    for name in ("barex", "summationdisplay", "radicalbig",
                 "bracketleftbig", "SI", "planckover2pi"):
        assert agl_char(name) == ""


def test_the_size_strip_is_not_fed_to_the_list():
    """A FIRST VERSION OF 1b RESOLVED `barex` TO `|`.

    `_TEX_SIZE_SUFFIX` turns `barex` into `bar`, which the AGL knows — but
    `barex` is the EXTENSION PIECE of a tall bar, not a pipe. The strip is for
    `parenrightBig` -> `parenright`, a real character at a display size, and
    `_GLYPH_BASE` owns that route with a curated table. So the list sees the
    font's OWN name only.
    """
    assert agl_char("barex") == ""
    assert agl_char("bar") == "|"            # the base IS a character
