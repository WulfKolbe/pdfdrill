"""
A fraction inside a script is script-sized (lib:6d90e8d27b8b p174).

`x(t) = e^c e^{(\\frac12 t^2 - t)}(t+1)`: the 4.8 pt fraction sits in a
6.72 pt exponent. Its synthetic node took the ROW's size, became a full-size
atom off the baseline, and the script pass refused the whole row, which was
then written as characters, `ece(21t2-t)(t+1)`. The node now takes its
parts' size over 0.7 (TeX's script ratio), capped at the row's.

Judge (pin ed6eb5d) 6d90 p174: 0.0206 -> 0.0147. The span is the page's own.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import structure as S
from pdfreader.docmodel_six import GlyphNode, RuleNode
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "fraction_in_an_exponent.span.json"


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def test_the_exponent_keeps_its_fraction():
    d = json.loads(FIX.read_text())
    glyphs = []
    for g in d["glyphs"]:
        g = {k: _tup(v) for k, v in g.items()}
        g["tex"] = TexToken(*g["tex"])
        glyphs.append(GlyphNode(**g))
    rules = [RuleNode(**{k: _tup(v) for k, v in r.items()}) for r in d["rules"]]
    tex = S.to_tex(sorted(glyphs, key=lambda g: g.rect[0]), rules)
    assert tex is not None, "the row is refused again"
    assert r"\mathrm{e}^{( \frac{1}{2} t^{2} -t)}" in tex, tex
