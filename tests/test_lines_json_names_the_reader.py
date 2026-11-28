r"""lines.json names the reader its records came from (T-0174, board rows).

`reader` is `pdfminer <version>` or `pdfread bin:<sha256 12>`;
`reader_fallback` is true when PDFDRILL_READER=pdfread was asked for and
pdfminer read instead.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

dm = pytest.importorskip("pdfreader.docmodel_six")
ps = pytest.importorskip("pdfreader.pdfread_source")

FIX = sorted((Path(__file__).parent / "fixtures" / "psred").rglob("*.pdf"))


def _lj(pdf):
    return dm.to_lines_json(dm.build(str(pdf)))


def test_the_default_reader_is_pdfminer(monkeypatch):
    monkeypatch.delenv("PDFDRILL_READER", raising=False)
    lj = _lj(FIX[0])
    assert lj["reader"].startswith("pdfminer ")
    assert lj["reader_fallback"] is False


def test_a_failed_switch_says_it_fell_back(monkeypatch):
    monkeypatch.setenv("PDFDRILL_READER", "pdfread")
    monkeypatch.setenv("PDFREAD", "/nonexistent/pdfread")
    lj = _lj(FIX[0])
    assert lj["reader"].startswith("pdfminer ")
    assert lj["reader_fallback"] is True


@pytest.mark.skipif(ps.binary() is None, reason="no pdfread binary")
def test_the_switch_names_the_binary(monkeypatch):
    monkeypatch.setenv("PDFDRILL_READER", "pdfread")
    lj = _lj(FIX[0])
    assert lj["reader"].startswith("pdfread bin:") and len(lj["reader"]) == 24
    assert lj["reader_fallback"] is False
