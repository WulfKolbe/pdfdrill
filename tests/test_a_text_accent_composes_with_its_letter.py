r"""An accent over a letter is one character, not a maths command.

TeX sets `Saarbr\"ucken` as the dieresis FIRST, at an offset, then the base
letter one point to its left:

    39  r         x=370.94
    40  dieresis  x=375.92   tex.latex='\ddot'
    41  u         x=374.92

`\ddot` is a MATHS accent, so the dieresis opened a maths span and dragged the
rest of the word into it. pdfdrill read the affiliation line of 0864 as

    1Max Planck Institute for Informatics, Saarbr $\mathrm{ucken},$ Germany

and pdf2mmd2, from the same glyphs, cut the line in two instead:

    x=550  'Max Planck Institute for Informatics, Saarbr¨'
    x=1302 'ucken, Germany'

against MathPix's one line `...Informatics, Saarbrücken, Germany`. Measured on
0864: 42 of the 69 unpaired open-page lines are an accent or end at one, and
most of the other 27 are the tail of such a cut.

`structure._merge_accents` already composes a MATHS accent into
`\widehat{...}`. It never sees this one, because the word is prose and never
reaches the maths structure pass. So a TEXT-family accent is composed here,
into the precomposed character the page actually shows, before spans are
decided -- then no maths span opens and nothing is cut.

NOT DONE: ROTATED TEXT. The base is found by horizontal overlap, because TeX
centres the accent over its base; for a glyph rotated 90 degrees the offset is
along the other axis and that test is simply the wrong one. Two lines of
0864 p4 -- the sideways axis labels of a chart -- still read a bare `\u02c6`
after this change, and they are left that way rather than guessed at.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfreader.docmodel_six import (GlyphNode, _compose_text_accents)  # noqa: E402
from pdfreader.texmap import TexToken  # noqa: E402


def _g(text, name, x, family="text", latex=None, kind="atom", base=636.3):
    return GlyphNode(id="g" + name, page=1,
                     rect=(x, base, x + 6.0, base + 8.0), text=text,
                     cid=0, glyphname=name, fontname="NimbusRomNo9L-Regu",
                     family=family, size=12.0,
                     tex=TexToken(latex, kind, None, "corpus"))


def _texts(rows):
    return ["".join(g.text for g in r) for r in rows]


def test_a_dieresis_and_its_u_become_u_umlaut():
    row = [_g("r", "r", 370.94),
           _g("¨", "dieresis", 375.92, latex=r"\ddot", kind="accent"),
           _g("u", "u", 374.92),
           _g("c", "c", 380.90)]
    out = _compose_text_accents([row])
    assert _texts(out) == ["rüc"], _texts(out)
    assert len(out[0]) == 3, "the accent and its base are ONE glyph now"


def test_the_composed_glyph_covers_both_boxes():
    row = [_g("¨", "dieresis", 375.92, latex=r"\ddot", kind="accent"),
           _g("u", "u", 374.92)]
    out = _compose_text_accents([row])
    g = out[0][0]
    assert g.rect[0] <= 374.92 and g.rect[2] >= 381.92, g.rect


def test_an_acute_over_an_e_composes():
    row = [_g("´", "acute", 100.5, latex=r"\acute", kind="accent"),
           _g("e", "e", 100.0)]
    assert _texts(_compose_text_accents([row])) == ["é"]


def test_a_maths_accent_is_left_for_the_structure_pass():
    """`\\widehat{\\otimes}` must still reach `structure._merge_accents`."""
    row = [_g("", "hatwide", 50.0, family="math-symbol",
              latex=r"\widehat", kind="accent"),
           _g("⊗", "circlemultiply", 50.0, family="math-symbol",
              latex=r"\otimes")]
    out = _compose_text_accents([row])
    assert len(out[0]) == 2, "a maths accent is not composed here"


def test_an_accent_with_no_base_after_it_is_left_alone():
    row = [_g("¨", "dieresis", 375.92, latex=r"\ddot", kind="accent")]
    assert len(_compose_text_accents([row])[0]) == 1


def test_a_letter_far_from_the_accent_is_not_its_base():
    row = [_g("¨", "dieresis", 100.0, latex=r"\ddot", kind="accent"),
           _g("u", "u", 400.0)]
    assert len(_compose_text_accents([row])[0]) == 2
