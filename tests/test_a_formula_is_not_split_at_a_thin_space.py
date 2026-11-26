"""
B10, lib:6d90e8d27b8b p174: `\\int e^{-x}\\,dx = \\int \\sin t\\,dt` read as
`$\\int \\mathrm{e}^{-x}$ $\\mathrm{d}x = \\int \\sin t$ $\\mathrm{d}t ,$`.
Neighbouring maths spans less than half an em apart, with no text between,
are one formula (`_join_close_maths`); a quad between two formulas keeps
them apart. The line is the page's own.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "integral_with_thin_spaces.line.json"


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def test_the_integral_is_one_formula():
    d = json.loads(FIX.read_text())
    glyphs = []
    for g in d["glyphs"]:
        g = {k: _tup(v) for k, v in g.items()}
        g["tex"] = TexToken(*g["tex"])
        glyphs.append(dm.GlyphNode(**g))
    ln = dm.LineNode(id=d["id"], page=d["page"], rect=tuple(d["rect"]),
                     type=d["type"], glyphs=glyphs,
                     rules=[dm.RuleNode(**{k: _tup(v) for k, v in r.items()})
                            for r in d["rules"]])
    text = " ".join(dm.span_reading_text(sp) for sp in ln.spans)
    assert text.startswith(r"$\int \mathrm{e}^{-x} \mathrm{d}x = \int \sin t \mathrm{d}t ,$"), text
