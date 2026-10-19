r"""Whoever made the box, the ink is the arbiter.

Boxes reach this pass from an ink row (too loose: the row's slack, a
neighbour's descender), from a layout detector (too loose at the left and
right, because the box is drawn around a region and not around glyphs), or
from an interpolation (roughly right). All three are repaired by the same
three questions and none of them needs to know which produced it — so these
tests build the boxes directly rather than running a reader.

What this pass must NOT do is as important as what it does, and four of the
tests below are about that: a figure keeps its box, a container takes its
children's union, an empty table cell keeps a box the ink cannot confirm, and
a line nobody placed is REPORTED rather than quietly given a position. The
last one has a measured history: asking the ink to confirm empty cells cost
735 cells their geometry.
"""
from __future__ import annotations

import pytest

from pdfdrill import sanitize

np = pytest.importorskip("numpy")


def page_img(w: int = 400, h: int = 300):
    return np.full((h, w), 255, dtype="uint8")


def ink(img, x0: int, y0: int, x1: int, y1: int) -> None:
    img[y0:y1, x0:x1] = 0


def line(typ: str, x: int, y: int, w: int, h: int, **kw) -> dict:
    out = {"type": typ, "text": kw.pop("text", "t"),
           "line": kw.pop("line", 1), "geometry": kw.pop("geometry", "ink"),
           "region": {"top_left_x": x, "top_left_y": y,
                      "width": w, "height": h}}
    out.update(kw)
    return out


def page(lines, w: int = 400, h: int = 300) -> dict:
    return {"page": 1, "page_width": w, "page_height": h, "lines": lines}


def run(lines, img):
    st = sanitize.new_stats()
    checks = sanitize.sanitize_page(page(lines, img.shape[1], img.shape[0]),
                                    img, st)
    return st, checks


def box(l: dict) -> tuple[int, int, int, int]:
    r = l["region"]
    return (r["top_left_x"], r["top_left_y"],
            r["top_left_x"] + r["width"], r["top_left_y"] + r["height"])


# --------------------------------------------------------------------------- #
#  shrink
# --------------------------------------------------------------------------- #

def test_a_loose_box_shrinks_to_the_ink_it_holds():
    img = page_img()
    ink(img, 100, 100, 200, 112)
    lines = [line("text", 50, 90, 300, 40)]          # much too loose
    st, _ = run(lines, img)
    assert box(lines[0]) == (100, 100, 200, 112)
    assert st["boxes_changed"] == 1
    assert lines[0]["geometry_before"] == {"top_left_x": 50, "top_left_y": 90,
                                           "width": 300, "height": 40}


def test_the_four_point_polygon_is_rewritten_with_the_region():
    """`cnt` is the same box said twice; a consumer reading one and not the
    other gets a stale answer."""
    img = page_img()
    ink(img, 100, 100, 200, 112)
    lines = [line("text", 50, 90, 300, 40,
                  cnt=[[50, 90], [350, 90], [350, 130], [50, 130]])]
    run(lines, img)
    r = lines[0]["region"]
    assert lines[0]["cnt"][0] == [r["top_left_x"], r["top_left_y"]]
    assert lines[0]["cnt"][2] == [r["top_left_x"] + r["width"],
                                  r["top_left_y"] + r["height"]]


def test_an_unchanged_box_is_left_alone_and_records_nothing():
    img = page_img()
    ink(img, 100, 100, 200, 112)
    lines = [line("text", 100, 100, 100, 12)]
    st, _ = run(lines, img)
    assert st["boxes_changed"] == 0
    assert "geometry_before" not in lines[0]


# --------------------------------------------------------------------------- #
#  claim
# --------------------------------------------------------------------------- #

def test_a_component_belongs_to_the_smallest_box_holding_its_centre():
    """An equation number inside the box drawn around its formula block is
    the case this ordering exists for."""
    img = page_img()
    ink(img, 100, 100, 300, 140)        # the formula
    ink(img, 340, 112, 360, 126)        # its number
    lines = [line("math", 90, 90, 290, 60, line=1),
             line("equation_number", 335, 108, 30, 22, line=2)]
    run(lines, img)
    assert box(lines[1]) == (340, 112, 360, 126)
    assert box(lines[0])[2] <= 340


def test_two_lines_do_not_share_a_component():
    img = page_img()
    ink(img, 100, 100, 200, 112)
    ink(img, 100, 140, 200, 152)
    lines = [line("text", 90, 95, 300, 25, line=1),
             line("text", 90, 135, 300, 25, line=2)]
    run(lines, img)
    assert box(lines[0]) == (100, 100, 200, 112)
    assert box(lines[1]) == (100, 140, 200, 152)


# --------------------------------------------------------------------------- #
#  grow
# --------------------------------------------------------------------------- #

def test_a_glyph_the_box_clipped_rejoins_its_line():
    """What a detector box leaves out at the left or right edge: the model
    read the character, the box stopped short of it."""
    img = page_img()
    ink(img, 100, 100, 200, 112)        # the line
    ink(img, 205, 100, 212, 112)        # a glyph just past the box
    lines = [line("text", 100, 100, 100, 12)]
    st, _ = run(lines, img)
    assert box(lines[0])[2] == 212
    assert st["components_grown"] >= 1
    assert st["widened"] == 1


def test_a_component_too_far_away_does_not_join():
    """GAP is wider than a word space and narrower than the space between an
    equation and its number, so growing recovers a clipped glyph without
    swallowing the neighbour."""
    img = page_img()
    ink(img, 100, 100, 200, 112)
    ink(img, 360, 100, 380, 112)        # far right, on the same band
    lines = [line("text", 100, 100, 100, 12)]
    run(lines, img)
    assert box(lines[0])[2] == 200


def test_a_component_off_the_band_does_not_join():
    img = page_img()
    ink(img, 100, 100, 200, 112)
    ink(img, 205, 200, 215, 212)        # beside it horizontally, far below
    lines = [line("text", 100, 100, 100, 12)]
    run(lines, img)
    assert box(lines[0]) == (100, 100, 200, 112)


def test_a_container_does_not_grow():
    """Its box means its children's extent, not the extent of its own ink —
    of which it has none."""
    img = page_img()
    ink(img, 100, 100, 200, 112)
    ink(img, 100, 130, 180, 142)
    kids = [line("text", 100, 100, 100, 12, id="k1", line=2),
            line("text", 100, 130, 80, 12, id="k2", line=3)]
    parent = line("footnote", 0, 0, 0, 0, text="", line=1,
                  children_ids=["k1", "k2"])
    lines = [parent] + kids
    st, _ = run(lines, img)
    assert box(parent) == (100, 100, 200, 142)
    assert st["containers_unioned"] == 1


def test_a_container_whose_children_were_never_placed_keeps_its_box():
    img = page_img()
    parent = line("footnote", 5, 6, 7, 8, text="", line=1,
                  children_ids=["k1"])
    lines = [parent, line("text", 0, 0, 0, 0, id="k1", line=2)]
    run(lines, img)
    assert box(parent) == (5, 6, 12, 14)


# --------------------------------------------------------------------------- #
#  what it refuses to touch
# --------------------------------------------------------------------------- #

def test_a_figure_keeps_its_box_and_swallows_its_own_ink():
    """So a figure's strokes never join a text line. The figure is a large
    connected mass belonging to no printed line, and a row banding that must
    consume rows monotonically hands it to whatever line is passing."""
    img = page_img()
    ink(img, 50, 50, 350, 200)           # the figure
    ink(img, 50, 230, 250, 242)          # a caption line below it
    fig = line("diagram", 40, 40, 320, 170, text="", line=1)
    cap = line("text", 50, 230, 200, 12, line=2)
    lines = [fig, cap]
    run(lines, img)
    assert box(fig) == (40, 40, 360, 210)        # untouched
    assert box(cap) == (50, 230, 250, 242)       # did not swallow the figure


def test_an_empty_table_cell_keeps_a_box_the_ink_cannot_confirm():
    """A cell's geometry comes from the grid. A cell owning no ink is an EMPTY
    CELL, which is correct — and asking the ink to confirm it cost 735 cells
    their geometry once already."""
    img = page_img()
    lines = [line("simple_cell", 100, 100, 50, 20, text="", line=1)]
    st, checks = run(lines, img)
    assert box(lines[0]) == (100, 100, 150, 120)
    assert st["no_ink"] == 0
    assert checks == []


# --------------------------------------------------------------------------- #
#  check
# --------------------------------------------------------------------------- #

def test_a_line_with_no_ink_is_reported_with_how_its_box_was_made():
    """MEASURED on penev_A's sheet reading: 829 lines carried
    `geometry: none` and 95 carried `pending-split`, an INTERNAL marker of
    `align` that should never have reached a file. This pass cannot invent a
    position for a line the alignment never placed — but it says so, once,
    per line, which is the difference between a reading that is wrong and one
    that is wrong and silent."""
    img = page_img()
    ink(img, 100, 100, 200, 112)
    lines = [line("text", 100, 100, 100, 12, line=1),
             line("text", 300, 250, 60, 12, line=2, geometry="pending-split")]
    st, checks = run(lines, img)
    assert st["no_ink"] == 1
    assert st["no_ink_by_geometry"] == {"pending-split": 1}
    assert "no ink in its box" in checks[0] and "pending-split" in checks[0]


def test_a_text_line_two_printed_lines_tall_is_reported():
    """The box has to HOLD the tall mass for it to be claimed and then
    measured: an unclaimed component is the `no ink` check, not this one."""
    img = page_img()
    ink(img, 100, 100, 200, 112)        # an ordinary line, so lh is ordinary
    ink(img, 100, 200, 200, 260)        # one mass, two printed lines tall
    lines = [line("text", 100, 100, 100, 12, line=1),
             line("text", 100, 200, 100, 30, line=2, text="two lines?")]
    st, checks = run(lines, img)
    assert st["tall_text"] == 1
    assert "two printed lines" in checks[0]


def test_overlapping_boxes_are_reported_not_repaired():
    """A report, because which of the two is wrong is not knowable here."""
    img = page_img()
    ink(img, 100, 100, 200, 112)
    lines = [line("text", 100, 100, 100, 12, line=1),
             line("text", 105, 101, 90, 10, line=2)]
    st, checks = run(lines, img)
    assert st["overlaps"] >= 1
    assert any("overlap" in c for c in checks)


# --------------------------------------------------------------------------- #
#  the document pass
# --------------------------------------------------------------------------- #

def test_a_page_with_no_image_is_left_exactly_as_it_is(tmp_path):
    """A reading whose boxes were not checked beats one checked against the
    wrong picture."""
    doc = {"pages": [page([line("text", 1, 2, 3, 4)])]}
    before = doc["pages"][0]["lines"][0]["region"].copy()
    out = sanitize.sanitize(doc, {})
    assert out["pages"][0]["lines"][0]["region"] == before
    assert out["sanitize"]["stats"]["pages"] == 0


def test_sanitize_records_its_parameters_beside_its_counts(tmp_path):
    """So a number in the block can be read back against the thresholds that
    produced it."""
    Image = pytest.importorskip("PIL.Image", reason="Pillow")
    img = page_img()
    ink(img, 100, 100, 200, 112)
    png = tmp_path / "p.png"
    Image.fromarray(img, mode="L").save(png)
    doc = {"pages": [page([line("text", 50, 90, 300, 40)])]}
    out = sanitize.sanitize(doc, {1: png})
    blk = out["sanitize"]
    assert blk["stats"]["pages"] == 1 and blk["stats"]["boxes_changed"] == 1
    assert blk["params"]["gap"] == sanitize.GAP
    assert blk["checks_total"] == len(blk["checks"])
    assert "boxes tightened" in sanitize.report(out)


def test_the_checks_list_is_capped_but_the_total_is_not(tmp_path):
    """A 22-sheet document produced 941 checks; a lines.json carrying all of
    them verbatim is a lines.json nobody opens."""
    img = page_img()
    lines = [line("text", 300, 10 + 20 * i, 60, 12, line=i + 1)
             for i in range(12)]
    doc = {"pages": [page(lines)]}
    Image = pytest.importorskip("PIL.Image", reason="Pillow")
    png = tmp_path / "p.png"
    Image.fromarray(img, mode="L").save(png)
    out = sanitize.sanitize(doc, {1: png}, max_checks=5)
    assert len(out["sanitize"]["checks"]) == 5
    assert out["sanitize"]["checks_total"] == 12


def test_the_boxes_are_scaled_when_the_reading_is_at_another_resolution(tmp_path):
    """After `merge` the reading is in sheet pixels and the sheet render is
    the same size — but a reading made elsewhere need not be, and a pass that
    assumed it would repair boxes against the wrong coordinates."""
    img = page_img(400, 300)
    ink(img, 100, 100, 200, 112)
    doc = {"pages": [{"page": 1, "page_width": 200, "page_height": 150,
                      "lines": [line("text", 25, 45, 150, 20)]}]}
    st = sanitize.new_stats()
    sanitize.sanitize_page(doc["pages"][0], img, st)
    # image is 2x the reading, so ink at 100..200 px is 50..100 in the reading
    assert box(doc["pages"][0]["lines"][0]) == (50, 50, 100, 56)
