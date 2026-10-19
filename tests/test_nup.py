r"""A scanned sheet is not always a printed page.

`penev_A` is a thesis photographed four printed pages to a sheet. The lane
assumed one, and that assumption — not the document, and not any threshold —
cost it 85% of its boxes and 18 points of reading order. These tests hold the
two halves of the fix: that the detector finds the imposition when it is there
and refuses to invent one when it is not, and that a reading of the printed
pages comes back to the sheet coordinates every consumer downstream requires.

The numbers in the docstrings are measured on penev_A's 22 sheets at 400 dpi
and on three 1-up documents' pages at the same dpi.
"""
from __future__ import annotations

import json

import pytest

from pdfdrill import nup

np = pytest.importorskip("numpy")


# --------------------------------------------------------------------------- #
#  Synthetic sheets. White is 255, ink is 0, as a page render is.
# --------------------------------------------------------------------------- #

def blank(w: int = 400, h: int = 600):
    return np.full((h, w), 255, dtype="uint8")


def text_block(img, x0: int, y0: int, x1: int, y1: int, *,
               pitch: int = 10, thick: int = 4) -> None:
    """Rows of ink, like printed lines: ink on `thick` rows of every `pitch`."""
    for y in range(y0, y1, pitch):
        img[y:min(y + thick, y1), x0:x1] = 0


def one_up(w: int = 400, h: int = 600):
    """A single printed page with a paragraph gap across the middle — the
    shape that the band-gutter rule must NOT cut in half."""
    img = blank(w, h)
    text_block(img, 40, 40, w - 40, h // 2 - 30)
    text_block(img, 40, h // 2 + 30, w - 40, h - 40)
    return img


def two_by_two(w: int = 400, h: int = 600, gx: int = 196, gy: int = 302):
    img = blank(w, h)
    for x0, x1 in ((20, gx - 20), (gx + 20, w - 20)):
        for y0, y1 in ((20, gy - 20), (gy + 20, h - 20)):
            text_block(img, x0, y0, x1, y1)
    return img


# --------------------------------------------------------------------------- #
#  Finding the gutter
# --------------------------------------------------------------------------- #

def test_a_one_up_page_with_a_paragraph_gap_is_not_cut_in_half():
    """THE false positive that matters. Measured with the band gutter sought
    unconditionally: all three of killing20's probe sheets, two of collatz14's
    and one of hilbert10's were cut through their own text. A horizontal blank
    band in the middle of a page is ORDINARY — a paragraph break, the space
    above a display — while a vertical one is not, because printed text runs
    across the full measure. Hence a band gutter only inside a column."""
    sheet = nup.detect(one_up())
    assert sheet.kind == "1-up"
    assert sheet.n == 1
    assert sheet.gutter_x is None


def test_a_two_by_two_sheet_is_found_and_ordered_down_each_column():
    sheet = nup.detect(two_by_two())
    assert sheet.kind == "2x2"
    assert sheet.n == 4
    assert sheet.gutter_x == pytest.approx(196, abs=12)
    # column order: top-left, bottom-left, top-right, bottom-right. This is
    # the duplex imposition -- penev_A sheet 10 holds pp. 27, 28, 29, 30 in
    # exactly that order.
    xs = [b[0] for b in sheet.pages]
    ys = [b[1] for b in sheet.pages]
    assert xs[0] == xs[1] < xs[2] == xs[3]
    assert ys[0] < ys[1] and ys[2] < ys[3]


def test_row_order_finishes_a_band_before_moving_down():
    sheet = nup.detect(two_by_two(), order="row")
    xs = [b[0] for b in sheet.pages]
    ys = [b[1] for b in sheet.pages]
    assert xs[0] < xs[1] and xs[2] < xs[3]
    assert ys[0] == ys[1] < ys[2] == ys[3]


def test_the_pages_tile_the_sheet_with_no_gap_and_no_overlap():
    """A printed page that is not inside the sheet is a page whose lines come
    back to the wrong place after `merge`."""
    w, h = 400, 600
    sheet = nup.detect(two_by_two(w, h))
    assert sum((b[2] - b[0]) * (b[3] - b[1]) for b in sheet.pages) == w * h
    for a in range(len(sheet.pages)):
        for b in range(a + 1, len(sheet.pages)):
            p, q = sheet.pages[a], sheet.pages[b]
            ix = max(0, min(p[2], q[2]) - max(p[0], q[0]))
            iy = max(0, min(p[3], q[3]) - max(p[1], q[1]))
            assert ix * iy == 0, (p, q)


def test_a_wide_margin_near_the_middle_is_not_a_gutter():
    """SIDE_INK. A sheet whose right half is blank — a plate's verso, the last
    page of a chapter — has a blank run at the middle and one printed page."""
    img = blank()
    text_block(img, 30, 30, 150, 560)
    assert nup.detect(img).kind == "1-up"


def test_the_gutter_nearest_the_middle_wins_not_the_widest():
    """The detail the whole detector rests on. A sparse printed page has a
    blank run inside it wider than the gutter; taking the widest run puts the
    cut through the middle of a page's text."""
    prof = np.full(100, 0.5)
    prof[10:40] = 0.0          # a wide blank INSIDE the left page
    prof[48:54] = 0.0          # the real gutter, narrower, at the middle
    assert nup.middle_blank(prof, 0, 100, 4) == 51


def test_no_blank_run_means_no_gutter_rather_than_the_middle():
    """It returns None, so the caller can say 1-up. An earlier shape returned
    the profile's midpoint as a fallback, which cuts every page in half."""
    assert nup.middle_blank(np.full(100, 0.5), 0, 100, 4) is None


# --------------------------------------------------------------------------- #
#  The document's shape
# --------------------------------------------------------------------------- #

def test_the_shape_is_decided_for_the_document_and_not_per_sheet():
    """MEASURED on penev_A: the per-sheet detector reads 19 of 22 sheets as
    2x2 and three as 2-up or 3-up — sheet 1 (a dedication, a blank verso, a
    copyright notice and folio `iii`), sheet 3 and sheet 16. All three carry
    four printed pages; what they lack is enough ink on one of the four to
    prove the gutter. Trusting each sheet gives 84 printed pages where there
    are 88, and merges four pages into a neighbour on exactly the sheets that
    are hardest to read."""
    sparse = two_by_two()
    sparse[320:580, :] = 255           # the bottom two pages nearly blank
    grays = [two_by_two(), two_by_two(), sparse]
    shp = nup.shape(grays)
    assert (shp.columns, shp.bands) == (2, 2)
    assert shp.votes == 2 and shp.sheets == 3
    # and the sparse sheet is still cut into four, using the document median
    assert nup.pages_for(sparse, shp).n == 4
    assert sum(nup.pages_for(g, shp).n for g in grays) == 12


def test_a_sheet_uses_its_own_gutter_when_it_has_one():
    """The shape fixes HOW MANY cuts; a sheet that can say where places them
    itself, because a scan's sheets differ by a few per cent."""
    shifted = two_by_two(gx=170, gy=250)
    shp = nup.shape([two_by_two(), two_by_two(), shifted])
    got = nup.pages_for(shifted, shp)
    assert got.gutter_x == pytest.approx(170, abs=12)


def test_a_one_up_document_is_one_up_unanimously():
    shp = nup.shape([one_up(), one_up(), one_up()])
    assert shp.kind == "1-up" and shp.n == 1
    assert nup.pages_for(one_up(), shp).n == 1


def test_no_sheets_is_one_up_and_not_a_crash():
    assert nup.shape([]).n == 1


# --------------------------------------------------------------------------- #
#  Forcing it
# --------------------------------------------------------------------------- #

def test_parse_shape_covers_auto_one_and_columns_by_bands():
    assert nup.parse_shape("auto") is None
    assert nup.parse_shape("") is None
    assert nup.parse_shape("1").n == 1
    assert (nup.parse_shape("2x2").columns, nup.parse_shape("2x2").bands) == (2, 2)
    # stacked with no vertical gutter: the one imposition detection refuses to
    # guess, so it has to be sayable
    assert nup.parse_shape("1x2").n == 2


@pytest.mark.parametrize("bad", ["2", "2x", "x2", "two", "0x2", "5x5"])
def test_parse_shape_refuses_what_it_cannot_mean(bad):
    with pytest.raises(ValueError):
        nup.parse_shape(bad)


def test_a_forced_stacked_shape_cuts_a_one_up_page_in_two():
    shp = nup.parse_shape("1x2")
    got = nup.pages_for(one_up(), shp)
    assert got.n == 2
    assert got.pages[0][1] == 0 and got.pages[1][3] == 600


# --------------------------------------------------------------------------- #
#  The map back to the sheet
# --------------------------------------------------------------------------- #

def _doc(pages):
    return {"source": "gemma4-ink-yolo", "pages": pages}


def _line(x, y, w, h, **kw):
    out = {"type": "text", "text": "t", "line": 1,
           "region": {"top_left_x": x, "top_left_y": y, "width": w, "height": h}}
    out.update(kw)
    return out


def test_merge_puts_every_printed_page_back_on_its_sheet():
    amap = {"1": {"sheet": 1, "box": [0, 0, 200, 300], "sheet_size": [400, 600],
                  "kind": "2x2"},
            "2": {"sheet": 1, "box": [0, 300, 200, 600],
                  "sheet_size": [400, 600], "kind": "2x2"},
            "3": {"sheet": 1, "box": [200, 0, 400, 300],
                  "sheet_size": [400, 600], "kind": "2x2"},
            "4": {"sheet": 1, "box": [200, 300, 400, 600],
                  "sheet_size": [400, 600], "kind": "2x2"}}
    doc = _doc([{"page": n, "page_width": 200, "page_height": 300,
                 "lines": [_line(10, 20, 100, 12)]} for n in (1, 2, 3, 4)])
    out = nup.merge(doc, amap)
    assert len(out["pages"]) == 1
    page = out["pages"][0]
    assert page["page"] == 1
    assert (page["page_width"], page["page_height"]) == (400, 600)
    assert len(page["lines"]) == 4
    # the four pages' identical line lands in the four quadrants
    got = [(l["region"]["top_left_x"], l["region"]["top_left_y"])
           for l in page["lines"]]
    assert got == [(10, 20), (10, 320), (210, 20), (210, 320)]
    # every line says which printed page it came from, and is renumbered over
    # the sheet in reading order
    assert [l["nup_page"] for l in page["lines"]] == [1, 2, 3, 4]
    assert [l["line"] for l in page["lines"]] == [1, 2, 3, 4]


def test_merge_scales_a_page_read_at_another_size():
    """The printed page may have been read at a different resolution from the
    crop; the box still has to land on the sheet."""
    amap = {"1": {"sheet": 7, "box": [0, 0, 200, 300],
                  "sheet_size": [400, 600], "kind": "2x2"}}
    doc = _doc([{"page": 1, "page_width": 100, "page_height": 150,
                 "lines": [_line(10, 20, 50, 6)]}])
    reg = nup.merge(doc, amap)["pages"][0]["lines"][0]["region"]
    assert (reg["top_left_x"], reg["top_left_y"]) == (20, 40)
    assert (reg["width"], reg["height"]) == (100, 12)


def test_merge_keeps_cnt_in_step_with_the_region():
    """MathPix's four-point polygon is the same box said twice; a consumer
    reading one and not the other gets a stale answer."""
    amap = {"1": {"sheet": 1, "box": [100, 50, 300, 350],
                  "sheet_size": [400, 600], "kind": "2x2"}}
    doc = _doc([{"page": 1, "page_width": 200, "page_height": 300,
                 "lines": [_line(10, 20, 40, 10,
                                 cnt=[[10, 20], [50, 20], [50, 30], [10, 30]])]}])
    line = nup.merge(doc, amap)["pages"][0]["lines"][0]
    r = line["region"]
    assert line["cnt"] == [[r["top_left_x"], r["top_left_y"]],
                           [r["top_left_x"] + r["width"], r["top_left_y"]],
                           [r["top_left_x"] + r["width"],
                            r["top_left_y"] + r["height"]],
                           [r["top_left_x"], r["top_left_y"] + r["height"]]]


def test_merge_leaves_an_empty_region_empty():
    """A line the alignment never placed must not be moved onto the sheet's
    top-left corner, where it would look like a real box."""
    amap = {"1": {"sheet": 1, "box": [100, 50, 300, 350],
                  "sheet_size": [400, 600], "kind": "2x2"}}
    doc = _doc([{"page": 1, "page_width": 200, "page_height": 300,
                 "lines": [_line(0, 0, 0, 0)]}])
    reg = nup.merge(doc, amap)["pages"][0]["lines"][0]["region"]
    assert (reg["top_left_x"], reg["top_left_y"], reg["width"],
            reg["height"]) == (0, 0, 0, 0)


def test_merge_moves_math_regions_too():
    amap = {"1": {"sheet": 1, "box": [0, 100, 200, 400],
                  "sheet_size": [400, 600], "kind": "2x2"}}
    doc = _doc([{"page": 1, "page_width": 200, "page_height": 300,
                 "lines": [_line(10, 20, 40, 10, math_regions=[
                     {"top_left_x": 12, "top_left_y": 21,
                      "width": 8, "height": 8}])]}])
    mr = nup.merge(doc, amap)["pages"][0]["lines"][0]["math_regions"][0]
    assert (mr["top_left_x"], mr["top_left_y"]) == (12, 121)


def test_is_identity_is_true_only_when_every_sheet_holds_one_page():
    one = {"1": {"sheet": 1, "box": [0, 0, 4, 6], "sheet_size": [4, 6],
                 "kind": "1-up"},
           "2": {"sheet": 2, "box": [0, 0, 4, 6], "sheet_size": [4, 6],
                 "kind": "1-up"}}
    assert nup.is_identity(one)
    two = dict(one)
    two["3"] = {"sheet": 2, "box": [0, 0, 4, 3], "sheet_size": [4, 6],
                "kind": "1x2"}
    assert not nup.is_identity(two)


# --------------------------------------------------------------------------- #
#  The evidence for the reading order, which only the reading can give
# --------------------------------------------------------------------------- #

def test_folios_ascend_under_the_right_order_and_not_under_the_wrong_one():
    """A 2x2 sheet's reading order cannot be read off the image: both orders
    produce four plausible pages. What CAN be checked is the printed folios,
    and that is available only after the read — which is why `--nup-order` is
    a flag with evidence rather than a detector."""
    def doc_for(sequence):
        return _doc([{"page": 1, "lines": [
            {"type": "page_info", "text": str(f), "line": i + 1,
             "nup_page": i + 1, "region": {"top_left_x": 0, "top_left_y": 0,
                                           "width": 1, "height": 1}}
            for i, f in enumerate(sequence)]}])
    right = nup.ascending(nup.folios(doc_for([27, 28, 29, 30])))
    wrong = nup.ascending(nup.folios(doc_for([27, 29, 28, 30])))
    assert right == (3, 3)
    assert wrong[0] < wrong[1]


def test_folios_ignores_a_running_head_and_a_roman_numeral():
    doc = _doc([{"page": 1, "lines": [
        {"type": "page_info", "text": "Die Zusammensetzung der Gruppen",
         "line": 1, "region": {"top_left_x": 0, "top_left_y": 0,
                               "width": 1, "height": 1}},
        {"type": "page_info", "text": "iv", "line": 2,
         "region": {"top_left_x": 0, "top_left_y": 0, "width": 1, "height": 1}},
        {"type": "page_info", "text": "12", "line": 3,
         "region": {"top_left_x": 0, "top_left_y": 0, "width": 1, "height": 1}},
    ]}])
    got = nup.folios(doc)
    assert "Die Zusammensetzung der Gruppen" not in [t for _p, t in got]
    assert nup.ascending(got) == (0, 0)      # one arabic folio: nothing to compare


# --------------------------------------------------------------------------- #
#  Splitting on disk, and the cache hazard it creates
# --------------------------------------------------------------------------- #

def _write_png(path, arr):
    Image = pytest.importorskip("PIL.Image", reason="Pillow")
    Image.fromarray(arr, mode="L").save(path)


def test_split_writes_the_pages_and_the_map(tmp_path):
    src = tmp_path / "page-0001.png"
    _write_png(src, two_by_two())
    out = tmp_path / "printed"
    amap = nup.split([(1, src)], out)
    assert sorted(amap) == ["1", "2", "3", "4"]
    assert sorted(p.name for p in out.glob("page-*.png")) == [
        "page-0001.png", "page-0002.png", "page-0003.png", "page-0004.png"]
    assert json.loads((out / "nup.json").read_text()) == amap
    assert {m["sheet"] for m in amap.values()} == {1}


def test_changing_the_map_archives_the_old_pages_instead_of_serving_them(tmp_path):
    """THE hazard this layer creates, and it is a money hazard. The per-page
    Markdown the paid read writes is named for the PRINTED PAGE, so a changed
    map makes page 1 a different picture than the page-1 Markdown on disk was
    read from — and a resumed run would serve it anyway. Measured live on
    penev_A: its first reading numbered 22 SHEETS 1..22 and the split numbers
    88 printed pages 1..88, so pages 1-22 would have resumed from a reading of
    four times as much page.

    The old directory is MOVED, never removed: what is in it was paid for.
    """
    src = tmp_path / "page-0001.png"
    _write_png(src, two_by_two())
    out = tmp_path / "printed"
    nup.split([(1, src)], out)
    (out / "page-0001.md").write_text("bought and paid for", encoding="utf-8")

    nup.split([(1, src)], out, nup="1")          # a different map
    assert len(list(out.glob("page-*.png"))) == 1
    assert not (out / "page-0001.md").is_file()  # not served under a new map
    archived = list(tmp_path.glob("printed-was*"))
    assert len(archived) == 1
    assert (archived[0] / "page-0001.md").read_text() == "bought and paid for"


def test_splitting_twice_with_the_same_map_keeps_the_markdown(tmp_path):
    """The other half of the same rule: an unchanged map must not cost a
    re-read."""
    src = tmp_path / "page-0001.png"
    _write_png(src, two_by_two())
    out = tmp_path / "printed"
    nup.split([(1, src)], out)
    (out / "page-0002.md").write_text("kept", encoding="utf-8")
    nup.split([(1, src)], out)
    assert (out / "page-0002.md").read_text() == "kept"
    assert not list(tmp_path.glob("printed-was*"))


def test_a_one_up_sheet_is_copied_whole_rather_than_cropped(tmp_path):
    src = tmp_path / "page-0001.png"
    _write_png(src, one_up())
    amap = nup.split([(1, src)], tmp_path / "printed")
    assert len(amap) == 1
    assert amap["1"]["box"] == [0, 0, 400, 600]
    assert nup.is_identity(amap)
