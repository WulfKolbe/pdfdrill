r"""128 — CJK in a MATHS value is MathPix hallucinating, not content.

U+2FF0–U+2FFB are Ideographic Description Characters: not glyphs but a notation
for DESCRIBING how an unknown ideograph is composed ("⿱ 日 一" = the thing with
日 above 一). Their presence in a formula means the OCR could not identify a
character and emitted its recipe instead.

0902.0431_EQ1187 (page 200, confidence 0.183) is the worked case: it carries
⿱ ⿻ 一 日 and \zh, and its glyphs were SILENTLY DROPPED by xelatex — a report
that looks finished and is missing symbols with no visible trace.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.report_tex import cjk_defect, renderable


def test_ideographic_description_character_is_flagged():
    r = cjk_defect(r"\begin{aligned} x &= ⿱ 日 一 \end{aligned}")
    assert "ideographic description" in r and "U+2FF1" in r


def test_cjk_ideograph_is_flagged():
    assert "CJK ideograph" in cjk_defect(r"\mathrm{孔}")


def test_zh_command_is_flagged():
    assert cjk_defect(r"a + \zh{x}") == r"\zh command"
    assert cjk_defect(r"a + \zhang") == ""      # \zh must not match a prefix


def test_ordinary_mathematics_is_clean():
    """The converse, and the one that matters: 335,043 corpus values were
    scanned and only 26 flagged, so a false positive here would be expensive."""
    for v in (r"\frac{a}{b}", r"\alpha\beta\gamma", r"\int_0^\infty e^{-x}dx",
              r"\left(\begin{array}{cc}1&2\\3&4\end{array}\right)",
              "x = 52+26 = 78", r"\mathfrak{e}_{6}{ }^{C}", "λ σ Ω ℏ ∇ ⊗ ∮"):
        assert cjk_defect(v) == "", v


def test_greek_and_symbols_are_not_cjk():
    """Non-ASCII is not the test — the maths fonts are full of it."""
    assert cjk_defect("∀x∈ℝ: ‖x‖₂ ≤ ∞") == ""


def test_renderable_refuses_a_contaminated_value():
    """The point of the validator: hallucinated script never reaches xelatex,
    where it becomes a silently dropped glyph instead of a visible failure."""
    assert renderable(r"x = ⿱ 日 一") == ""
    assert renderable(r"\frac{a}{b}") == r"\frac{a}{b}"


def test_the_real_row():
    src = (r"\begin{aligned} &=(\boldsymbol{v}, \boldsymbol{w})"
           r"((\boldsymbol{b} \times ⿻ ⿱ 一 ⿱ 日 一 \zh \end{aligned}")
    assert cjk_defect(src)
    assert renderable(src) == ""


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
