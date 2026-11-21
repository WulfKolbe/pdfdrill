r"""`q.sc_u.sc` is two letters, and the reader was writing one.

T-0156, reported by inkdrill-10 from 1805.01788 p3. Linux Libertine sets the
small-cap `Qu` of "Equity" as ONE glyph named `q.sc_u.sc`, and the font's
ToUnicode maps it to a single `q`. So the reading says

    Eqity

four times on that page, against `Equity` six times. A dropped letter is a
GLYPH finding, not a style one, so this touches the residual and not
`style_rate`.

THE RULE FIRES ONLY WHERE THE TEXT IS SHORTER THAN THE NAME'S PARTS, and
that scoping is the whole of the care needed here. MEASURED over the 24
board-14 extracts, every glyph whose PostScript name contains an underscore:

    f_i   29 -> 'fi'   two characters, correct
    f_f   21 -> 'ff'   correct
    f_l    6 -> 'fl'   correct
    t_t    2 -> 'tt'   correct
    q.sc_u.sc  2 -> 'q'    ONE character for a two-part name

So 58 of the 60 composite glyphs on the whole board set are already right —
the font's own ToUnicode, or `_spell_ligature` (d1e73fe2), handles them — and
a rule that rewrote every `X_Y` name from its parts would be a no-op for
those and a risk for any name whose parts are not plain letters. Only the
short ones are touched.

AND EVERY PART MUST REDUCE TO ONE LETTER. `q.sc` drops its `.sc` suffix and
leaves `q`; a part that does not reduce that way — `dotlessi`, `ff`, a name
this reader has never seen — makes the whole name abstain, because inventing
characters is worse than the one that is missing. The glyph keeps its own box
either way: one glyph, one rectangle, as with the f-ligatures.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

pytest.importorskip("pdfreader.docmodel_six")
from pdfreader.docmodel_six import _spell_glyph


def test_the_measured_case():
    """`q.sc_u.sc` with the font's one-character ToUnicode."""
    assert _spell_glyph("q", "q.sc_u.sc") == "qu"


def test_a_part_may_carry_any_suffix():
    assert _spell_glyph("a", "a.sc_b.sc") == "ab"
    assert _spell_glyph("a", "a.alt_b.alt") == "ab"
    assert _spell_glyph("f", "f.sc_i") == "fi"


def test_three_parts():
    assert _spell_glyph("f", "f_f_i") == "ffi"


def test_a_name_whose_text_is_already_complete_is_untouched():
    """58 of the 60 composite glyphs on the board set. The rule must be a
    no-op for them, including when the text is LONGER than the part count."""
    assert _spell_glyph("fi", "f_i") == "fi"
    assert _spell_glyph("ff", "f_f") == "ff"
    assert _spell_glyph("tt", "t_t") == "tt"
    assert _spell_glyph("fl", "f_l") == "fl"


def test_a_part_that_is_not_one_letter_makes_the_name_abstain():
    """Inventing characters is worse than the one that is missing."""
    assert _spell_glyph("x", "dotlessi_j") == "x"
    assert _spell_glyph("x", "ff_i") == "x"
    assert _spell_glyph("x", "_i") == "x"
    assert _spell_glyph("x", "a_") == "x"


def test_a_plain_name_is_untouched():
    for text, name in (("a", "a"), ("Q", "Q"), ("", ""), ("x", None),
                       ("ß", "germandbls")):
        assert _spell_glyph(text, name) == text, (text, name)


def test_the_f_ligature_character_is_still_decomposed():
    """d1e73fe2's rule still applies, and the two compose: a ligature
    CHARACTER under a composite NAME resolves by the character."""
    assert _spell_glyph("ﬁ", "f_i") == "fi"
    assert _spell_glyph("ﬃ", "f_f_i") == "ffi"
