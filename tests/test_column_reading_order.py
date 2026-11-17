"""A two-column page's lines come out in reading order, not stream order.

`_add_column_containers` states the columns as containers because "that
nesting IS the reading order of a two-column paper, stated rather than left for
each consumer to guess from x-coordinates" -- but the flat `lines` list kept
the order the content stream emits, and every consumer that walks it (a
markdown projection, the ink judge, a CER against the page's own text layer)
read the columns interleaved.

Measured on the board page lib:69bc5c71b881 p16 (91 lines, every one assigned
to one of 2 columns). Left/right of each line in list order was
`LLRRLLLLLLLLRRRRRRRLLLL...` against MathPix's `LLLL...RRRR...`: the stream
emits two lines of the left column, two of the right, and we followed it.
Order-free the two readings of that page differ by 8 words missing and 18 extra
of 714, yet our CER against the page's text layer was 0.3169 against MathPix's
0.0151. After this change, 0.0875.

The guard is the point of the second test: only a page where EVERY line belongs
to a column is reordered. A page with a full-width line between column blocks
needs that line placed in a band, and a band rule with no measurement behind it
would move text that is in the right place today.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

docmodel = pytest.importorskip("pdfreader.docmodel_six")


def _line(ident, x0, y_top):
    return docmodel.LineNode(id=ident, page=1,
                             rect=(x0, y_top - 10.0, x0 + 200.0, y_top),
                             type="text")


def _page(lines):
    return docmodel.PageNode(page=1, rect=(0.0, 0.0, 612.0, 792.0),
                             lines=list(lines))


#: the shape measured on p16: two lines of the left column, two of the right
_INTERLEAVED = [_line("l0", 61, 730), _line("l1", 61, 717),
                _line("r0", 319, 731), _line("r1", 319, 718),
                _line("l2", 61, 705), _line("r2", 319, 705)]


def _patch(monkeypatch, member):
    import pdfreader.project_mmd as pm
    monkeypatch.setattr(pm, "column_membership", lambda p: dict(member),
                        raising=False)


def test_a_fully_columnised_page_is_reordered_column_major(monkeypatch):
    _patch(monkeypatch, {0: 0, 1: 0, 2: 1, 3: 1, 4: 0, 5: 1})
    out = docmodel._column_reading_order([_page(_INTERLEAVED)])
    assert [ln.id for ln in out[0].lines] == ["l0", "l1", "l2", "r0", "r1", "r2"]


def test_a_page_with_a_line_outside_every_column_keeps_its_order(monkeypatch):
    # line 4 belongs to no column (a full-width heading): leave the page alone.
    _patch(monkeypatch, {0: 0, 1: 0, 2: 1, 3: 1, 5: 1})
    out = docmodel._column_reading_order([_page(_INTERLEAVED)])
    assert [ln.id for ln in out[0].lines] == [ln.id for ln in _INTERLEAVED]


def test_a_single_column_page_keeps_its_order(monkeypatch):
    _patch(monkeypatch, {i: 0 for i in range(len(_INTERLEAVED))})
    out = docmodel._column_reading_order([_page(_INTERLEAVED)])
    assert [ln.id for ln in out[0].lines] == [ln.id for ln in _INTERLEAVED]


def test_the_input_page_is_not_mutated(monkeypatch):
    _patch(monkeypatch, {0: 0, 1: 0, 2: 1, 3: 1, 4: 0, 5: 1})
    page = _page(_INTERLEAVED)
    before = [ln.id for ln in page.lines]
    docmodel._column_reading_order([page])
    assert [ln.id for ln in page.lines] == before


def test_a_membership_that_raises_leaves_the_page_alone(monkeypatch):
    import pdfreader.project_mmd as pm

    def boom(_p):
        raise RuntimeError("no columns here")

    monkeypatch.setattr(pm, "column_membership", boom, raising=False)
    out = docmodel._column_reading_order([_page(_INTERLEAVED)])
    assert [ln.id for ln in out[0].lines] == [ln.id for ln in _INTERLEAVED]
