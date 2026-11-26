"""
B9, lib:6d90e8d27b8b p174: `e^{(\\frac12 t^2 - t)}` on the line under a text
line. The `1` sits 0.9 pt above the bar and two letters of the line above at
7.6 pt, inside the same window. The role test took the most frequent baseline
above (the text line), saw it run past the bar, and called the bar an
overline: `_{\\overline{2}}^{1}`. It takes the nearest baseline now.

(The same commit stops the fraction-row merge from joining the line above as
the fraction's "host" when the merged row already runs past the bar on both
sides at its line's level; that part is checked on the board pages.)
The bar and the glyphs the reader passes with it (within 25 pt) are the
page's own.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "half_in_an_exponent_under_a_text_line.json"


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def test_the_bar_of_the_half_is_a_fraction():
    d = json.loads(FIX.read_text())
    glyphs = []
    for g in d["glyphs"]:
        g = {k: _tup(v) for k, v in g.items()}
        g["tex"] = TexToken(*g["tex"])
        glyphs.append(dm.GlyphNode(**g))
    rule = dm.RuleNode(**{k: _tup(v) for k, v in d["rule"].items()})
    others = [dm.RuleNode(**{k: _tup(v) for k, v in r.items()}) for r in d["others"]]
    assert dm._rule_role(rule, glyphs, d["size"], others,
                         d["page_width"]) == "fraction"
