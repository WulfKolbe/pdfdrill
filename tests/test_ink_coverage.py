r"""Phase 1 — the coverage audit: what MathPix did not report, and where.

MathPix reports what it found; ink reports what is there. This classifies every
ink component against the MathPix regions already in the model, and the
residual IS the deliverable — on 2409.18839 p8 the 1.03% "ink with no region"
is every table rule on the page plus the footnote separator. MathPix describes
the table's logical structure and omits the ink that draws it, which is a
design boundary rather than a bug; but `\toprule/\midrule`, a full `\hline`
grid, and no rules at all are three different documents.

pdfdrill CONSUMES inkdrill's `lines.json`; it does not import inkdrill. The
classification contract is inkdrill's (coverage.py G1-G7) and is restated here
as pdfdrill behaviour, because a re-implementation that quietly drifted from it
would make a disagreement between the two tools unreadable.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.ink_coverage import (  # noqa: E402
    EMPTY_REGION,
    INSIDE,
    MISSED,
    OVERLAPPING,
    STRADDLE,
    classify,
    ink_boxes,
    mathpix_regions_pt,
    rect_of,
)


def _reg(x0, y0, x1, y1):
    return {"top_left_x": x0, "top_left_y": y0,
            "width": x1 - x0, "height": y1 - y0}


# ------------------------------------------------------------------ geometry
def test_rect_of_reads_a_mathpix_region_as_edges_not_extents():
    assert rect_of(_reg(10, 20, 30, 50)) == (10.0, 20.0, 30.0, 50.0)


def test_mathpix_regions_are_converted_with_the_declared_page_size_not_a_guess():
    r"""inkdrill's `ocr.units` says `pt`, derived from the PNG's `pHYs`;
    MathPix emits its own pixel space. Deriving the scale from a nominal page
    size instead costs 0.071 pt — the size of the residuals being measured."""
    got = mathpix_regions_pt([_reg(1000, 1500, 1200, 1600)],
                             page_px=(2000, 3000), page_pt=(500.0, 750.0))
    assert got[0][1] == (250.0, 375.0, 300.0, 400.0)


# ------------------------------------------------------------------ classes
def test_a_tall_blob_whose_centre_is_inside_still_straddles_the_edge():
    """Containment, NOT centres — the inversion is the point.

    This is the case that clips the limits off a tall sum: the region was
    fitted to the body of the line and the glyph extends above and below it.
    Centres would call that comfortably inside and report nothing.
    """
    regions = [(0, (10.0, 100.0, 90.0, 110.0))]
    tall = (1, (40.0, 90.0, 50.0, 120.0), 300)      # centre inside, ends out
    rep = classify([tall], regions)
    assert rep["members"][STRADDLE] == [1]
    assert rep["members"][INSIDE] == []


def test_every_box_lands_in_exactly_one_class():
    regions = [(0, (0.0, 0.0, 10.0, 10.0)), (1, (5.0, 5.0, 20.0, 20.0))]
    boxes = [(1, (1.0, 1.0, 2.0, 2.0), 4),         # inside region 0 only
             (2, (6.0, 6.0, 7.0, 7.0), 4),         # inside both -> overlapping
             (3, (50.0, 50.0, 51.0, 51.0), 4),     # no region -> missed
             (4, (9.0, 9.0, 12.0, 12.0), 16)]      # crosses region 0's edge
    rep = classify(boxes, regions)
    seen = [b for k in (INSIDE, MISSED, STRADDLE, OVERLAPPING)
            for b in rep["members"][k]]
    assert sorted(seen) == [1, 2, 3, 4]
    assert len(seen) == len(set(seen))
    assert rep["members"][OVERLAPPING] == [2]
    assert rep["members"][MISSED] == [3]


def test_a_region_with_no_ink_is_reported_rather_than_measured_at_zero():
    """Rare but not zero — 0.00% on a six-page sample, 0.03% on the next.
    Reading the first as "this tool never hallucinates a region" was a
    small-sample artefact."""
    regions = [(0, (0.0, 0.0, 10.0, 10.0)), (7, (200.0, 200.0, 210.0, 210.0))]
    rep = classify([(1, (1.0, 1.0, 2.0, 2.0), 4)], regions)
    assert rep["members"][EMPTY_REGION] == [7]


def test_classification_does_not_depend_on_input_order():
    regions = [(0, (0.0, 0.0, 10.0, 10.0)), (1, (5.0, 5.0, 20.0, 20.0))]
    boxes = [(1, (1.0, 1.0, 2.0, 2.0), 4), (2, (6.0, 6.0, 7.0, 7.0), 4),
             (3, (50.0, 50.0, 51.0, 51.0), 4)]
    assert classify(boxes, regions) == classify(list(reversed(boxes)),
                                                list(reversed(regions)))


def test_an_empty_page_reports_zeros_and_does_not_divide_by_zero():
    rep = classify([], [])
    assert rep["boxes"] == 0 and rep["regions"] == 0
    assert rep["fractions"][MISSED] == 0.0


def test_the_size_filter_is_visible_rather_than_inferred():
    """A 1-px speck reported as missed content is noise the caller has to
    filter anyway — but a filter that silently shrinks the denominator is how
    a coverage number improves without the page changing."""
    boxes = [(1, (0.0, 0.0, 1.0, 1.0), 1), (2, (50.0, 50.0, 60.0, 60.0), 100)]
    rep = classify(boxes, [], min_area=10)
    assert rep["boxes"] == 1 and rep["dropped"] == 1


# ------------------------------------------------------------------ ingest
def test_ink_boxes_reads_glyph_lines_of_one_page_and_carries_the_ink_area():
    ink = {"source": "inkdrill", "ocr": {"units": "pt", "render_dpi": 400.0},
           "pages": [{"page": 8, "page_width": 612.0, "page_height": 792.0,
                      "lines": [
                          {"type": "glyph", "region": _reg(10, 20, 30, 50),
                           "ink": {"region_id": 3, "area": 44, "holes": 0}},
                          {"type": "glyph", "region": _reg(0, 0, 2, 2),
                           "ink": {"region_id": 4, "area": 3, "holes": 0}},
                      ]}]}
    got = ink_boxes(ink, page=8)
    assert got == [(3, (10.0, 20.0, 30.0, 50.0), 44),
                   (4, (0.0, 0.0, 2.0, 2.0), 3)]


def test_ink_boxes_refuses_a_file_that_does_not_declare_points():
    """The units travel with the data or the call fails. A pixel-space file
    read as points is a scale error that looks like a coverage finding."""
    ink = {"ocr": {"units": "px"}, "pages": [{"page": 1, "lines": []}]}
    try:
        ink_boxes(ink, page=1)
    except ValueError as exc:
        assert "units" in str(exc)
    else:
        raise AssertionError("a px-space file was read as points")
