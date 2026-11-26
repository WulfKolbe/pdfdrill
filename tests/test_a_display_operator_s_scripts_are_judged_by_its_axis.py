"""
A display operator's scripts are judged against its axis (B2c).

A display `\\sum` from CMEX hangs below its reference point: on
lib:1a36bfe66b9c p154 its ink runs 549.0-563.0 with the reference at 563.0.
That page's restricted sum `\\sideset{}{'}\\sum_{n \\equiv d(v)}` has its prime
at 561.5, which against the reference is "below"; it joined the subscript
and the display was refused. Against the ink's middle (556.0) it is above;
and since it stands BESIDE the operator while the condition is UNDER it,
it is `\\sideset{}{^{\\prime}}`, not a limit on top.

Judge (pin ed6eb5d) on the page: 0.0181 -> 0.0000. A TEXT-size sum keeps
its baseline (1805.01788 p3's `\\sum_m`, whose m sits above the ink middle).
The span is the page's own, frozen.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import structure as S
from pdfreader.docmodel_six import GlyphNode, RuleNode
from pdfreader.texmap import TexToken

FIX = Path(__file__).parent / "fixtures" / "restricted_sum_with_a_beside_prime.span.json"


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def _span():
    d = json.loads(FIX.read_text())
    glyphs = []
    for g in d["glyphs"]:
        g = {k: _tup(v) for k, v in g.items()}
        g["tex"] = TexToken(*g["tex"])
        glyphs.append(GlyphNode(**g))
    return glyphs, [RuleNode(**{k: _tup(v) for k, v in r.items()}) for r in d["rules"]]


def test_the_span_holds_display_sums_and_the_prime():
    glyphs, _ = _span()
    assert sum(g.glyphname == "summationdisplay" for g in glyphs) == 3
    assert any(g.glyphname == "prime" for g in glyphs)


def test_the_restricted_sum_is_read_with_its_prime_beside():
    tex = S.to_tex(*_span())
    assert tex is not None, "the display is refused again"
    assert r"\sideset{}{^{\prime}}\sum\limits_{n\equiv d (v)}" in tex
    assert r"\sum\limits_{d=0}^{v-1}" in tex
