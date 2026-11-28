r"""phi / varphi (and the other variant pairs): one rule for text and display.

In a TeX maths-italic font the glyph name says which of a pair it is (CM:
`phi` straight \phi, `phi1` loopy \varphi); `to_tex` reads the glyph token,
and the text path read the Unicode value, which need not agree.
- lib:3fe71b4ef018 p328, MTMI `phi` (ink 0.661 em, straight), U+03C6;
- lib:1a36bfe66b9c p154, CMMI `phi1` (ink 0.442 em, loopy), U+03D5.
A glyph whose name is not CM's (MT2MIT `SI`) keeps its Unicode value.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

dm = pytest.importorskip("pdfreader.docmodel_six")
texmap = pytest.importorskip("pdfreader.texmap")


def _g(text, name, latex, family="math-italic", font="X+CMMI10"):
    return dm.GlyphNode(
        id="g", page=1, rect=(0, 0, 5, 10), text=text, cid=0, glyphname=name,
        fontname=font, family=family, size=10.0,
        tex=texmap.TexToken(latex, "atom", None, "corpus"),
        matrix=(10, 0, 0, 10, 0, 0))


def test_cm_phi1_is_varphi_whatever_its_unicode():
    assert dm._run_text([_g("ϕ", "phi1", r"\varphi")], maths_mode=True) == r"\varphi"


def test_cm_phi_is_phi_whatever_its_unicode():
    assert dm._run_text([_g("φ", "phi", r"\phi", font="X+MTMI")],
                        maths_mode=True) == r"\phi"


def test_a_name_that_says_nothing_keeps_the_unicode_value():
    assert dm._run_text([_g("ϵ", "SI", r"\varepsilon", font="X+MT2MIT")],
                        maths_mode=True) == r"\epsilon"


def test_display_and_text_agree():
    from pdfreader import structure as st
    for g in (_g("ϕ", "phi1", r"\varphi"), _g("φ", "phi", r"\phi")):
        assert st.to_tex([g], []) == dm._run_text([g], maths_mode=True)
