r"""PDFDRILL_READER=pdfread gives the build pdfminer's reading, bit for bit.

T-0174: `pdfread_source.read` turns pdfread's records into the layout tree,
stream index, ink records, links, line bands and crop boxes the build takes
from pdfminer. The gate on the 24 born board extracts is the full lines.json;
here, the build's inputs are compared on the committed fixture PDFs. Skips
where no pdfread binary is installed ($PDFREAD, or `pdfread` on PATH).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

ps = pytest.importorskip("pdfreader.pdfread_source")
dm = pytest.importorskip("pdfreader.docmodel_six")

FIX = sorted((Path(__file__).parent / "fixtures" / "psred").rglob("*.pdf"))[:12]


def _flat(layout):
    items = []
    for e in layout:
        dm._walk(e, items)
    return [(type(o).__name__, o.bbox,
             getattr(o, "fontname", None), getattr(o, "cid", None),
             getattr(o, "glyphname", None),
             o.get_text() if hasattr(o, "get_text") else None,
             getattr(o, "matrix", None), getattr(o, "size", None),
             getattr(o, "upright", None), getattr(o, "invisible", None),
             getattr(getattr(o, "graphicstate", None), "ncolor", None),
             getattr(o, "fill", None), getattr(o, "non_stroking_color", None))
            for o in items]


@pytest.mark.skipif(ps.binary() is None, reason="no pdfread binary")
@pytest.mark.parametrize("pdf", FIX, ids=lambda p: p.stem)
def test_records_rebuild_pdfminers_reading(pdf):
    rd = ps.read(str(pdf), None, True)
    mine = list(dm._pages_with_order(str(pdf), None, ink=True))
    assert len(rd["pairs"]) == len(mine)
    for (la, sa, ra), (lb, sb, rb) in zip(rd["pairs"], mine):
        assert _flat(la) == _flat(lb)
        assert la.bbox == lb.bbox
        assert sa == sb
        assert ra == rb
    assert rd["bands"] == dm._line_bands(str(pdf), None)
    assert rd["crop"] == dm._cropboxes(str(pdf))
    key = lambda d: {p: [(l.rect, l.uri, l.dest) for l in v] for p, v in d.items()}
    assert key(rd["links"]) == key(dm._page_links(str(pdf), None))


def test_the_switch_is_off_by_default(monkeypatch):
    monkeypatch.delenv("PDFDRILL_READER", raising=False)
    assert not ps.wanted()
    monkeypatch.setenv("PDFDRILL_READER", "pdfread")
    assert ps.wanted()


def test_a_missing_binary_falls_back_to_pdfminer(monkeypatch, capsys):
    if not FIX:
        pytest.skip("no fixture PDF")
    monkeypatch.setenv("PDFDRILL_READER", "pdfread")
    monkeypatch.setenv("PDFREAD", "/nonexistent/pdfread")
    dm.build(str(FIX[0]))
    assert dm.LAST_READER == "pdfminer"
    assert "PDFDRILL_READER=pdfread failed" in capsys.readouterr().err
