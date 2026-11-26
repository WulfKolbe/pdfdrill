"""
B11, 2312.11532 p7: the panel regions take in their subcaption row,
"(a) 20NG-NPMI.", set in the page's body face, and the row was removed with
the charts' own labels (DejaVuSerif): lost words. A glyph inside a figure
region stays when it is in the page's dominant text face.

Judge (pin ed6eb5d) 2312 p7: 0.0283 -> 0.0162, uncovered page glyphs 94 -> 54.
The glyphs and regions are the page's own (a sample: the caption's `(`, `a`,
`N`, chart labels `k=5`, and prose for the body face).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "subcaption_inside_a_figure_region.json"


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def test_the_subcaption_stays_and_the_chart_labels_go():
    d = json.loads(FIX.read_text())
    glyphs = []
    for g in d["glyphs"] if "glyphs" in d else d["g"]:
        g = {k: _tup(v) for k, v in g.items()}
        g["tex"] = TexToken(*g["tex"])
        glyphs.append(dm.GlyphNode(**g))
    inner = [tuple(r) for r in d["inner"]]
    kept = dm._outside_figures(glyphs, inner)
    cap = [g for g in glyphs if "Nimbus" in g.fontname and 660 < g.baseline < 670]
    # the charts' own labels INSIDE a region (an edge band is kept by design)
    chart = [g for g in glyphs if "DejaVu" in g.fontname
             and dm._region_holding(g.rect, inner) is not None]
    assert cap and all(g in kept for g in cap)
    assert chart and not any(g in kept for g in chart)
