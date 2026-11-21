r"""Composing an accent must compose its LaTeX too, or maths loses the accent.

T-0154. `_compose_text_accents` joins an accent to the letter under it —
"an accent over a letter is ONE character, in prose" — and builds the
composed glyph with

    replace(base, text=composed, rect=...)

which updates the TEXT and leaves `tex` as the base's. In a prose span that
is right, because the span is written from `text`. In a MATHS span the span
is written from `tex.latex`, so the accent is silently dropped.

MEASURED on lib:6d90e8d27b8b p174, a differential-equations exercise sheet
whose derivatives are dotted:

    pdfminer gives                      '˙' x22 in `DlgbwdCMR9`
    our reader composes                 'ẋ' x18 and 'ċ' x4   = 22
    the composed glyph's tex.latex      'x'        <- the dot is gone
    our reading holds                   0 `ẋ`, 0 `ċ`, 0 `\dot`
    MathPix writes                      `\dot{x}` x22

So the composition is working and its result never reaches the reading. The
glyph carries `family=math-italic`, so its span is maths and is written from
the LaTeX.

THE ITEM AS QUEUED WAS "5 dot accents missing from the reading". There are
no missing dot accents: all 22 are found and composed. What is missing is
their LaTeX, 22 times, and the count is 22 rather than 5.

The accent glyph already holds the command — `_TEXT_ACCENT` gives `dotaccent`
the token `\dot` — so the composed token is that command applied to the
base's own LaTeX, and nothing has to be invented.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")
texmap = pytest.importorskip("pdfreader.texmap")


def _g(text, glyphname, x0, family=None, latex=None):
    #: An ACCENT must be in a text family for `_compose_text_accents` to
    #: consider it — that gate is what keeps a maths accent out of this pass
    #: (`structure._merge_accents` composes those). The BASE may be maths:
    #: on p174 it is `math-italic`, which is why the composed glyph's span is
    #: written from its LaTeX and the dot was lost.
    if family is None:
        family = "text" if glyphname in ("dotaccent", "dieresis", "acute") \
            else "math-italic"
    tok = texmap.TexToken(latex, "atom", None, "corpus") if latex else texmap.UNKNOWN
    if glyphname in ("dotaccent", "dieresis", "acute"):
        tok = texmap.project("text", glyphname, 0, "ABC+CMR9")
    return D.GlyphNode(
        id="g" + str(x0), page=1, rect=(x0, 100.0, x0 + 5.0, 110.0), text=text,
        cid=0, glyphname=glyphname, fontname="ABC+CMR9", family=family,
        size=10.0, tex=tok, matrix=(10, 0, 0, 10, x0, 100.0))


def test_the_composed_glyph_carries_the_accented_latex():
    """`\dot` over `x` is `\dot{x}`, not `x`."""
    acc = _g("˙", "dotaccent", 100.0)
    base = _g("x", None, 100.0, latex="x")
    out = D._compose_text_accents([[acc, base]])[0]
    assert len(out) == 1, out
    assert out[0].text == "ẋ", out[0].text          # ẋ
    assert out[0].tex.latex == r"\dot{x}", out[0].tex


def test_the_text_is_unchanged_by_this():
    """A prose span is written from `text` and must not move."""
    acc = _g("¨", "dieresis", 100.0, family="text")
    base = _g("u", None, 100.0, family="text", latex="u")
    out = D._compose_text_accents([[acc, base]])[0]
    assert out[0].text == "ü", out[0].text          # ü


def test_a_base_with_no_latex_of_its_own_uses_its_text():
    acc = _g("˙", "dotaccent", 100.0)
    base = _g("c", None, 100.0)                          # tex is UNKNOWN
    out = D._compose_text_accents([[acc, base]])[0]
    assert out[0].tex.latex == r"\dot{c}", out[0].tex


def test_an_uncomposable_pair_is_left_alone():
    """No precomposed character exists, so both glyphs stay as they were and
    nothing is invented."""
    acc = _g("˙", "dotaccent", 100.0)
    base = _g("q", None, 100.0, latex="q")               # no precomposed q-dot
    out = D._compose_text_accents([[acc, base]])[0]
    assert len(out) == 2, out


def test_a_lone_accent_is_untouched():
    acc = _g("˙", "dotaccent", 100.0)
    out = D._compose_text_accents([[acc]])[0]
    assert len(out) == 1 and out[0].text == "˙"
