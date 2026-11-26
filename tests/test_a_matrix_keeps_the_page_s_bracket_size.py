"""
B12, lib:c57ac038ae5f p293: script-size column vectors in brackets the page
sized itself (`bracketleftbig` = `\\bigl[`). Re-sized with `\\left[...\\right]`
around the small matrix they came out smaller than the page's and up to 0.3
of a size out of place. The matrix keeps the page's own sized delimiters.
The span is the page's own.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader import structure as S
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "sized_brackets_round_a_small_matrix.span.json"


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def test_the_vector_keeps_bigl_brackets():
    d = json.loads(FIX.read_text())
    glyphs = []
    for g in d["glyphs"]:
        g = {k: _tup(v) for k, v in g.items()}
        g["tex"] = TexToken(*g["tex"])
        glyphs.append(dm.GlyphNode(**g))
    rules = [dm.RuleNode(**{k: _tup(v) for k, v in r.items()}) for r in d["rules"]]
    tex = S.to_tex(sorted(glyphs, key=lambda g: g.rect[0]), rules)
    assert r"3 \bigl[\begin{smallmatrix}1 \\ -1/2\end{smallmatrix}\bigr]" in tex, tex
    assert r"\left[" not in tex
