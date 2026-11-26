"""
B11, lib:6d90e8d27b8b p174 L10: `\\int e^{-x}\\,dx = \\int \\sin t\\,dt,
\\quad\\text{also}\\quad -e^{-x} = -\\cos t + c` is a display: its integrals are
esint's DISPLAY cut (0.556 em wide; the inline cut is 0.472). With the word
between, it read as two inline formulas with text-size integrals.
Judge (pin ed6eb5d) 6d90 p174: 0.0110 -> 0.0096, formulas 7/8 -> 8/8.
The line is the page's own (the fixture of the thin-space test).
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


def _line():
    d = json.loads(FIX.read_text())
    glyphs = []
    for g in d["glyphs"]:
        g = {k: _tup(v) for k, v in g.items()}
        g["tex"] = TexToken(*g["tex"])
        glyphs.append(dm.GlyphNode(**g))
    return dm.LineNode(id=d["id"], page=d["page"], rect=tuple(d["rect"]),
                       type=d["type"], glyphs=glyphs,
                       rules=[dm.RuleNode(**{k: _tup(v) for k, v in r.items()})
                              for r in d["rules"]])


def test_the_integral_line_is_one_display_with_its_word():
    ln = _line()
    text = " ".join(dm.span_reading_text(sp) for sp in ln.spans)
    out = dm._display_by_operator(ln, text)
    assert out.startswith("\\[\n\\int") and "\\quad\\text{also}\\quad" in out, out


def test_a_line_without_a_display_operator_is_left_alone():
    assert dm._display_by_operator(_line().__class__(
        id="x", page=1, rect=(0, 0, 1, 1), type="text", glyphs=[]), "$a$ also $b$") == "$a$ also $b$"
