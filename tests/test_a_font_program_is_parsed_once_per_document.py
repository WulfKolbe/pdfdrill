r"""
SPEED (EXACT): `ink_boxes` runs a fresh resource manager for every page, so
the font program cached on the font object lived one page: 43 Type 1 parses
for 12 board pages, 19 of 141 profiled seconds of `glyphlines`. The program
is now kept per DOCUMENT, keyed by its FontFile stream's object number, and a
glyph's bounds once per program. The 24 born board pages' lines.json are
byte-identical with and without it.

Guarded here: a second read of the same document parses nothing, and a read
of another document in between changes no box (the id-reuse failure the
module's docstring describes).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

IB = pytest.importorskip("pdfreader.inkboxes")
T1 = pytest.importorskip("fontTools.t1Lib")

FIX = Path(__file__).parent / "fixtures" / "psred" / "mathrows"


@pytest.fixture
def parses(monkeypatch):
    n = {"count": 0}
    orig = T1.T1Font.parse

    def counting(self, *a, **k):
        n["count"] += 1
        return orig(self, *a, **k)
    monkeypatch.setattr(T1.T1Font, "parse", counting)
    # the lean reader (board 118, option (a)) reads a Type 1 program without
    # T1Font.parse; a program read either way is one parse
    lean = IB._t1_program

    def counting_lean(data):
        n["count"] += 1
        return lean(data)
    monkeypatch.setattr(IB, "_t1_program", counting_lean)
    return n


def _boxes(pdf):
    return [(r["name"], r["ink"]) for r in IB.ink_boxes(str(pdf), 1)]


def test_a_second_read_parses_nothing(parses):
    if IB.build_gap():
        pytest.skip(IB.build_gap())
    IB._DOC_PROGRAMS.update(doc=None, progs={})
    first = _boxes(FIX / "r00.pdf")
    n1 = parses["count"]
    assert n1 > 0
    again = _boxes(FIX / "r00.pdf")
    assert parses["count"] == n1
    assert again == first


def test_another_document_between_changes_no_box():
    if IB.build_gap():
        pytest.skip(IB.build_gap())
    IB._DOC_PROGRAMS.update(doc=None, progs={})
    fresh = _boxes(FIX / "r00.pdf")
    _boxes(FIX / "r01.pdf")
    assert _boxes(FIX / "r00.pdf") == fresh
