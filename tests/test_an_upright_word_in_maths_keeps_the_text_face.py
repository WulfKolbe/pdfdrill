r"""
B12, 0864 p4: `\bar{f}_{spc}` with "spc" set in the page's TEXT face
(NimbusRomNo9L-Regu, Times). `\mathrm{spc}` sets Computer Modern whatever
the document's font is, and every one of them was flagged on ink while every
`\text{spc}` beside it passed. A run of upright letters from a non-CM text
face is `\text{...}`; from a CM text face it stays `\mathrm{...}`, which is
the same face. Judge (pin f78391d) 0864 p4: 0.0098 -> 0.0039.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

S = pytest.importorskip("pdfreader.structure")
D = pytest.importorskip("pdfreader.docmodel_six")
from pdfreader.texmap import UNKNOWN


def _run(word, fontname, family, size=5.98, x=100.0, base=637.4):
    out = []
    for ch in word:
        w = 0.45 * size
        out.append(D.GlyphNode(
            id="g%.1f" % x, page=2, rect=(x, base - 0.2 * size, x + w, base + 0.7 * size),
            text=ch, cid=0, glyphname=ch, fontname=fontname, family=family,
            size=size, tex=UNKNOWN, matrix=(size, 0, 0, size, x, base)))
        x += w
    return out


def test_a_times_subscript_word_is_text():
    (g,) = S._merge_operator_runs(_run("spc", "ABCDEF+NimbusRomNo9L-Regu", "text"))
    assert g.tex.latex == r"\text{spc}"


def test_a_computer_modern_word_stays_mathrm():
    (g,) = S._merge_operator_runs(_run("spc", "ABCDEF+CMR6", "text-cm"))
    assert g.tex.latex == r"\mathrm{spc}"
