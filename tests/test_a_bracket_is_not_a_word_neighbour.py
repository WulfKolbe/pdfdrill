r"""
B16, 0864 p4: "(OPUS_mon)" sets OPUS in bold small caps against an opening
bracket. The base of a script counts as "in a word" when its left neighbour
touches it, and the bracket counted: the O stayed in prose while PUS and its
subscript went to maths, `(\textbf{O} $\text{\textbf{PUS}}_{\text{mon}}$)`,
and the small-caps merge never saw the word (3 glyph findings). A word
neighbour is a letter or digit. Judge (pin inkdrill 43e9783) 0864 p4:
0.0015 -> 0.0012.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")
from pdfreader.texmap import UNKNOWN


def _g(ch, x, size, font, base=100.0):
    return D.GlyphNode(id="g%.1f" % x, page=2, rect=(x, base - 0.2 * size, x + 0.6 * size, base + 0.7 * size),
                       text=ch, cid=0, glyphname=None, fontname=font, family="text",
                       size=size, tex=UNKNOWN, matrix=(size, 0, 0, size, x, base))


def _line(glyphs):
    xs = [g.rect for g in glyphs]
    return D.LineNode(id="p2l0", page=2, rect=(min(r[0] for r in xs), min(r[1] for r in xs),
                                                max(r[2] for r in xs), max(r[3] for r in xs)),
                      type="text", glyphs=glyphs, rules=[])


def test_the_letter_after_a_bracket_joins_its_scripts():
    reg, bold = "ABC+NimbusRomNo9L-Regu", "ABC+NimbusRomNo9L-Medi"
    gs = [_g(c, 10 + 6 * i, 9.96, reg) for i, c in enumerate("that ")]
    x = 10 + 6 * 5
    gs.append(_g("(", x, 9.96, reg)); x += 3.3
    gs.append(_g("O", x, 9.96, bold)); x += 7.2
    for c in "PUS":
        gs.append(_g(c, x, 7.97, bold)); x += 4.6
    for c in "mon":
        gs.append(_g(c, x, 4.98, reg, base=98.6)); x += 2.9
    spans = D._spans(_line(gs))
    o = next(g for g in gs if g.text == "O")
    p = next(g for g in gs if g.text == "P")
    home = [sp for sp in spans if o in sp.glyphs][0]
    assert p in home.glyphs, [(sp.kind, "".join(g.text for g in sp.glyphs)) for sp in spans]
