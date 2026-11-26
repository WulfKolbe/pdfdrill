"""
P6, 2103.01507 p117: "sup-ported", hyphenated at the line end, read as
`$\\sup\\text{-}$ported`. The operator-name merge collapses upright letters
spelling `\\sup`, `\\min`, ... only when nothing word-like follows; a text-font
hyphen directly after them is a word break, not maths.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader.texmap import TexToken


def _g(ch, x, name=None):
    return dm.GlyphNode(id=f"g{x}", page=1, rect=(x, 100.0, x + 5.0, 110.0),
                        text=ch, cid=-1, glyphname=name or ch,
                        fontname="ABCDEF+CMR10", family="text-cm", size=10.0,
                        tex=TexToken(None, "unknown", None, "none"),
                        matrix=(1, 0, 0, 1, x, 100.0))


def test_sup_before_a_hyphen_stays_letters():
    out = dm._merge_operator_names([_g("s", 0), _g("u", 5), _g("p", 10),
                                    _g("-", 15, "hyphen")])
    assert [g.text for g in out] == ["s", "u", "p", "-"]


def test_sup_alone_is_still_the_operator():
    out = dm._merge_operator_names([_g("s", 0), _g("u", 5), _g("p", 10),
                                    _g("x", 30)])
    assert out[0].text == r"\sup"
