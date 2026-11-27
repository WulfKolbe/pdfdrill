r"""
SPEED (EXACT): `GlyphNode.is_math` was read 2.1 M times on 12 board pages.
It is memoised by the values of the three fields it reads (family,
glyphname, text), never by the glyph, because the build reassigns `family`
and `text` (a glyph turned into a maths symbol, a run turned into text). A
mutated glyph must answer from its new fields.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")
from pdfreader.texmap import UNKNOWN


def _g(text, family, name=None):
    return D.GlyphNode(id="g", page=1, rect=(0, 0, 5, 10), text=text, cid=0,
                       glyphname=name, fontname="ABC+X", family=family, size=10.0,
                       tex=UNKNOWN, matrix=(10, 0, 0, 10, 0, 0))


def test_a_reassigned_family_changes_the_answer():
    g = _g("x", "text")
    assert g.is_math is False
    g.family = "math-symbol"
    assert g.is_math is True
    g.family = "text"
    assert g.is_math is False


def test_text_and_name_still_decide():
    assert _g("=", "text").is_math is True              # a relation
    assert _g("A", "text", name="Gamma").is_math is True  # Greek by name
    assert _g("a", "text").is_math is False
