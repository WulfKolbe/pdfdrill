r"""Two structure fixes for lib:3fe71b4ef018 p328's displays (MathTime).

1. `\Bigl(\frac{r_\circ}{r}\Bigr)^4`: a sized delimiter pair whose content
   is split by a fraction bar at the pair's centre holds a FRACTION, not an
   array of rows (`_merge_stacked_delimiters`, T-0154).
2. `\frac{\bar\Delta}{\bar\rho^2}`: the overline over the numerator stops at
   the fraction bar beneath it; it took the denominator too.
Both made `to_tex` defer the whole display.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

dm = pytest.importorskip("pdfreader.docmodel_six")
st = pytest.importorskip("pdfreader.structure")
texmap = pytest.importorskip("pdfreader.texmap")
_N = [0]


def _g(text, x0, x1, base, latex, kind="atom", size=10.0, ink=None,
       family="math-italic"):
    _N[0] += 1
    return dm.GlyphNode(
        id="g%d" % _N[0], page=1, rect=(x0, base, x1, base + size), text=text,
        cid=0, glyphname=None, fontname="X+MTMI", family=family, size=size,
        tex=texmap.TexToken(latex, kind, None, "corpus"),
        matrix=(size, 0, 0, size, x0, base), ink=ink)


def _rule(x0, x1, y, role):
    _N[0] += 1
    r = dm.RuleNode(id="r%d" % _N[0], page=1, rect=(x0, y, x1, y))
    r.role = role
    return r


def test_a_fraction_inside_sized_delimiters_is_a_fraction():
    gs = [_g("(", 161.7, 167.1, 317.1, r"\Bigl(", "delimiter",
             ink=(163.1, 299.6, 166.9, 317.6), family="math-extension"),
          _g("r", 168.1, 172.0, 313.1, "r"),
          _g("◦", 172.5, 175.4, 311.6, r"\circ", size=7.0),
          _g("r", 169.7, 173.6, 299.1, "r"),
          _g(")", 176.1, 181.4, 317.2, r"\Bigr)", "delimiter",
             ink=(177.5, 299.7, 181.4, 317.6), family="math-extension")]
    out = st.to_tex(gs, [_rule(168.3, 176.2, 308.6, "fraction")])
    assert out is not None
    assert r"\frac{r_{\circ}}{r}" in out and "array" not in out


def test_an_overline_stops_at_the_fraction_bar_beneath_it():
    gs = [_g("ρ", 105.6, 111.0, 94.3, r"\rho"),
          _g("Δ", 107.3, 115.2, 109.0, r"\Delta"),
          _g("2", 112.8, 116.3, 98.3, "2", size=7.0, family="text")]
    rules = [_rule(107.3, 115.2, 117.1, "overline"),
             _rule(105.6, 116.8, 104.5, "fraction"),
             _rule(105.6, 111.6, 100.3, "overline")]
    out = st.to_tex(gs, rules)
    assert out == r"\frac{\overline{\Delta}}{\overline{\rho}^{2}}"
