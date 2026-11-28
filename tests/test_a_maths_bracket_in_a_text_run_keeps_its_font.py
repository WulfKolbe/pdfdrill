r"""A maths font's angle bracket in a text run keeps its font and its kern.

Board 113, lib:d68e0271bd4d p334, line L18: a code-typed table row carries
CMSY7's ⟨⟨...⟩⟩. The reading wrote U+27E8 as text, which pdflatex's utf8 sets
as TS1 `\textlangle` -- another shape, whose ToUnicode reads U+2329 -- so all
four brackets were glyph findings. Written as `$\langle$` the character and
font match, but the page sets the pair 1.44 pt apart against CMSY7's 3.22 pt
advance, and at full width the second bracket fell inside the first one's
judging window. With the measured kern, three of the four are clean.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

docmodel = pytest.importorskip("pdfreader.docmodel_six")
texmap = pytest.importorskip("pdfreader.texmap")


def _g(text, x0, x1, *, family="text-cm", latex=None, size=6.97):
    tex = texmap.TexToken(latex, "delimiter", None, "corpus") if latex else texmap.UNKNOWN
    return docmodel.GlyphNode(
        id="g%d" % int(x0 * 100), page=1, rect=(x0, 100.0, x1, 100.0 + size),
        text=text, cid=0, glyphname=None, fontname="CMSY7", family=family,
        size=size, tex=tex)


def _lang(x0):
    return _g("⟨", x0, x0 + 3.22, family="math-symbol", latex=r"\langle")


def test_a_maths_font_bracket_in_text_is_written_in_maths():
    out = docmodel._run_text([_g("a", 0, 3.7), _lang(3.7)])
    assert out == r"a$\langle$"
    assert "⟨" not in out


def test_two_brackets_closer_than_their_advance_carry_the_measured_kern():
    out = docmodel._run_text([_lang(337.10), _lang(338.54)])
    assert out == r"$\langle\kern-1.78pt\langle$"


def test_two_brackets_at_their_advance_carry_no_kern():
    out = docmodel._run_text([_lang(10.0), _lang(13.22)])
    assert out == r"$\langle$$\langle$"


def test_a_text_font_bracket_and_a_maths_minus_are_left_alone():
    assert docmodel._run_text([_g("⟨", 0, 3)]) == "⟨"
    minus = _g("−", 0, 5, family="math-symbol", latex="-")
    assert docmodel._run_text([minus]) == "−"
