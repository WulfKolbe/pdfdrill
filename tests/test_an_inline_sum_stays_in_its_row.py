r"""
B14, lib:5a5c76391c9c p4: an inline `\sum_{i=1}^n` (CMEX10 `summationtext`)
sits 0.75 em above its row's baseline, because TeX centres a CMEX operator on
the maths axis. Read unraised, the sum and its `n` went into the prose line
above, leaving `{}_{i=1}` behind. Judge (pin 8a67b8a) 5a5c p4: 0.0034 ->
0.0000. Positions are the page's own.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")
from pdfreader.texmap import TexToken, UNKNOWN


def _g(text, x0, x1, base, size=9.96, name=None, tex=UNKNOWN, family="text",
       font="ABC+SFRM1000"):
    return D.GlyphNode(id="g%.1f_%.1f" % (x0, base), page=2,
                       rect=(x0, base - 0.2 * size, x1, base + 0.7 * size),
                       text=text, cid=0, glyphname=name, fontname=font,
                       family=family, size=size, tex=tex,
                       matrix=(size, 0, 0, size, x0, base))


def test_the_text_cut_sum_is_raised():
    assert D._bigop_raise("summationtext") == 0.75


def test_the_sum_joins_the_row_it_was_set_in():
    above = [_g(c, 230 + 5 * i, 234 + 5 * i, 260.8) for i, c in enumerate("weight")]
    row = [_g(c, 230 + 5 * i, 234 + 5 * i, 248.8) for i, c in enumerate("minimize")]
    s = D.GlyphNode(id="sum", page=2, rect=(252.3, 250.3, 262.9, 260.3), text="∑", cid=80,
                    glyphname="summationtext", fontname="ABC+CMEX10", family="math-extension",
                    size=9.96, tex=TexToken(r"\sum", "bigop", None, "corpus"),
                    matrix=(9.96, 0, 0, 9.96, 252.3, 256.3))
    rows = D._group_lines(above + row + [s])
    home = [r for r in rows if s in r][0]
    assert any(g.text == "m" for g in home) and not any(g.text == "w" for g in home)
