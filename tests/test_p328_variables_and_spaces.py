r"""The coordinator's read of lib:3fe71b4ef018 p328 (board 126), as units.

- a single space among touching glyphs is a word break (`system (`);
- one italic letter before a relation is maths: `$Q = ...$`;
- up to three italic letters END a maths line inside it (`c\,dt`);
- a face change adds no second space.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

dm = pytest.importorskip("pdfreader.docmodel_six")


def _g(x0, x1, size=10.0):
    return SimpleNamespace(rect=(x0, 0, x1, size), size=size)


def test_one_space_among_touching_glyphs_is_a_word_break():
    xs, gs, x = [4.0] * 6, [], 0.0
    for w in xs:                                # system
        gs.append(_g(x, x + w)); x += w
    x += 2.03                                   # the space before "("
    for w in [3.0] * 8:                         # (Mc-Guire
        gs.append(_g(x, x + w)); x += w
    wg = dm._word_gap(gs)
    assert wg < 2.03                             # was 0.22 em = 2.2


def test_a_gap_before_a_bracket_of_0_16_em_is_not_taken_alone():
    gs, x = [], 0.0
    for _ in range(8):
        gs.append(_g(x, x + 6, size=12.0)); x += 6
    x += 1.95                                   # c9da p68 `5.3 )`
    gs.append(_g(x, x + 4, size=12.0))
    assert dm._word_gap(gs) == pytest.approx(0.22 * 12.0)


def test_no_double_space_at_a_face_change(monkeypatch):
    def run_text(glyphs, word_gap=0.0, **_k):
        return "".join(g.text for g in glyphs)

    monkeypatch.setattr(dm, "_run_text", run_text)
    monkeypatch.setattr(dm.texmap, "emphasis_for",
                        lambda f, n=(), lo=True: ["\\textit"] if all("Italic" in x for x in f) else [])
    monkeypatch.setattr(dm.texmap, "wrap_emphasis",
                        lambda t, f, n=(), lo=True: "\\textit{%s}" % t if all("Italic" in x for x in f) else t)
    G = lambda t, f, x: SimpleNamespace(text=t, fontname=f, glyphname=t,
                                        rect=(x, 0, x + 4, 10), size=10.0)
    gs = [G("f", "Roman", 0), G("u", "Roman", 4), G("r", "Roman", 8),
          G(" ", "Roman", 12), G("n", "Italic", 20)]
    assert dm._faced_text(gs, wg=2.0) == "fur \\textit{n}"
