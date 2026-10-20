"""
`layoutgeom` — the OCR path used for nothing but geometry.

The detector's boxes put on a model built from something else, by a MONOTONE
WALK between the objects a text match did place. The rules under test, each
from a measurement on arXiv 2402.13444v1:

  * a box may only be taken inside the window its neighbours leave, and the
    window runs from the previous anchor's TOP to the next anchor's BOTTOM
    (with tops alone, 23 of 26 candidates found nothing — an inline formula
    sits INSIDE its host paragraph);
  * each box is taken once;
  * a type with no detector class is never given a box;
  * where the window holds no box of the right class, the object keeps NONE —
    a wrong box cannot be detected downstream;
  * a Reference the bibliography made from a `\\cite` key has nothing to box
    and is not a missing measurement.
"""
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import DocObject, Document
from pdfdrill import layoutgeom as L
from pdfdrill.yololayout import Det


# --------------------------------------------------------------------------- #
#  Fixtures
# --------------------------------------------------------------------------- #

def _doc(objs):
    d = Document(meta={"bibkey": "T"})
    for o in objs:
        d.add(o)
    return d


def _page(n, w=600.0, h=800.0):
    return DocObject(type="Page", props={"page_number": n, "page_width": w,
                                         "page_height": h})


def _obj(kind, flow, *, region=None, page=None, **props):
    p = {"flow_index": flow, **props}
    if region:
        x, y, w, h = region
        p["region"] = {"top_left_x": x, "top_left_y": y, "width": w,
                       "height": h}
        p["page"] = page
    return DocObject(type=kind, props=p)


def _det(cls, box, model="layout"):
    return Det(model, cls, 0.9, box)


# the render is 1200x1600 px for a 600x800 pt page: scale 0.5
PX = {1: (1200, 1600)}


# --------------------------------------------------------------------------- #
#  The walk
# --------------------------------------------------------------------------- #

def test_an_unboxed_formula_takes_the_inline_box_between_its_anchors():
    doc = _doc([
        _page(1),
        _obj("Paragraph", 1, region=(50, 100, 500, 80), page=1, text="a"),
        _obj("Formula", 2, display=False, latex="x^2"),
        _obj("Paragraph", 3, region=(50, 300, 500, 60), page=1, text="b"),
    ])
    dets = [_det("embedding", (200, 300, 300, 320), model="mfd")]
    stats = L.place(doc, {1: dets}, PX)
    assert stats["boxed"] == 1 and stats["by_type"] == {"Formula": 1}
    f = next(o for o in doc.objects.values() if o.type == "Formula")
    # scaled from px to pt: 200*0.5 = 100
    assert f.props["region"]["top_left_x"] == 100.0
    assert f.props["page"] == 1
    assert f.props["region_via"] == "yolo"


def test_the_window_runs_to_the_next_anchors_BOTTOM():
    """An inline formula sits inside its host paragraph, so its box is BELOW
    the next anchor's top. A window built from tops alone excludes it — which
    is how 23 of 26 candidates found nothing."""
    doc = _doc([
        _page(1),
        _obj("Paragraph", 1, region=(50, 100, 500, 20), page=1, text="a"),
        _obj("Formula", 2, display=False, latex="x"),
        # the next anchor STARTS at y=200 and is 200pt tall
        _obj("Paragraph", 3, region=(50, 200, 500, 200), page=1, text="b"),
    ])
    dets = [_det("embedding", (200, 700, 300, 720), model="mfd")]  # y=350pt
    assert L.place(doc, {1: dets}, PX)["boxed"] == 1


def test_a_box_outside_the_window_is_refused():
    doc = _doc([
        _page(1),
        _obj("Paragraph", 1, region=(50, 100, 500, 20), page=1, text="a"),
        _obj("Formula", 2, display=False, latex="x"),
        _obj("Paragraph", 3, region=(50, 150, 500, 20), page=1, text="b"),
    ])
    # the only inline box is at y=600pt, far below the next anchor's bottom
    dets = [_det("embedding", (200, 1200, 300, 1220), model="mfd")]
    stats = L.place(doc, {1: dets}, PX)
    assert stats["boxed"] == 0 and stats["no_box"] == 1
    f = next(o for o in doc.objects.values() if o.type == "Formula")
    assert "region" not in f.props          # no box is better than a wrong one


def test_each_box_is_taken_once():
    doc = _doc([
        _page(1),
        _obj("Paragraph", 1, region=(50, 50, 500, 20), page=1, text="a"),
        _obj("Formula", 2, display=False, latex="x"),
        _obj("Formula", 3, display=False, latex="y"),
        _obj("Paragraph", 4, region=(50, 600, 500, 20), page=1, text="b"),
    ])
    dets = [_det("embedding", (100, 200, 200, 220), model="mfd"),
            _det("embedding", (300, 400, 400, 420), model="mfd")]
    stats = L.place(doc, {1: dets}, PX)
    assert stats["boxed"] == 2
    got = sorted(o.props["region"]["top_left_x"]
                 for o in doc.objects.values()
                 if o.type == "Formula")
    assert got == [50.0, 150.0]             # two different boxes


def test_more_objects_than_boxes_leaves_the_extra_ones_unboxed():
    doc = _doc([
        _page(1),
        _obj("Paragraph", 1, region=(50, 50, 500, 20), page=1, text="a"),
        _obj("Formula", 2, display=False, latex="x"),
        _obj("Formula", 3, display=False, latex="y"),
        _obj("Paragraph", 4, region=(50, 600, 500, 20), page=1, text="b"),
    ])
    dets = [_det("embedding", (100, 200, 200, 220), model="mfd")]
    stats = L.place(doc, {1: dets}, PX)
    assert stats["boxed"] == 1 and stats["no_box"] == 1


def test_an_object_that_already_has_a_region_is_left_alone():
    doc = _doc([
        _page(1),
        _obj("Formula", 1, region=(10, 20, 30, 40), page=1, display=False),
    ])
    dets = [_det("embedding", (900, 900, 950, 950), model="mfd")]
    stats = L.place(doc, {1: dets}, PX)
    assert stats["boxed"] == 0 and stats["candidates"] == 0
    f = next(o for o in doc.objects.values() if o.type == "Formula")
    assert f.props["region"]["top_left_x"] == 10


def test_a_type_with_no_detector_class_is_never_given_a_box():
    """A Paragraph's box comes from the ink rows of its block, which answer
    better than any detector class; a Citation is an inline marker."""
    assert L._family(_obj("Paragraph", 1, text="x")) is None
    assert L._family(_obj("Citation", 1)) is None
    assert L._family(_obj("Reference", 1)) is None


def test_a_formula_chooses_its_family_by_its_display_flag():
    assert L._family(_obj("Formula", 1, display=True)) == "display"
    assert L._family(_obj("Formula", 1, display=False)) == "inline"
    assert L._family(_obj("Equation", 1)) == "display"


def test_an_object_with_no_anchor_at_all_is_reported_not_guessed():
    doc = _doc([_page(1), _obj("Formula", 1, display=False, latex="x")])
    dets = [_det("embedding", (100, 200, 200, 220), model="mfd")]
    stats = L.place(doc, {1: dets}, PX)
    assert stats["no_window"] == 1 and stats["boxed"] == 0


def test_a_page_with_no_render_size_contributes_no_boxes():
    """Without the render's pixel size there is no scale, and a detection in
    pixels written into a model in points is off by a factor of five."""
    doc = _doc([
        _page(1),
        _obj("Paragraph", 1, region=(50, 50, 500, 20), page=1, text="a"),
        _obj("Formula", 2, display=False, latex="x"),
    ])
    dets = [_det("embedding", (100, 200, 200, 220), model="mfd")]
    assert L.place(doc, {1: dets}, {})["boxed"] == 0


def test_boxes_are_scaled_from_the_render_to_the_models_own_units():
    doc = _doc([
        _page(1, w=600.0, h=800.0),
        _obj("Paragraph", 1, region=(0, 0, 10, 10), page=1, text="a"),
        _obj("Table", 2),
    ])
    dets = [_det("table", (400, 800, 800, 1200))]
    L.place(doc, {1: dets}, {1: (1200, 1600)})
    r = next(o for o in doc.objects.values() if o.type == "Table").props["region"]
    assert (r["top_left_x"], r["top_left_y"], r["width"], r["height"]) == \
        (200.0, 400.0, 200.0, 200.0)


# --------------------------------------------------------------------------- #
#  families — which detector class answers for which object
# --------------------------------------------------------------------------- #

def test_a_table_takes_a_table_box_and_a_figure_takes_a_figure_box():
    dets = [_det("table", (0, 0, 10, 10)), _det("figure", (0, 20, 10, 30))]
    fam = L.families(dets)
    assert fam["table"] == [(0, 0, 10, 10)]
    assert fam["figure"] == [(0, 20, 10, 30)]


def test_families_covers_every_family_the_map_names():
    fam = L.families([])
    assert set(fam) >= set(L.FAMILY.values()) - {"formula"}
    assert "inline" in fam and "display" in fam


# --------------------------------------------------------------------------- #
#  not_printed — an object with nothing to box
# --------------------------------------------------------------------------- #

def test_a_citation_and_a_stub_reference_have_nothing_to_box():
    assert L.not_printed("Citation", {}) is True
    assert L.not_printed("Reference", {"stub": True}) is True


def test_a_real_bibliography_entry_IS_printed():
    """27 of the 34 box-less elements on 2402.13444v1 were stubs; once the
    author's .bbl is read they are entries that ARE on pages 8 and 9, and a
    missing box for one of those is a real missing box."""
    assert L.not_printed("Reference", {"raw_text": "Caragea et al. 2014"}) is False
    assert L.not_printed("Paragraph", {"text": "x"}) is False


# --------------------------------------------------------------------------- #
#  png_size — the one number that makes a detection placeable
# --------------------------------------------------------------------------- #

def _png(path, w, h):
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IEND", b""))


def test_png_size_reads_the_header(tmp_path):
    p = tmp_path / "page-0001.png"
    _png(p, 1234, 5678)
    assert L.png_size(p) == (1234, 5678)


def test_png_size_of_a_missing_or_wrong_file_is_none(tmp_path):
    assert L.png_size(tmp_path / "nope.png") is None
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not a png at all")
    assert L.png_size(bad) is None
