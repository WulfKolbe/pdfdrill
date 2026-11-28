r"""
SPEED (EXACT): `LineNode.spans` ran `_spans` on every read: 2,428 times
for one 3-page board extract, mostly from the projections. It is memoised
only inside `docmodel_six.spans_memo()`, which read-only phases open
(`to_lines_json`, and `glyphlines`' Markdown, crop list and LaTeX once their
mutating passes have run). The model is changed while it is built and by
`absorb_equation_numbers`, so outside a phase nothing is memoised. 0864 p4:
868 calls; 24 born extracts: lines.json, .glyphs.md and .glyphs.tex
byte-identical, glyphlines 68.0 -> 65.2 s side by side on one core.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")
FIX = Path(__file__).parent / "fixtures" / "psred" / "mathrows" / "r00.pdf"


def _counting(monkeypatch):
    n = {"c": 0}
    orig = D._spans

    def counting(line):
        n["c"] += 1
        return orig(line)
    monkeypatch.setattr(D, "_spans", counting)
    return n


def test_inside_a_phase_a_line_is_computed_once(monkeypatch):
    ln = next(l for p in D.build(str(FIX)) for l in p.lines if l.glyphs)
    n = _counting(monkeypatch)
    with D.spans_memo():
        a, b = ln.spans, ln.spans
    assert n["c"] == 1 and [s.id for s in a] == [s.id for s in b]
    assert a is not b                     # a fresh list each read


def test_outside_a_phase_nothing_is_memoised(monkeypatch):
    ln = next(l for p in D.build(str(FIX)) for l in p.lines if l.glyphs)
    n = _counting(monkeypatch)
    ln.spans
    ln.spans
    assert n["c"] == 2


def test_a_change_after_the_phase_is_seen(monkeypatch):
    ln = next(l for p in D.build(str(FIX)) for l in p.lines if len(l.glyphs) > 2)
    with D.spans_memo():
        before = sum(len(s.glyphs) for s in ln.spans)
    ln.glyphs = ln.glyphs[:-1]
    assert sum(len(s.glyphs) for s in ln.spans) == before - 1


def test_nested_phases_share_one_memo(monkeypatch):
    ln = next(l for p in D.build(str(FIX)) for l in p.lines if l.glyphs)
    n = _counting(monkeypatch)
    with D.spans_memo():
        ln.spans
        with D.spans_memo():
            ln.spans
    assert n["c"] == 1


def test_a_lines_plain_text_is_memoised_only_inside_the_phase():
    # SPEED (EXACT), board 118's to_lines_json: classify_lines asked for the
    # same line's plain text from four places; inside the phase it is kept
    from pdfreader import docmodel_six as _dm
    from pdfreader import texmap as _tm
    g = [_dm.GlyphNode(id=f"g{i}", page=1, rect=(5.0 * i, 0, 5.0 * i + 4, 10),
                       text=c, cid=0, glyphname=None, fontname="CMR10",
                       family="text-cm", size=10.0, tex=_tm.UNKNOWN)
         for i, c in enumerate("abc")]
    calls = []
    real = _dm._run_text_raw

    def counting(*a, **k):
        calls.append(1)
        return real(*a, **k)
    _dm._run_text_raw = counting
    try:
        with _dm.spans_memo():
            first = _dm._run_text(g)
            second = _dm._run_text(g)
        assert first == second == real(g) and len(calls) == 1
        _dm._run_text(g)
        assert len(calls) == 2           # outside the phase: computed again
        with _dm.spans_memo():
            _dm._run_text(g, word_gap=3.0)
            _dm._run_text(g, word_gap=3.0)
        assert len(calls) == 4           # a non-default call is not kept
    finally:
        _dm._run_text_raw = real
