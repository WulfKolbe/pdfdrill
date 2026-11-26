"""
A root keeps its index, and a fraction under its bar keeps its rule (B2c).

lib:6d90e8d27b8b p174 prints `x(t) = \\sqrt[3]{c - \\frac{3}{4}t^4} - 1`. The
vinculum is an overline, so `_merge_overlines` built the root, and it built
the body with NO rules: the digits 3 and 4 went into the root, the fraction
bar stayed outside with nothing above or below it, and the whole display was
refused. Once built, the index 3 hung on the glyph before it: `=^{3}`.

Judge (pin ed6eb5d) on the page: 0.0221 -> 0.0206. MathPix reads
`\\sqrt[3]{c-\\frac{3}{4} t^{4}}-1`. The span is the page's own, frozen.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import structure as S
from pdfreader.docmodel_six import GlyphNode, RuleNode
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "cube_root_over_a_fraction.span.json"


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def _span():
    d = json.loads(FIX.read_text())
    glyphs = []
    for g in d["glyphs"]:
        g = {k: _tup(v) for k, v in g.items()}
        g["tex"] = TexToken(*g["tex"])
        glyphs.append(GlyphNode(**g))
    rules = [RuleNode(**{k: _tup(v) for k, v in r.items()}) for r in d["rules"]]
    return glyphs, rules


def test_the_span_is_the_one_the_test_claims():
    glyphs, rules = _span()
    assert any(g.glyphname == "radicalBig" for g in glyphs)
    assert sorted(r.role for r in rules) == ["fraction", "overline"]


def test_the_cube_root_over_a_fraction_is_read():
    tex = S.to_tex(*_span())
    assert tex is not None, "the display is refused again"
    assert r"\sqrt[3]{c - \frac{3}{4} t^{4}}" in tex
    assert "=^{3}" not in tex
