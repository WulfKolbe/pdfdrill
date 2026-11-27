r"""
B13, lib:c57ac038ae5f p293: "By (13.5) we have Q(x_k + alpha p_k) = ... +
1/2 alpha^2 p_k^T A p_k, where r_k :=" came out as one maths span,
`$\mathrm{By} (13.5) \mathrm{we} \mathrm{have} ...$`. Two causes:

- the body font `HffcmrYvygwvTimes-Roman` (subset tag glued on with no `+`)
  was taken for Computer Modern because the tag spells `cmr`;
- a line with a fraction bar and mostly maths was kept whole as maths, even
  when it opens like a sentence.

Judge (pin 8a67b8a) c57a p293: 0.0042 -> 0.0025.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")
from pdfreader import texmap as T
from pdfreader.texmap import UNKNOWN


def test_times_with_a_cmr_tag_is_text():
    assert T.family_of("HffcmrYvygwvTimes-Roman") == "text"
    assert T.family_of("CMR10") == "text-cm"


def _g(ch, x, family="text", font="ABC+Times-Roman"):
    return D.GlyphNode(id="g%.1f" % x, page=2, rect=(x, 100.0, x + 5.0, 110.0),
                       text=ch, cid=0, glyphname=None, fontname=font, family=family,
                       size=10.0, tex=UNKNOWN, matrix=(10, 0, 0, 10, x, 100.0))


def _line(text, start=0.0):
    out, x = [], start
    for ch in text:
        if ch != " ":
            fam = "math-italic" if ch in "Qαx" else "text"
            out.append(_g(ch, x, fam, "ABC+CMMI10" if fam != "text" else "ABC+Times-Roman"))
        x += 5.0 if ch != " " else 4.0
    return out


def test_a_line_opening_with_a_word_is_prose():
    assert D._has_prose_word(_line("By (13.5) we have Q(x)"))


def test_a_display_opening_with_maths_is_not():
    assert not D._has_prose_word(_line("Q(x) = x, also x"))


def test_an_operator_name_is_not_a_word():
    assert not D._has_prose_word(_line("log Q(x)"))
