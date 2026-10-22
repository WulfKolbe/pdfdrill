"""
The GEOMETRY-ONLY lane, and the page's own furniture.

Two things that both come from the detector and cost nothing:

  * `gemma_reader.geometry_page` — a page's SHAPE with no words in it: the ink
    gives the rows, the detector gives each row its type, and a figure or a
    table is ONE object rather than the rows its strokes form. The keyless
    install's scan lane.
  * `gemma_reader.retype_furniture` — a running head or folio typed as
    `page_info` instead of `text`. FOUR conditions, and the conjunction is the
    whole of it: `markdown()` DROPS a `page_info` line, so a wrong retype
    deletes prose, and a deletion is not visible in the result. Measured with
    the band and the detector's word alone, 128 lines were retyped on penev_A
    and the score fell from 2,696 of 3,080 reference lines to 2,617 — 79 of
    them body text.
"""
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import gemma_reader as G, yololayout as Y
from pdfdrill.pagemd import Item
from pdfdrill.yololayout import Det


def _det(cls, box, model="layout"):
    return Det(model, cls, 0.9, box)


def _placed(kind, box):
    return G.Placed(Item(type=kind, text=""), box, "ink")


# --------------------------------------------------------------------------- #
#  typed_boxes — the detector's vocabulary mapped to MathPix's line types
# --------------------------------------------------------------------------- #

def test_each_mapped_class_becomes_its_line_type():
    dets = [_det("title", (0, 0, 10, 10)),
            _det("plain text", (0, 20, 10, 30)),
            _det("abandon", (0, 40, 10, 50)),
            _det("isolate_formula", (0, 60, 10, 70)),
            _det("formula_caption", (0, 80, 10, 90)),
            _det("figure", (0, 100, 10, 110)),
            _det("table", (0, 120, 10, 130))]
    got = [k for k, _b in Y.typed_boxes(dets)]
    assert got == ["title", "text", "page_info", "math", "equation_number",
                   "diagram", "table"]


def test_an_inline_formula_is_not_a_line_of_its_own():
    """`embedding` lives INSIDE a text line; a line for it would double the
    line it sits on."""
    assert Y.typed_boxes([_det("embedding", (0, 0, 10, 10), model="mfd")]) == []
    assert "embedding" not in Y.CLASS_TO_TYPE


def test_typed_boxes_come_back_top_to_bottom():
    dets = [_det("plain text", (0, 500, 10, 510)),
            _det("title", (0, 10, 10, 20))]
    assert [k for k, _ in Y.typed_boxes(dets)] == ["title", "text"]


def test_the_mfd_display_box_comes_in_only_where_the_layout_model_found_none():
    """Two boxes for one printed object guarantees one of them is wrong."""
    same = [_det("isolate_formula", (0, 0, 100, 50)),
            _det("isolated", (0, 0, 100, 50), model="mfd")]
    assert len(Y.typed_boxes(same)) == 1
    apart = [_det("isolate_formula", (0, 0, 100, 50)),
             _det("isolated", (0, 400, 100, 450), model="mfd")]
    assert len(Y.typed_boxes(apart)) == 2


# --------------------------------------------------------------------------- #
#  _type_for_row — an ink row's type is the class of the box it sits in
# --------------------------------------------------------------------------- #

def test_a_row_in_no_box_is_text():
    """…and SAYS the type was not measured. The second half of the answer is
    the line's provenance: `text` because the detector said so and `text`
    because nothing looked are different claims (finding I)."""
    assert G._type_for_row((0, 0, 10, 10), []) == ("text", False)


def test_a_row_takes_the_type_of_the_SMALLEST_box_containing_it():
    """An equation number sits inside the formula block as often as beside it,
    and the inner box is the one that names what the row actually is."""
    typed = [("math", (0, 0, 1000, 400)),
             ("equation_number", (900, 180, 990, 220))]
    assert G._type_for_row((910, 190, 980, 210), typed) == ("equation_number", True)
    assert G._type_for_row((100, 100, 300, 140), typed) == ("math", True)


def test_a_row_whose_centre_is_outside_every_box_is_text():
    typed = [("math", (0, 0, 100, 100))]
    assert G._type_for_row((500, 500, 600, 520), typed) == ("text", False)


# --------------------------------------------------------------------------- #
#  assemble_geometry — the document, and what it says about itself
# --------------------------------------------------------------------------- #

def test_the_document_says_it_was_not_read():
    doc = G.assemble_geometry([(1, None, [])])
    assert doc["source"].endswith("-geometry")
    assert doc["geometry_only"] is True
    assert "NOT READ" in doc["ocr"]["words"]
    assert "gemmaocr" in doc["ocr"]["words"]


def test_a_page_with_no_render_is_said_so_and_not_refused():
    doc = G.assemble_geometry([(3, None, [])])
    pg = doc["pages"][0]
    assert pg["page"] == 3 and pg["parse_status"] == "no_render"
    assert pg["lines"] == []


# --------------------------------------------------------------------------- #
#  retype_furniture — the four conditions
# --------------------------------------------------------------------------- #

PAGE_H, PAGE_W, LH = 1000, 1000, 40.0
HEAD = (100, 20, 300, 60)              # a short line in the top band
ABANDON = [(90, 15, 310, 65)]


def _retype(placed, boxes=None, **kw):
    opts = {"page_height": PAGE_H, "page_width": PAGE_W, "line_height": LH}
    opts.update(kw)
    return G.retype_furniture(placed, ABANDON if boxes is None else boxes,
                              **opts)


def test_a_short_line_in_the_top_band_inside_an_abandon_box_is_furniture():
    p = [_placed("text", HEAD)]
    assert _retype(p) == 1
    assert p[0].item.type == "page_info"


def test_a_short_line_in_the_BOTTOM_band_is_furniture_too():
    box = (100, 940, 300, 980)
    p = [_placed("text", box)]
    assert _retype(p, [(90, 935, 310, 985)]) == 1
    assert p[0].item.type == "page_info"


def test_a_line_in_the_middle_of_the_page_is_never_furniture():
    box = (100, 480, 300, 520)
    p = [_placed("text", box)]
    assert _retype(p, [(90, 475, 310, 525)]) == 0
    assert p[0].item.type == "text"


def test_a_FULL_MEASURE_line_in_the_band_is_body_text():
    """The condition that cost 79 lines of prose when it was missing: the top
    twelfth of a scanned page holds the first body line as often as a head."""
    box = (50, 20, 950, 60)
    p = [_placed("text", box)]
    assert _retype(p, [(40, 15, 960, 65)]) == 0
    assert p[0].item.type == "text"


def test_an_abandon_box_drawn_over_a_BLOCK_is_the_detector_mislabelling():
    box = (100, 20, 300, 60)
    p = [_placed("text", box)]
    tall = [(90, 15, 310, 400)]            # ten line-heights tall
    assert _retype(p, tall) == 0
    assert p[0].item.type == "text"


def test_a_line_with_no_abandon_box_over_it_is_left_alone():
    p = [_placed("text", HEAD)]
    assert _retype(p, [(600, 20, 800, 60)]) == 0
    assert p[0].item.type == "text"


def test_only_a_text_line_is_ever_retyped():
    """A math line, a caption or a container in the margin keeps its type —
    the reading named it and the detector's class does not outrank that."""
    for kind in ("math", "equation_number", "figure_label", "diagram",
                 "title", "page_info"):
        p = [_placed(kind, HEAD)]
        assert _retype(p) == 0, kind
        assert p[0].item.type == kind


def test_a_line_with_no_box_is_skipped():
    p = [_placed("text", None)]
    assert _retype(p) == 0


def test_no_detector_boxes_means_no_retyping():
    p = [_placed("text", HEAD)]
    assert G.retype_furniture(p, [], page_height=PAGE_H) == 0


def test_the_four_thresholds_are_named_constants():
    """Each was measured; a reader must be able to find the number."""
    assert 0 < G.FURNITURE_BAND < 0.5
    assert 0 < G.FURNITURE_WIDTH < 1.0
    assert G.FURNITURE_LINES > 1.0
    assert 0 < G.FURNITURE_SHARE <= 1.0


# ---- the lane without the detector: boxes, no types -----------------------

def test_route_calls_the_inkonly_geometry_lane_free(monkeypatch):
    """MEASURED after the first version of this branch said "there is no free
    lane on this install" and `drill` produced 355 boxed lines on hilbert10 in
    6.6 s anyway. The ink finds the lines with nothing but NumPy; the detector
    types them. A weaker lane is not an absent one."""
    from pdfdrill import ocr_router as R
    monkeypatch.setattr(R, "ink_available", lambda: True)
    d = R.choose_route(text_layer=False, needs_ocr=True, page_count=10,
                       scanned_images=10, arxiv_source=None, keys=set(),
                       detector=False)
    assert d.lane == "geometry" and d.cost == "free"
    assert "NO type" in d.reason or "no type" in d.reason.lower()
    assert "PDFDRILL_YOLO_PYTHON" in d.reason
    assert "--geometry-only" in d.command


def test_no_detector_and_no_numpy_is_the_only_lane_that_costs_none(monkeypatch):
    from pdfdrill import ocr_router as R
    monkeypatch.setattr(R, "ink_available", lambda: False)
    d = R.choose_route(text_layer=False, needs_ocr=True, page_count=10,
                       scanned_images=10, arxiv_source=None, keys=set(),
                       detector=False)
    assert d.lane == "geometry" and d.cost == "none"
    assert "numpy" in d.command.lower()


def test_the_typed_lane_is_still_the_one_with_a_detector(monkeypatch):
    from pdfdrill import ocr_router as R
    d = R.choose_route(text_layer=False, needs_ocr=True, page_count=10,
                       scanned_images=10, arxiv_source=None, keys=set(),
                       detector=True)
    assert d.lane == "geometry" and d.cost == "free"
    assert "a box and a type" in d.reason


# --------------------------------------------------------------------------- #
#  PROVENANCE — `geometry` says HOW the box was arrived at, and it lied.
#
#  Found by an auditing session (finding I): every line of a geometry-only
#  lines.json carried `"geometry": "ink-yolo"`, including on the untyped half
#  of the lane where no detector runs at all. The field is read to decide
#  whether a box can be trusted as a Formula's extent or is only the ink under
#  a row — so claiming the detector where none looked makes the weaker half of
#  the lane indistinguishable from the stronger one.
# --------------------------------------------------------------------------- #

def _inked_page(tmp_path, bars):
    """A white page with black bars, as a PNG the ink half can read."""
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw
    img = Image.new("L", (400, 300), 255)
    d = ImageDraw.Draw(img)
    for x0, y0, x1, y1 in bars:
        d.rectangle((x0, y0, x1, y1), fill=0)
    out = tmp_path / "page-0001.png"
    img.save(out)
    return out


BARS = [(60, 80, 340, 100), (60, 180, 340, 200)]


def test_with_no_detector_every_line_says_ink_and_only_ink(tmp_path):
    png = _inked_page(tmp_path, BARS)
    doc = G.assemble_geometry([(1, png, [])])
    kinds = {ln["geometry"] for ln in doc["pages"][0]["lines"]}
    assert kinds, "the ink found no rows at all — the fixture is wrong"
    assert kinds == {"ink"}, (
        f"a line claims the detector on a page no detector saw: {kinds}")
    assert all(ln["type"] == "text" for ln in doc["pages"][0]["lines"])


def test_the_document_head_says_the_types_are_not_measured(tmp_path):
    png = _inked_page(tmp_path, BARS)
    doc = G.assemble_geometry([(1, png, [])])
    assert "NONE" in doc["ocr"]["types"], doc["ocr"]["types"]
    assert doc["ocr"]["geometry_kinds"] == ["ink"]
    assert "a box and a type" not in doc["ocr"]["words"], (
        "the head still promises a type on every line")


def test_a_row_the_detector_typed_says_ink_yolo(tmp_path):
    png = _inked_page(tmp_path, BARS)
    dets = [_det("isolate_formula", (50, 170, 350, 210))]
    doc = G.assemble_geometry([(1, png, dets)], detector="a test detector")
    lines = doc["pages"][0]["lines"]
    kinds = {ln["geometry"] for ln in lines}
    assert "ink-yolo" in kinds, (
        f"the detector typed a row and the provenance does not say so: {kinds}")
    assert "ink" in kinds, (
        f"the row OUTSIDE the detector box must still say plain ink: {kinds}")
    assert "from the layout detector" in doc["ocr"]["types"]


def test_the_source_names_the_half_that_actually_ran(tmp_path):
    """Finding I, second half: `source` said `yolo-geometry` on a run whose own
    lane line reported no layout detector. The field names the READER."""
    png = _inked_page(tmp_path, BARS)
    untyped = G.assemble_geometry([(1, png, [])])
    assert untyped["source"] == "ink-geometry", (
        f"no detector ran and source says {untyped['source']!r}")
    typed = G.assemble_geometry(
        [(1, png, [_det("isolate_formula", (50, 170, 350, 210))])],
        detector="a test detector")
    assert typed["source"] == "yolo-geometry", (
        f"the detector typed a row and source says {typed['source']!r}")
