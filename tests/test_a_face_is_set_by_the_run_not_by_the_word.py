"""
P6: the reading's faces follow the page's runs of one face.

- 4859 p1287 sets `metric, or distance` in italic (CMTI12) with a roman comma
  after it. Per word, `distance,` mixed two faces and got no italic, and the
  rest came out `\\textit{metric,} \\textit{or}`. Now each run of one face is
  wrapped, and neighbouring words of one face share one wrapper.
- 0864 p4 fakes small caps for GREEDY: a capital at 8.97 pt, capitals at
  7.17 pt on its baseline. Read as `GREEDY`, and with the face right (bold
  both sides) every capital was a glyph finding. It is `\\textsc{Greedy}`.
- BBOLD is blackboard bold (`\\mathbb`, the bbold package), not a bold face.

The glyphs are the pages' own, frozen.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader import docmodel_six as dm
from pdfreader import texmap as T

FIX = Path(__file__).parent / "fixtures" / "faces_and_small_caps.glyphs.json"


def _tup(v):
    return tuple(v) if isinstance(v, list) else v


def _glyphs(name):
    out = []
    for g in json.loads(FIX.read_text())[name]:
        g = {k: _tup(v) for k, v in g.items()}
        g["tex"] = T.TexToken(*g["tex"])
        out.append(dm.GlyphNode(**g))
    return out


def test_an_italic_phrase_with_a_roman_comma():
    text = dm._join_faces(dm._faced_text(_glyphs("emphasis")))
    assert text == r"a \textit{metric, or distance},", text


def test_neighbouring_words_of_one_face_share_a_wrapper():
    assert (dm._join_faces(r"\textbf{Definition} \textbf{37.1.} A")
            == r"\textbf{Definition 37.1.} A")
    assert dm._join_faces(r"\textit{x} $y$ \textit{z}") == r"\textit{x} $y$ \textit{z}"


def test_a_faked_small_caps_word_is_textsc():
    live = [g for g in _glyphs("small_caps") if g.text.strip()]
    assert dm._small_caps_word(live) == r"\textbf{\textsc{Greedy}}."


def test_bbold_is_blackboard_maths_not_bold_text():
    assert T.family_of("ScdkxjMhssxpBBOLD7") == "bbold"
    assert T.project("bbold", "k", -1, "X+BBOLD10").latex == r"\mathbb{k}"
