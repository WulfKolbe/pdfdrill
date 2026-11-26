"""
P10 + 3fe71's (14.4.17): displays whose rows sit on several baselines.

- 1805.01788 p3: text-size `\\sum_{l=1}^{m}` inside display fractions. A
  hanging `\\sum` put both its scripts "below" it (two levels beside one
  operator: the higher is `^`), its kerned beside-scripts were set as
  `\\limits`, and the tail `u_{i2}` stayed prose.
- 3fe71b4ef018 p328 (14.4.17): a `\\frac14` inside each part of the main
  fraction; in x order the main bar took their digits and the display was
  refused. A nested bar is handed down to the part it sits in.

(The two row rules in `build` -- a short preceding prose line is not the
display's host, and a row of limits beside an operator joins its row -- are
measured on the board pages.) Judge (pin f78391d): 1805 p3 0.0080 ->
0.0033, 3fe71 p328 0.0145 -> 0.0054. The rows are the pages' own.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader import structure as S
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "multi_row_displays.json"


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def _glyphs(d):
    out = []
    for g in d["glyphs"]:
        g = {k: _tup(v) for k, v in g.items()}
        g["tex"] = TexToken(*g["tex"])
        out.append(dm.GlyphNode(**g))
    return out


def _rules(d):
    return [dm.RuleNode(**{k: _tup(v) for k, v in r.items()}) for r in d["rules"]]


def test_nested_fractions_are_built_inside_their_outer_fraction():
    d = json.loads(FIX.read_text())["nested"]
    tex = S.to_tex(sorted(_glyphs(d), key=lambda g: g.rect[0]), _rules(d))
    assert tex is not None, "refused again"
    assert r"\frac{\bigl[1 + \frac{1}{4}" in tex and r"}{1 - \frac{1}{4} N^{2}" in tex, tex


def test_sums_with_two_script_levels_and_the_tail_variable():
    d = json.loads(FIX.read_text())["display"]
    ln = dm.LineNode(id=d["id"], page=d["page"], rect=tuple(d["rect"]),
                     type=d["type"], glyphs=_glyphs(d), rules=_rules(d))
    text = " ".join(dm.span_reading_text(sp) for sp in ln.spans)
    assert r"\frac{\sum_{l =1}^{m} a_{i 1}^{l}}{\sum_{l =1}^{m} r_{i 1}^{l}}" in text, text
    assert r"\forall u_{i 1} , u_{i 2} ." in text, text
