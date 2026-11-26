"""
B11, lib:3fe71b4ef018 p328 (14.4.15): a MathTime display whose Latin
variables are Times-Italic text glyphs. The letters `c\\,dt` at its end were
counted as the three-letter run "cdt" (runs joined up to 0.3 em), the line
was not "mostly maths", and the variables A, Q, N stayed prose with the bars
of \\bar{Q} lost. A word has no gap between its letters; a thin space is one.

Judge (pin ed6eb5d) 3fe7 p328: 0.0156 -> 0.0145. The line is the page's own.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "mathtime_display_with_times_italic_letters.line.json"


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def test_the_variables_and_their_bars_are_maths():
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
    assert text.startswith(r"$A = - \frac{1}{\rho^{2}} (\overline{Q} \cos \delta"
                           r" + N \overline{Q} \sin \delta)"), text
