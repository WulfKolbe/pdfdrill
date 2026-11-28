r"""`\nocorr` where a slanted or italic run is touched by the next run.

lib:d68e0271bd4d p334 (inkdrill, board 124): CMSL8 `l` ends its advance at
359.315 and CMSY7 `>` starts at 359.18. `\textsl{CMel}$\rangle..$` added the
l's italic correction and set the `>` 0.39 pt right of the page's.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

dm = pytest.importorskip("pdfreader.docmodel_six")


def _faced(monkeypatch, second_x0, second_text=">"):
    runs = {"sl": "CMel", "sy": second_text}

    def run_text(glyphs, word_gap=0.0, **_k):
        return "".join(g.text for g in glyphs)

    def emph(fonts, names=(), lower=True):
        return ["\\textsl"] if all("CMSL" in f for f in fonts) else []

    def wrap(text, fonts, names=(), lower=True):
        return "\\textsl{%s}" % text if emph(fonts) else text

    monkeypatch.setattr(dm, "_run_text", run_text)
    monkeypatch.setattr(dm.texmap, "emphasis_for", emph)
    monkeypatch.setattr(dm.texmap, "wrap_emphasis", wrap)
    gs = []
    x = 350.0
    for ch in "CMel":
        gs.append(SimpleNamespace(text=ch, fontname="X+CMSL8", glyphname=ch,
                                  rect=(x, 0, x + 2.057, 7), size=6.97))
        x += 2.3
    gs.append(SimpleNamespace(text=second_text, fontname="X+CMSY7",
                              glyphname="angbracketright",
                              rect=(second_x0, 0, second_x0 + 2.7, 7), size=6.97))
    return dm._faced_text(gs, wg=1.5)


def test_a_touching_run_gets_nocorr(monkeypatch):
    last_end = 350.0 + 3 * 2.3 + 2.057
    assert _faced(monkeypatch, last_end - 0.13) == "\\textsl{CMel\\nocorr}>"


def test_a_run_set_with_the_correction_keeps_it(monkeypatch):
    last_end = 350.0 + 3 * 2.3 + 2.057
    assert _faced(monkeypatch, last_end + 0.39) == "\\textsl{CMel}>"


def test_a_comma_needs_no_nocorr(monkeypatch):
    last_end = 350.0 + 3 * 2.3 + 2.057
    assert _faced(monkeypatch, last_end - 0.1, ",") == "\\textsl{CMel},"
