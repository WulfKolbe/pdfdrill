r"""Latin maths variables set in the TEXT italic join the maths (p328 rules).

lib:3fe71b4ef018 p328 sets its Greek in MathTime (MTMI/MTSYN) and its Latin
variables in Times-Italic, family `text`. Two rules of `_spans_of`
(pdfdrill 5574c793), on small hand-made lines with p328's fonts:

- one italic letter directly before a maths run that starts with a
  relation is its left-hand side, in prose too: `$P = -Q\sin\delta$`;
- up to three italic letters that END a maths line are inside it
  (`... c\,dt`), but not in the middle of one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

dm = pytest.importorskip("pdfreader.docmodel_six")
texmap = pytest.importorskip("pdfreader.texmap")

ROMAN, ITALIC = "SQJWRA+KhnwyxTimes-Roman", "RBXWMQ+NyjrspTimes-Italic"
SYM, MI = "LNEOIM+MrvbhvMTSYN", "CRWVES+MjhtdgMTMI"
_N = [0]


def _g(text, x0, w, font, family, latex=None, size=9.963, base=378.7):
    _N[0] += 1
    tex = (texmap.TexToken(latex, "atom", None, "corpus") if latex
           else texmap.UNKNOWN)
    return dm.GlyphNode(
        id="g%d" % _N[0], page=1, rect=(x0, base - 2.0, x0 + w, base + size - 2.0),
        text=text, cid=0, glyphname=None, fontname=font, family=family,
        size=size, tex=tex, matrix=(size, 0, 0, size, x0, base))


def _word(s, x, font=ROMAN, w=4.5):
    out = []
    for ch in s:
        out.append(_g(ch, x, w, font, "text"))
        x += w
    return out, x


def _line(glyphs):
    xs = [g.rect for g in glyphs]
    rect = (min(r[0] for r in xs), min(r[1] for r in xs),
            max(r[2] for r in xs), max(r[3] for r in xs))
    return dm.LineNode(id="l1", page=1, rect=rect, type="text", glyphs=glyphs)


def _texts(glyphs):
    return [(sp.kind, dm.span_reading_text(sp)) for sp in dm._spans(_line(glyphs))]


def _rhs(x):
    """` = - Q \\sin \\delta` as p328 sets it."""
    out = [_g("=", x, 7.8, SYM, "math-symbol", "="),
           _g("−", x + 10.5, 7.8, SYM, "math-symbol", "-"),
           _g("Q", x + 19.0, 7.2, ITALIC, "text"),
           _g("\\sin", x + 28.4, 11.6, ROMAN, "math-symbol", "\\sin"),
           _g("δ", x + 41.8, 4.3, MI, "math-italic", "\\delta")]
    return out, x + 46.1


def test_an_italic_letter_before_a_relation_is_its_left_hand_side():
    w1, x = _word("strength", 50.0)
    p = _g("P", x + 2.5, 6.1, ITALIC, "text")
    rhs, x = _rhs(x + 2.5 + 6.1 + 3.6)
    w2, _ = _word("and", x + 2.5)
    spans = _texts(w1 + [p] + rhs + w2)
    maths = [t for k, t in spans if k == "math"]
    assert maths and maths[0].startswith("$P =")
    assert not any("\\textit{P}" in t for _k, t in spans)


def test_a_roman_word_before_a_relation_stays_prose():
    w1, x = _word("strength", 50.0)
    rhs, x = _rhs(x + 3.6)
    spans = _texts(w1 + rhs)
    assert spans[0] == ("text", "strength")


def test_an_italic_word_before_a_relation_stays_prose():
    w1, x = _word("called", 50.0)
    w2, x = _word("mass", x + 2.5, font=ITALIC)
    rhs, x = _rhs(x + 3.6)
    spans = _texts(w1 + w2 + rhs)
    assert not any(t.startswith("$mass") or "mass =" in t for _k, t in spans)


def _display_head(x=50.0):
    """`A = (Q \\sin\\delta) c` -- a line that is mostly maths."""
    out = [_g("A", x, 6.1, ITALIC, "text"),
           _g("=", x + 9.0, 7.8, SYM, "math-symbol", "="),
           _g("(", x + 19.5, 3.3, MI, "math-italic", "("),
           _g("Q", x + 23.0, 7.2, ITALIC, "text"),
           _g("\\sin", x + 32.0, 11.6, ROMAN, "math-symbol", "\\sin"),
           _g("δ", x + 45.4, 4.3, MI, "math-italic", "\\delta"),
           _g(")", x + 49.9, 3.3, MI, "math-italic", ")"),
           _g("c", x + 53.4, 4.4, ITALIC, "text")]
    return out, x + 57.8


def test_italic_letters_ending_a_maths_line_are_inside_it():
    head, x = _display_head()
    dt, _ = _word("dt", x + 1.66, font=ITALIC, w=4.4)   # a thin space
    spans = _texts(head + dt)
    assert all(k == "math" for k, _t in spans), spans
    assert not any("\\textit{dt}" in t for _k, t in spans)


def test_italic_letters_in_the_middle_of_a_maths_line_are_not_taken():
    head, x = _display_head()
    ds, x = _word("ds", x + 1.66, font=ITALIC, w=4.4)
    tail = [_g("+", x + 2.2, 7.8, SYM, "math-symbol", "+"),
            _g("δ", x + 12.2, 4.3, MI, "math-italic", "\\delta")]
    spans = _texts(head + ds + tail)
    assert any(k == "text" and "ds" in t for k, t in spans), spans
