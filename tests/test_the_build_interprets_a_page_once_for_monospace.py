r"""
SPEED (EXACT): `build` interpreted every page twice, once in
`_advance_samples` (laparams=None) only to measure which fonts are
monospace, and once for the build. A document of up to
`_ONE_PASS_MAX_PAGES` pages is now interpreted once: the samples come from
the build's own layouts, which carry the same glyphs (equal multisets on all
24 born board extracts), and the same layouts are then processed. A longer
document, or a read error, takes the old route.

24 board extracts, warm bytecode, one core: 80.8 -> 75.4 s and 82.2 ->
75.8 s with the cores swapped; lines.json byte-identical.
"""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")
FIX = Path(__file__).parent / "fixtures" / "psred" / "mathrows" / "r00.pdf"


def test_the_layout_samples_are_the_separate_pass_samples():
    from pdfminer.high_level import extract_pages
    a = collections.Counter(D._advance_samples(str(FIX), None))
    b = collections.Counter(D._layout_samples(list(extract_pages(str(FIX)))))
    assert a == b and a


def test_a_short_document_does_not_take_the_second_pass(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("second pdfminer pass")
    monkeypatch.setattr(D, "_advance_samples", refuse)
    pages = D.build(str(FIX))
    assert pages and pages[0].lines
