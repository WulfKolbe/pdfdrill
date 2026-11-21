r"""`ﬁ` is two letters, and a reading that keeps it misspells every word.

T-0154. A typeface sets `fi`, `ff`, `fl`, `ffi`, `ffl` as ONE glyph, and
pdfminer hands that glyph back as the Unicode ligature character — U+FB01 for
`fi`. The reader stored it verbatim, so 0864 p4 came back with

    Artiﬁcial   deﬁnition   reﬁned   Schefﬂer   eﬃcient

Every one of those is a wrong word against any reference that spells the
letters out: the PDF's own text layer, MathPix, the author's LaTeX. Measured
against the text layer of that page, the f-ligature words account for most of
the reading's 155-token shortfall, and none of that shortfall is missing ink —
the words are all there, spelled with a character no reference uses.

MEASURED over the 24 board-14 extracts, as `pdfdrill glyphlines` wrote them at
d98fa365: 223 ligature characters on 13 of the 24 pages.

    fi  172     ff  19
    fl   20     ffi 12

    2103.01507 p118   32      lib:b21e554b9232 p201  15
    0864 p4           31      lib:008d43e5db48 p272  13
    lib:c9daf79960c3  29      lib:1a36bfe66b9c p154  11
    lib:3fe71b4ef018  27      lib:6d90e8d27b8b p174   8
    lib:4859edad9294  24      lib:c57ac038ae5f p293   7
    lib:5a5c76391c9c  24      two more with 1 each

The decomposition was already written down for the MATHS path —
`texmap._TEXT_MATHS` maps the glyph NAMES `ff`/`fi`/`fl`/`ffi`/`ffl` to their
letters, because "its ligatures stand for two letters". The prose path reads
`glyph.text` instead and never passed through it.

ONE GLYPH KEEPS ONE BOX. The letters share the box the type was set in, which
is what the page actually contains; `rect` is not split and no glyph is
invented. A reader that wants per-letter boxes cannot have them here, and
would be measuring something the PDF does not state.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

pytest.importorskip("pdfreader.docmodel_six")
from pdfreader.docmodel_six import _spell_ligature


def test_each_f_ligature_becomes_its_letters():
    assert _spell_ligature("ﬀ") == "ff"
    assert _spell_ligature("ﬁ") == "fi"
    assert _spell_ligature("ﬂ") == "fl"
    assert _spell_ligature("ﬃ") == "ffi"
    assert _spell_ligature("ﬄ") == "ffl"


def test_the_long_s_ligatures_too():
    """U+FB05 and U+FB06 are `ft` and `st`, set by older faces."""
    assert _spell_ligature("ﬅ") == "ft"
    assert _spell_ligature("ﬆ") == "st"


def test_a_ligature_inside_a_word_is_spelled_out():
    """pdfminer hands back one glyph per ligature, but a reader may receive
    a run; the function works on whatever it is given."""
    assert _spell_ligature("Artiﬁcial") == "Artificial"
    assert _spell_ligature("eﬃcient") == "efficient"
    assert _spell_ligature("Scheﬄer") == "Scheffler"


def test_an_ordinary_character_is_returned_unchanged():
    """The common case must cost nothing and change nothing."""
    for s in ("a", "Z", "7", " ", "", "α", "—", "fi"):
        assert _spell_ligature(s) == s


def test_no_other_character_is_touched():
    """Only the seven Latin f/s ligatures. U+FB1F and above are Hebrew
    ligatures, and U+FB00..FB06 is the whole Latin block — nothing else in
    this range is decomposed by guesswork."""
    for cp in (0x00DF, 0xFB07, 0xFB1F, 0xFB4F, 0x0153, 0x00E6):
        ch = chr(cp)
        assert _spell_ligature(ch) == ch, hex(cp)
