"""`_sane_rect` MARKS the glyph it repairs; nothing re-derives it from the box.

`PDFDRILL_INK_ESTIMATED_ONLY` (6d0aad30) measures ink only on a page holding a
box `_sane_rect` replaced. That detection first recognised the replacement's
own arithmetic -- `baseline - 0.3*size .. baseline + 1.0*size` to 1e-6 -- which
worked on every page measured and had one failure mode nothing would report:
move a constant in the formula and the detector finds nothing, so the flag
silently becomes "never measure" and the reading quietly loses the repair it
exists for.

So the mark is set by the function that makes the decision, and these tests
change the constants to prove the mark does not depend on them.
"""
import pytest
from pdfreader import docmodel_six as D

#: CMEX10's descent is -2.359 em, so pdfminer puts a big operator's box about
#: 28 pt below its ink. Real numbers, from lib:4859edad9294 p1287.
CMEX_BBOX = (111.20, 340.05, 114.52, 352.00)
CMEX_BASELINE, CMEX_SIZE = 347.94, 9.96


def test_a_repaired_glyph_is_marked():
    rect, estimated = D._sane_rect_marked(CMEX_BBOX, CMEX_BASELINE, CMEX_SIZE)
    assert estimated is True
    assert rect[1] == pytest.approx(CMEX_BASELINE - D.EST_BELOW * CMEX_SIZE)
    assert rect[3] == pytest.approx(CMEX_BASELINE + D.EST_ABOVE * CMEX_SIZE)


def test_an_ordinary_descender_is_not_marked():
    # a `g`: below its baseline, but nothing like 0.6 em
    rect, estimated = D._sane_rect_marked((10.0, 345.0, 14.0, 355.0), 347.9, 10.0)
    assert estimated is False
    assert rect == (10.0, 345.0, 14.0, 355.0)     # returned untouched


def test_the_mark_survives_a_change_to_the_formula(monkeypatch):
    """THE TEST THE ARITHMETIC DETECTOR COULD NOT PASS.

    Move the replacement extent. The repair still happens and must still be
    reported; a detector that recognised `baseline-0.3*size` would now see an
    ordinary box and answer False.
    """
    monkeypatch.setattr(D, "EST_BELOW", 0.45)
    monkeypatch.setattr(D, "EST_ABOVE", 1.25)
    rect, estimated = D._sane_rect_marked(CMEX_BBOX, CMEX_BASELINE, CMEX_SIZE)
    assert estimated is True, "the mark must come from the decision, not the numbers"
    assert rect[1] == pytest.approx(CMEX_BASELINE - 0.45 * CMEX_SIZE)
    # and the old arithmetic detector, kept here as the thing being prevented:
    assert not (abs(rect[1] - (CMEX_BASELINE - 0.3 * CMEX_SIZE)) < 1e-6
                and abs(rect[3] - (CMEX_BASELINE + 1.0 * CMEX_SIZE)) < 1e-6)


def test_the_trigger_is_a_named_constant(monkeypatch):
    """A box 0.5 em below the baseline is ordinary -- until the trigger moves."""
    bbox, baseline, size = (10.0, 342.9, 14.0, 352.9), 347.9, 10.0
    assert D._sane_rect_marked(bbox, baseline, size)[1] is False
    monkeypatch.setattr(D, "EST_TRIGGER", -0.4)
    assert D._sane_rect_marked(bbox, baseline, size)[1] is True


def test_a_page_reports_its_estimated_boxes_through_the_field():
    """`_page_has_estimated_box` reads the field, not the geometry."""
    g_ok = D.GlyphNode(id="g1", page=1, rect=(0, 0, 1, 1), text="x", cid=1,
                       glyphname="x", fontname="F", family="roman", size=10.0,
                       tex=D.project("roman", "x", 1, "F"))
    g_est = D.GlyphNode(id="g2", page=1, rect=(0, 0, 1, 1), text="(", cid=2,
                        glyphname="parenleftbig", fontname="CMEX10",
                        family="math", size=10.0,
                        tex=D.project("math", "parenleftbig", 2, "CMEX10"),
                        rect_estimated=True)

    class _Line:
        def __init__(self, glyphs): self.glyphs = glyphs

    class _Page:
        def __init__(self, lines): self.lines = lines

    assert D._page_has_estimated_box(_Page([_Line([g_ok])])) is False
    assert D._page_has_estimated_box(_Page([_Line([g_ok, g_est])])) is True
