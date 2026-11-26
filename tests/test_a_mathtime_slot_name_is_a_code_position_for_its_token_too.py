"""
A MathTime slot name is a code position for the TeX token as well as the text (B2c).

lib:3c16fac66fdd p370 sets its list bullets from MT2SYT, whose glyph is named
`SI` (control character 15). Since T-0163 the TEXT is spelled through
`mtpro2_glyph_name` and reads `•`, but the TeX token was still asked of the
slot name, came back UNKNOWN, and every bullet line went to `to_tex` as a
one-glyph maths span and was refused: 12 of the board's 41 early refusals.
The glyph identity below is the page's own (family, name, cid, face).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader.texmap import project


def test_the_bullet_slot_of_mtpro2_is_a_bullet():
    assert project("math-symbol", "SI", 2, "ABCDEF+MT2SYT").latex == r"\bullet"


def test_a_slot_name_in_another_font_still_abstains():
    """`SI` means slot 15 only in a MathTime font; elsewhere it is unknown."""
    assert project("math-symbol", "SI", 2, "ABCDEF+CMSY10").latex is None
