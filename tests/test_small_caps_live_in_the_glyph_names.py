r"""Libertine keeps its small capitals inside its own program, so the font
name reads plain and `is_small_caps` misses them.

T-0156, reported by inkdrill-10 from 1805.01788 p3. The `libertine` package
has no separate small-caps font: `LinLibertineT` carries them as glyphs named
`e.sc`, `i.sc`, `n.sc`, `t.sc` and so on. The judge reads them from the glyph
name (inkdrill 0cd3098) and the reader can do the same.

MEASURED on the board set: 54 such glyphs, all on that one page, in two
spans — the heads of Definition 1 and Definition 2. No other board page has
any. The letters themselves are already correct; only the `\textsc` marking
is missing, so this moves `style_rate` and not the residual.

THE WHOLE SPAN IS WRAPPED, and that is right rather than convenient. The two
spans read

    'Definition 1 (Equity of Attention).'
    'Definition 2 (Equity of Amortized Attention).'

with names `D, e.sc, f.sc, i.sc, n.sc, i.sc, t.sc, i.sc, o.sc, n.sc, one,
parenleft, E, q.sc_u.sc, …`. A small-cap word is set with its first letter a
FULL capital and the rest small, which is exactly what `\textsc{Definition 1
(Equity of Attention).}` renders: `\textsc` leaves capitals, digits and
punctuation alone and sets the lowercase as small capitals. So "every glyph
is `.sc`" would be the wrong test — it fails on the real shape, where `D`,
`E`, `one` and `parenleft` are not.

THE TEST IS: at least one `.sc` glyph, and NO PLAIN LOWERCASE GLYPH. A
lowercase letter from a non-`.sc` glyph cannot occur inside `\textsc`, so one
contradicts the claim. MEASURED on those two spans: 23 and 31 `.sc` glyphs
and ZERO plain lowercase in either.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

texmap = pytest.importorskip("pdfreader.texmap")


def test_a_span_of_small_cap_glyphs_is_small_caps():
    """The real shape: a full capital, then `.sc` letters, with a digit and
    a bracket among them."""
    names = ["D", "e.sc", "f.sc", "i.sc", "n.sc", "one", "parenleft",
             "E", "q.sc_u.sc"]
    assert r"\textsc" in texmap.emphasis_for({"ABC+LinLibertineT"},
                                             glyphnames=names,
                                             has_lowercase=False)


def test_a_plain_lowercase_glyph_contradicts_it():
    """A lowercase letter cannot occur inside `\textsc`, so one is enough to
    refuse the claim — otherwise a line that merely mentions a small-cap
    word would be set entirely in small capitals."""
    names = ["D", "e.sc", "f.sc", "a", "b"]
    assert r"\textsc" not in texmap.emphasis_for({"ABC+LinLibertineT"},
                                                 glyphnames=names,
                                                 has_lowercase=True)


def test_no_sc_glyph_means_no_small_caps():
    assert r"\textsc" not in texmap.emphasis_for({"ABC+LinLibertineT"},
                                                 glyphnames=["D", "e", "f"],
                                                 has_lowercase=True)


def test_the_font_name_route_still_works():
    """`Times-RomanSmallCaps` names itself and needs no glyph evidence —
    the 45 glyphs on lib:3fe71b4ef018 p328."""
    assert r"\textsc" in texmap.emphasis_for(
        {"YNAJWO+LnrnjhTimes-RomanSmallCaps"})


def test_a_plain_face_with_no_sc_glyphs_is_plain():
    assert texmap.emphasis_for({"ABC+LinLibertineT"},
                               glyphnames=["a", "b", "c"],
                               has_lowercase=True) == []


def test_the_default_arguments_keep_the_old_behaviour():
    """Every existing caller passes font names only."""
    assert texmap.emphasis_for({"ABC+CMBX10"}) == [r"\textbf"]
    assert texmap.emphasis_for({"ABC+CMR10"}) == []
