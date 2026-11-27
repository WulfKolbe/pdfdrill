r"""
SPEED (EXACT): `_stream_index` interpreted every page once more, only to
record at `render_char` each glyph's drawing position. `_pages_with_order`
is `extract_pages` line for line, with an aggregator that records the same
thing at the same callback, so a short document's build takes layouts and
stream order from ONE interpretation. The index is equal on all 24 born
board extracts; 24 extracts, warm bytecode, one core: 71.3 -> 66.7 s and
72.0 -> 67.1 s with the cores swapped; lines.json byte-identical.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

D = pytest.importorskip("pdfreader.docmodel_six")
FIX = Path(__file__).parent / "fixtures" / "psred" / "mathrows" / "r00.pdf"


def test_the_order_equals_the_separate_index():
    old = D._stream_index(str(FIX), None)
    new = {i + 1: seen for i, (_, seen) in enumerate(D._pages_with_order(str(FIX), None))}
    assert old == new and old[1]


def test_the_layouts_equal_extract_pages():
    from pdfminer.high_level import extract_pages
    a = [repr(list(l)) for l in extract_pages(str(FIX))]
    b = [repr(list(l)) for l, _ in D._pages_with_order(str(FIX), None)]
    assert a == b


def test_a_short_document_does_not_take_the_third_pass(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("third pdfminer pass")
    monkeypatch.setattr(D, "_stream_index", refuse)
    pages = D.build(str(FIX))
    assert pages and any(g.stream is not None and g.stream >= 0
                         for ln in pages[0].lines for g in ln.glyphs)
