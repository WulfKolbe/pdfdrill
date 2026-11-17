r"""A float's rectangle comes from the page's own figure, not from its caption.

`merge_page_geometry` can only reach a float through its caption -- an
`\includegraphics` has no text of its own to match -- so what a float ends up
with is the caption's LINE. Measured on the owner's arxiv.2209.02970 page 9:

    before   x 127.38  y 195.17  w 340.51  h   9.96     the caption line
    after    x  70.87  y  70.87  w 453.54  h 113.78     the figure itself

`pdflatex` embeds an `\includegraphics` as a form XObject, which pdfminer
reports among the page's DIRECT children. Measured read-only over the library:
12 of 12 and 16 of 16 on two pdftex documents, against 246 "LTFigures" on a
dvips document that are all 1x1 stencil masks. Nested forms (140 and 127, up to
65 on a page) are Type3 glyph forms inside the figure, so only direct children
count.

The rule is narrow on purpose: exactly one float and one figure on the page, so
the pairing is forced. Caption ADJACENCY was measured as a second rule and
rejected -- over 25 ambiguous pages and 56 float-page pairs it resolves 5, and
would hand a wrong box to the 11 where two floats pick the same figure.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

figurebox = pytest.importorskip("pdfdrill.figurebox")


class _O:
    def __init__(self, type_, **props):
        self.type = type_
        self.props = dict(props)


class _Doc:
    def __init__(self, objs):
        self.objects = {i: o for i, o in enumerate(objs)}


def _page(n=1, w=595.28, h=841.89):
    return _O("Page", page_number=n, page_width=w, page_height=h)


def _para(h=11.0):
    return _O("Paragraph", region={"top_left_x": 0, "top_left_y": 0,
                                   "width": 400, "height": h})


def _caption_box():
    return {"top_left_x": 127.38, "top_left_y": 195.17,
            "width": 340.51, "height": 9.96}


#: the owner's page 9: one figure, 453.54 x 113.78 pt, above its caption
_FIG9 = {9: [(70.87, 657.24, 524.41, 771.02, 841.89)]}


def test_a_caption_line_box_is_replaced_by_the_figure(monkeypatch):
    monkeypatch.setattr(figurebox, "top_level_figures", lambda pdf, want=None: _FIG9)
    f = _O("Picture", page=9, region=_caption_box(), file="figures/example0907.png")
    doc = _Doc([_page(9), _para(), _para(), f])
    st = figurebox.figure_boxes(doc, Path("x.pdf"))
    assert st["figurebox_replaced_caption_line"] == 1
    r = f.props["region"]
    assert round(r["width"]) == 454 and round(r["height"]) == 114
    assert f.props["region_via"] == "pdf_figure"


def test_a_float_with_no_box_at_all_is_filled(monkeypatch):
    monkeypatch.setattr(figurebox, "top_level_figures", lambda pdf, want=None: _FIG9)
    f = _O("Picture", page=9, file="figures/example0907.png")
    doc = _Doc([_page(9), _para(), f])
    st = figurebox.figure_boxes(doc, Path("x.pdf"))
    assert st["figurebox_filled"] == 1


def test_a_measured_box_taller_than_a_line_is_never_overwritten(monkeypatch):
    monkeypatch.setattr(figurebox, "top_level_figures", lambda pdf, want=None: _FIG9)
    measured = {"top_left_x": 10, "top_left_y": 20, "width": 300, "height": 200}
    f = _O("Picture", page=9, region=dict(measured), file="a.png")
    doc = _Doc([_page(9), _para(), f])
    st = figurebox.figure_boxes(doc, Path("x.pdf"))
    assert st["figurebox_kept_measured"] == 1
    assert f.props["region"] == measured


def test_two_floats_on_one_page_are_left_alone(monkeypatch):
    monkeypatch.setattr(figurebox, "top_level_figures", lambda pdf, want=None: _FIG9)
    a = _O("Picture", page=9, region=_caption_box(), file="a.png")
    b = _O("Picture", page=9, region=_caption_box(), file="b.png")
    doc = _Doc([_page(9), _para(), a, b])
    st = figurebox.figure_boxes(doc, Path("x.pdf"))
    assert st["figurebox_ambiguous"] == 2
    assert a.props["region"] == _caption_box()


def test_a_page_with_no_figure_is_left_alone(monkeypatch):
    # The Chinese twin: a CJK caption reduces to a Latin fragment and matched
    # page 5, which carries no figure. The rule rejects it for free.
    monkeypatch.setattr(figurebox, "top_level_figures", lambda pdf, want=None: _FIG9)
    f = _O("Picture", page=5, region=_caption_box(), file="figures/example0907.png")
    doc = _Doc([_page(5), _para(), f])
    st = figurebox.figure_boxes(doc, Path("x.pdf"))
    assert st["figurebox_filled"] == 0 and st["figurebox_replaced_caption_line"] == 0
    assert f.props["region"] == _caption_box()


def test_markup_comes_off_a_caption_but_its_words_stay():
    out = figurebox.strip_markup(r"\caption{A \emph{wide} figure \label{fig:x}}")
    assert "label" not in out and "fig:x" not in out
    assert "wide" in out and "figure" in out
