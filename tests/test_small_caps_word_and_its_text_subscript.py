"""
A small-capital word with a subscript in the page's text font (B2).

0864 p4 prints `OPUS_spc`: a capital O at 8.97 pt, small capitals P U S at
7.17 pt on the SAME baseline in the same bold face, and `spc` lower in the
regular TEXT face. The reader took P U S for scripts of the O, could place them
neither above nor below, and refused all 18 such spans on the page.

What the ink judge measured (pin ed6eb5d, 0864 p4): refusing scored 0.0386;
`\\textsc` with `\\mathrm{spc}` 0.0447, because `\\mathrm{}` sets the subscript
in Computer Modern where the print uses its text face (inkdrill-80 counted the
+27 glyph findings: exactly those subscripts); `\\textsc` with `\\text{spc}`
0.0381. So the test pins both halves: the word is one small-capital word, and
its text-font script is text.

The glyphs are the page's own, frozen from 0864 p4.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import structure as S
from pdfreader.docmodel_six import GlyphNode
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "small_caps_word_with_text_subscript.glyphs.json"


def _glyphs():
    out = []
    for d in json.loads(FIX.read_text()):
        d["tex"] = TexToken(*d["tex"])
        d["rect"] = tuple(d["rect"])
        d["matrix"] = tuple(d["matrix"])
        if d.get("ink") is not None:
            d["ink"] = tuple(d["ink"])
        if d.get("color") is not None:
            d["color"] = tuple(d["color"])
        out.append(GlyphNode(**d))
    return out


def test_the_page_glyphs_are_what_the_test_claims():
    g = _glyphs()
    assert "".join(x.text for x in g) == "OPUSspc"
    assert g[1].size < 0.9 * g[0].size and g[4].size < g[1].size


def test_the_small_capital_word_is_built_and_its_subscript_is_text():
    tex = S.to_tex(_glyphs(), [])
    assert tex is not None, "the span is refused again"
    assert r"\textsc{Opus}" in tex
    assert r"_{\text{spc}}" in tex
    assert r"\mathrm{spc}" not in tex
