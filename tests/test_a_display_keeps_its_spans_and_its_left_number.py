"""
P6, 2103.01507 p118 and 0864 p4: maths spans and numbered displays.

- A text-font `;` between two maths runs is maths: `C(Z$ ; $\\overline{M}X)`
  read as two spans. `:` likewise (4859 p1287's colon).
- A closing bracket after a maths run joins it as far as that run left a
  bracket open: `\\Gamma(..., \\overline{M}_0X$ )` -> inside; 0864's
  `; Y))` takes one `)` and leaves the prose's own.
- A number at the LEFT margin (`leqno`, (6.2.4)-(6.2.10)) is an equation
  number, and its line is a display with `\\tag`, as a right-hand one is.

The lines are the pages' own, frozen.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader import project_mmd as mmd
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "spans_at_semicolons_and_closers.lines.json"


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def _line(name):
    d = json.loads(FIX.read_text())[name]
    glyphs = []
    for g in d["glyphs"]:
        g = {k: _tup(v) for k, v in g.items()}
        g["tex"] = TexToken(*g["tex"])
        glyphs.append(dm.GlyphNode(**g))
    rules = [dm.RuleNode(**{k: _tup(v) for k, v in r.items()}) for r in d["rules"]]
    return dm.LineNode(id=d["id"], page=d["page"], rect=tuple(d["rect"]),
                       type=d["type"], glyphs=glyphs, rules=rules)


def _text(ln):
    return " ".join(dm.span_reading_text(sp) for sp in ln.spans)


def test_a_semicolon_and_a_closing_bracket_stay_in_the_maths():
    t = _text(_line("semicolon"))
    assert "(Z; \\overline{M} X )" in t, t
    assert t.endswith("\\overline{M}_{0} X )$"), t


def test_only_the_open_bracket_is_closed_inside_the_maths():
    t = _text(_line("closers"))
    assert "; Y )$ )" in t, t


def test_a_left_number_is_an_equation_number():
    ln = _line("semicolon")
    tag = mmd.equation_number(ln, 485.5, 127.0)
    assert "".join(g.text for g in tag) == "(6.2.5)"
    assert mmd.equation_number(ln, 485.5) == []      # without the left edge


def test_a_numbered_display_either_side():
    assert dm._as_display("(6.2.4) $a = b ,$", "math") == "\\[\na = b ,\\tag{6.2.4}\n\\]"
    assert dm._as_display("(6.2.7) $X \\to$ $\\mathrm{Map}(Z)$", "math") == \
        "\\[\nX \\to \\mathrm{Map}(Z)\\tag{6.2.7}\n\\]"
    assert dm._as_display("$a$ and $b$ (2)", "math") == "$a$ and $b$ (2)"
