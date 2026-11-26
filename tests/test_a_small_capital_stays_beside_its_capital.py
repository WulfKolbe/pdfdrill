"""
P6, 0864 p4 "PosiPtiUvSe": a small capital stays in the row of its capital.

A caption line set smaller than the body passes `_off_row_band` whole, and
the stream pass gave each of its smaller glyphs to the row of the stream
predecessor OUTSIDE the line. For `O{PUS}`, the last word of a line, that was
the last `e` of the line above, at the same right margin, and the two were
read interleaved: "PosiPtiUvSe". Walking back through the stream over glyphs
of the small capital's own size reaches the `O`: larger, flush before it, on
its baseline. That is the base (`_base_in_own_row`).

Judge (pin ed6eb5d) 0864 p4: 0.0142 -> 0.0124. The glyphs are the page's own.
"""
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "small_caps_after_their_capital.glyphs.json"


def _glyphs():
    out = []
    for g in json.loads(FIX.read_text()):
        g = {k: tuple(v) if isinstance(v, list) else v for k, v in g.items()}
        g["tex"] = TexToken(*g["tex"])
        out.append(dm.GlyphNode(**g))
    return out


def test_the_small_capitals_have_their_base_in_their_own_row():
    gs = _glyphs()
    assert "".join(g.text for g in gs) == "nOPUS"
    own = {g.stream: g for g in gs}
    assert all(dm._base_in_own_row(g, own) for g in gs[2:])     # P, U, S


def test_a_raised_glyph_is_a_script_not_a_small_capital():
    gs = _glyphs()
    p = gs[2]
    m = list(p.matrix)
    m[5] += 0.4 * p.size                                         # off the line
    raised = replace(p, matrix=tuple(m))
    own = {g.stream: g for g in gs}
    own[raised.stream] = raised
    assert not dm._base_in_own_row(raised, own)
