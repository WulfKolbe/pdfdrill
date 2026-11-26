"""
B4: a sideways figure label is read in its own frame.

0864 p4's rotated axis and legend labels were grouped by x (the baseline
LEVEL in the rotated frame) and read with pdfminer's box extent as their size
(the ADVANCE for a sideways glyph: 3.49 pt for 6.97 pt type). The legend came
out `spc`, `\\textbf{PUS}`, `mon`, ... and the axis label `\\textit{F}ˆ0`.

- a sideways glyph's size is its type size (`fontsize` x scale);
- sideways glyphs are turned upright (`_to_upright`) and grouped and split
  by the same rules as horizontal text, maths included when the line carries
  a maths font (a stamp, which has none, stays one text span).

Judge (pin ed6eb5d) 0864 p4: 0.0124 -> 0.0107, unpaired 3/3 -> 0/0.
The lines are the page's own, frozen.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "rotated_labels.lines.json"


def _line(name):
    d = json.loads(FIX.read_text())[name]
    glyphs = []
    for g in d["glyphs"]:
        g = {k: tuple(v) if isinstance(v, list) else v for k, v in g.items()}
        g["tex"] = TexToken(*g["tex"])
        glyphs.append(dm.GlyphNode(**g))
    return dm.LineNode(id=d["id"], page=d["page"], rect=tuple(d["rect"]),
                       type=d["type"], glyphs=glyphs, rotated=True)


def _text(ln):
    return " ".join(dm.span_reading_text(sp) for sp in ln.spans)


def test_the_axis_label_reads_as_the_page_sets_it():
    t = _text(_line("axis"))
    assert r"$\hat{F}_{0}$" in t and r"\textsc{Greedy}" in t and r"\textsc{Opus}" in t, t


def test_the_legend_label_keeps_its_small_caps_and_subscripts():
    t = _text(_line("legend"))
    assert r"\textsc{Opus}}}_{\text{mon}}" in t and r"_{\text{spc}}" in t, t


def test_a_sideways_glyph_is_turned_upright():
    g = _line("axis").glyphs[0]
    assert abs(g.matrix[1]) == 1.0 and g.size > 5.0        # type size, not advance
    u = dm._to_upright(g)
    assert u.upright and u.matrix[:4] == (1, 0, 0, 1)
    assert abs((u.rect[2] - u.rect[0]) - (g.rect[3] - g.rect[1])) < 1e-6
