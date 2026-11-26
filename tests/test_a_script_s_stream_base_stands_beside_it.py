"""
A script's stream base stands beside it, across the page as well as up and down.

The stream pass gives a band's glyph to the row of its predecessor outside the
band. On 0864 p4 a caption line set smaller than the body passed as a band of
scripts, and its small capitals (`G{REEDY}_spc`) went to their predecessor
outside the row, the last `e` of the caption line above, 120 pt to their right.
Judge (pin ed6eb5d) 0864 p4: 0.0381 -> 0.0156, unpaired glyphs 56/55 -> 5/5.

A fraction's part is exempt: lib:3fe71b4ef018 p328 emits a numerator whole
after its `=`, far off by construction, and the bar is the evidence (that page
went 0.0178 -> 0.0237 when the check applied to it). Both cases are the pages'
own glyphs, frozen.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "stream_base_beside.cases.json"


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def _glyph(d):
    d = {k: _tup(v) for k, v in d.items()}
    d["tex"] = TexToken(*d["tex"])
    return dm.GlyphNode(**d)


def _case(name):
    c = json.loads(FIX.read_text())[name]
    rules = [dm.RuleNode(**{k: _tup(v) for k, v in r.items()}) for r in c["rules"]]
    return _glyph(c["g"]), _glyph(c["base"]), rules, c["span_pt"], c["expect"]


def test_a_small_capital_is_not_given_to_the_end_of_the_line_above():
    g, base, rules, span_pt, expect = _case("small_cap")
    assert g.text == "R" and base.text == "e"
    assert abs(g.rect[0] - base.rect[2]) > 2 * span_pt   # the case is far
    assert dm._stream_base_beside(g, base, rules, span_pt) is expect is False


def test_a_numerator_far_from_its_equals_sign_is_still_placed():
    g, base, rules, span_pt, expect = _case("numerator")
    assert base.text == "=" and rules
    assert dm._stream_base_beside(g, base, rules, span_pt) is expect is True
