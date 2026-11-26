r"""
B12, 0864 p4: prose in NimbusRomNo9L (Times), maths in Computer Modern. The
axis labels `rnd(Opus_mon, Opus_spc)` take their brackets from CMR7, "70%"
its digits and `%` from CMR10. Read as text they came out in Times and were
flagged on ink; as maths they take CM. And an unnamed CMR10 `%` inside maths
is `\%`, never a bare comment sign. Judge (pin f78391d) 0864 p4: 0.0039 ->
0.0020, glyph findings 12 -> 4.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")
from pdfreader.texmap import UNKNOWN

TIMES = "ABCDEF+NimbusRomNo9L-Regu"


def _g(ch, x, font, family, size=9.96, gap=0.0):
    w = 0.5 * size
    return D.GlyphNode(id="g%.1f" % x, page=2, rect=(x, 100.0, x + w, 100.0 + size),
                       text=ch, cid=0, glyphname=None, fontname=font, family=family,
                       size=size, tex=UNKNOWN, matrix=(size, 0, 0, size, x, 100.0))


def _line(parts):
    out, x = [], 0.0
    for ch, font, fam in parts:
        out.append(_g(ch, x, font, fam))
        x += 5.0
    return out


def _marked(glyphs):
    m = D._cm_maths_marks(glyphs)
    return "".join(g.text for g in glyphs if id(g) in m)


def test_cm_brackets_in_a_times_label_are_maths():
    gs = _line([(c, TIMES, "text") for c in "rnd"] + [("(", "XYZ+CMR7", "text-cm")]
               + [(c, TIMES, "text") for c in "Opus"] + [(")", "XYZ+CMR7", "text-cm")])
    assert _marked(gs) == "()"


def test_a_percentage_in_cm_is_maths_with_its_digits():
    gs = _line([(c, TIMES, "text") for c in "in"] + [(c, "XYZ+CMR10", "text-cm") for c in "70%"]
               + [(c, TIMES, "text") for c in "of"])
    assert _marked(gs) == "70%"


def test_cm_digits_alone_stay_prose():
    gs = _line([(c, "XYZ+CMR10", "text-cm") for c in "32"] + [("x", TIMES, "text")]
               + [(c, "XYZ+CMR10", "text-cm") for c in "32"] + [(c, TIMES, "text") for c in "images"])
    assert _marked(gs) == ""


def test_times_with_a_tag_that_spells_cmr_is_not_cm():
    gs = _line([("(", "HffcmrYvygwvTimes-Roman", "text-cm")]
               + [(c, TIMES, "text") for c in "Example"] + [(")", "HffcmrYvygwvTimes-Roman", "text-cm")])
    assert _marked(gs) == ""


def test_an_unnamed_percent_in_maths_is_escaped():
    assert D.glyph_latex(_g("%", 0.0, "XYZ+CMR10", "text-cm")) == r"\%"
