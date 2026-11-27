r"""
J10, 1511.08771 p2709: eight bold table numbers carry an overline,
`\overline{\mathbf{138600}}`, and every reader dropped the bars. Three
causes:

- the bar 1.3 pt under a full-width table rule was taken for a table rule
  (B13). A bar exactly as wide as the run under it is that run's overline;
- a run of text-font digits under an overline stayed prose, which drops its
  rules. A run wholly under one overline is maths. And in the primed rows
  (`138600'`) the bar sits 8.8 pt above the baseline, past the row
  window; an overline exactly as wide as a row's run is that row's;
- bold CM digits arrive by glyph NAME (`one`), which `_bold_math_glyph`
  refused, so `\mathbf` was lost.

Judge (pin inkdrill 43e9783, J10) 1511 p2709: 0.0032 -> 0.0000, rules
missing 8 -> 0. The primed row's inputs are the page's own, frozen.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader import texmap as T
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "an_overline_over_a_primed_number.json"


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def _glyphs(items):
    out = []
    for g in items:
        g = {k: _tup(v) for k, v in g.items()}
        g["tex"] = TexToken(*g["tex"])
        out.append(dm.GlyphNode(**g))
    return out


def test_a_bold_cm_digit_is_mathbf():
    assert T.project("text-cm", "one", fontname="ABCDEF+CMBX10").latex == r"\mathbf{1}"
    assert T.project("text-cm", "one", fontname="ABCDEF+CMR10").latex == "1"


def test_the_bar_is_as_wide_as_the_primed_number():
    d = json.loads(FIX.read_text())
    bar = dm.RuleNode(**{k: _tup(v) for k, v in d["bar"].items()})
    assert dm._overlines_a_run(bar, _glyphs(d["line"]["glyphs"]), 10.91)


def test_the_primed_row_reads_its_overline():
    d = json.loads(FIX.read_text())["line"]
    ln = dm.LineNode(id=d["id"], page=d["page"], rect=tuple(d["rect"]), type=d["type"],
                     glyphs=_glyphs(d["glyphs"]),
                     rules=[dm.RuleNode(**{k: _tup(v) for k, v in r.items()}) for r in d["rules"]])
    text = " ".join(dm.span_reading_text(sp) for sp in ln.spans)
    assert text.startswith(r"$\overline{\mathbf{1}\mathbf{3}\mathbf{8}\mathbf{6}\mathbf{0}\mathbf{0}^{\prime}}"), text
