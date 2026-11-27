r"""
B14, lib:69bc5c71b881 p16:

- "Eavor-Loop(TM)" sets its TM at 5.54 pt, 3.7 pt above the 9.5 pt line.
  Read flat it sat 0.57 of a size too low; it is `\textsuperscript{TM}`.
- The footer draws its page number "16" (x 583) before "CATF - Superhot Rock
  Energy" (x 20). Stream order read "16CATF"; across a gap of more than
  10 em, x orders a row.

Judge (pin inkdrill 5b2f283) 69bc p16: 0.0025 -> 0.0007. Positions and
sizes are the page's own.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")
from pdfreader.texmap import UNKNOWN


def _g(ch, x, base, size, stream, font="ABC+CircularStd-Book"):
    w = 0.55 * size
    return D.GlyphNode(id="g%d" % stream, page=2, rect=(x, base - 0.2 * size, x + w, base + 0.7 * size),
                       text=ch, cid=0, glyphname=None, fontname=font, family="text",
                       size=size, tex=UNKNOWN, matrix=(size, 0, 0, size, x, base), stream=stream)


def _word(text, x, base, size, s0):
    out = []
    for i, ch in enumerate(text):
        out.append(_g(ch, x, base, size, s0 + i))
        x += 0.55 * size
    return out, x


def test_a_trademark_is_a_superscript():
    a, x = _word("Loop", 100.0, 175.1, 9.5, 0)
    b, x = _word("TM", x + 0.3, 178.8, 5.54, 10)
    c, _ = _word("and", x + 2.6, 175.1, 9.5, 20)
    out = D._text_with_superscripts(a + b + c)
    assert out == r"Loop\textsuperscript{TM} and", out


def test_a_level_line_is_untouched():
    a, x = _word("plain", 100.0, 175.1, 9.5, 0)
    assert D._text_with_superscripts(a) == D._faced_text(a)


def test_a_far_page_number_is_read_after_the_title():
    num, _ = _word("16", 583.5, 17.0, 8.5, 0)
    title, _ = _word("CATF", 20.0, 17.0, 8.0, 2)
    got = "".join(g.text for g in D._row_order(num + title))
    assert got == "CATF16", got


def test_a_tight_row_keeps_stream_order():
    a, x = _word("ab", 100.0, 17.0, 10.0, 5)
    b, _ = _word("cd", x + 1.0, 17.0, 10.0, 0)
    assert "".join(g.text for g in D._row_order(a + b)) == "cdab"
