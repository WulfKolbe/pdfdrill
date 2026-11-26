"""
B12, lib:3fe71b4ef018 p328: the page's five missing rules were bars.

- `1/\\bar{\\rho}^2`: the bar over the rho lies 4 pt under the fraction bar,
  so it too had the numerator above and the rho below and was called a
  fraction. A narrower bar under a wider one, as wide as the single glyph
  below it, with NOTHING between the two bars, is that glyph's overline;
  (14.4.17)'s nested `\\frac14` has its `1` between and stays a fraction.
- `\\bar{\\Delta}`, `\\bar{\\rho}`: MathTime's font box reaches far above the ink,
  so a bar about as wide as its glyph may sit inside the box top.
- `\\bar{Q}` with a Times-Italic Q in prose: a short run under an overline is
  maths (a text span drops its rules).

Judge (pin f78391d) 3fe71 p328: 0.0054 -> 0.0027, rules missing 5 -> 0,
formulas 1/5 -> 2/5. The inputs are the page's own, frozen.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "bars_under_bars_and_a_barred_letter.json"


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def _glyphs(items):
    out = []
    for g in items:
        g = {k: _tup(v) for k, v in g.items()}
        g["tex"] = TexToken(*g["tex"])
        out.append(dm.GlyphNode(**g))
    return out


def _role(name):
    d = json.loads(FIX.read_text())[name]
    rule = dm.RuleNode(**{k: _tup(v) for k, v in d["rule"].items()})
    others = [dm.RuleNode(**{k: _tup(v) for k, v in r.items()}) for r in d["others"]]
    others.append(rule)
    return dm._rule_role(rule, _glyphs(d["glyphs"]), d["size"], others, d["page_width"])


def test_the_bar_over_rho_is_an_overline():
    assert _role("rho_bar") == "overline"


def test_the_nested_quarter_stays_a_fraction():
    assert _role("quarter_bar") == "fraction"


def test_a_barred_q_in_prose_is_maths():
    d = json.loads(FIX.read_text())["qbar_line"]
    ln = dm.LineNode(id=d["id"], page=d["page"], rect=tuple(d["rect"]), type=d["type"],
                     glyphs=_glyphs(d["glyphs"]),
                     rules=[dm.RuleNode(**{k: _tup(v) for k, v in r.items()}) for r in d["rules"]])
    text = " ".join(dm.span_reading_text(sp) for sp in ln.spans)
    assert r"\overline{Q} \cos \delta" in text, text
