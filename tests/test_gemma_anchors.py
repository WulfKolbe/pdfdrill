r"""The detector's display boxes as fixed points in the ink alignment.

WHY ANCHORS AND NOT A BETTER COST FUNCTION. `align` is one monotone walk down
the page, so its errors are CUMULATIVE: a single display whose row count it
guesses wrong shifts every box below it, and the cost function cannot tell,
because a formula's ink width is not predictable from its LaTeX the way a
prose line's is. MEASURED on penev_A with the ink walk alone: 5 of 116 display
formulas and 3 of 116 equation numbers boxed at IoU >= 0.5, against 110 and
112 once the detector's boxes anchor the walk.

MEASURED on Killing pages 1-20, assembling the same Markdown three ways
against the same MathPix reference: 705 of 733 reference lines boxed by the
ink walk alone (96%, median IoU 0.824) and 715 with anchors (98%, 0.832).

So these tests hold two separate promises: that an anchor fixes the band it
is in, and that a page WITHOUT a detector is aligned exactly as it was before
this existed — which is why `align_anchored` wraps `align` rather than
replacing it.
"""
from __future__ import annotations

import pytest

from pdfdrill import gemma_reader as gr
from pdfdrill.pagemd import Item


def row(y0: int, y1: int, x0: int = 100, x1: int = 900):
    """One ink row as the single component that spans it."""
    return [(x0, y0, x1, y1)]


def prose(text: str = "a prose line of ordinary length here") -> Item:
    return Item("text", text, md=text)


def display(md: str = "$$x = y$$") -> Item:
    return Item("math", md, md=md)


# --------------------------------------------------------------------------- #
#  Falling back
# --------------------------------------------------------------------------- #

def test_without_detector_boxes_it_is_exactly_the_plain_walk():
    items = [prose(), display(), prose()]
    rows = [row(100, 130), row(200, 280), row(320, 350)]
    plain = gr.align(items, rows, page_width=1000)
    got = gr.align_anchored(items, rows, page_width=1000, displays=())
    assert [(p.box, p.geometry) for p in got] == [(p.box, p.geometry)
                                                  for p in plain]


def test_a_page_with_no_math_items_is_the_plain_walk():
    items = [prose(), prose()]
    rows = [row(100, 130), row(200, 230)]
    got = gr.align_anchored(items, rows, page_width=1000,
                            displays=[(100, 500, 900, 600)])
    assert [p.geometry for p in got] == ["ink", "ink"]


def test_a_detector_box_nowhere_near_the_reading_is_not_forced_on_it():
    """ANCHOR_REACH. Six line heights is wide enough to survive the drift a
    dense page accumulates and narrow enough that two formulas cannot swap.
    A box far outside that is evidence about some other page."""
    items = [prose(), display(), prose()]
    rows = [row(100, 130), row(200, 280), row(320, 350)]
    got = gr.align_anchored(items, rows, page_width=1000,
                            displays=[(100, 3000, 900, 3100)],
                            line_height=30)
    assert got[1].geometry != "yolo"


# --------------------------------------------------------------------------- #
#  Anchoring
# --------------------------------------------------------------------------- #

def test_a_matched_display_takes_the_detectors_box():
    items = [prose(), display(), prose()]
    rows = [row(100, 130), row(200, 280), row(320, 350)]
    got = gr.align_anchored(items, rows, page_width=1000,
                            displays=[(140, 205, 880, 275)],
                            line_height=30)
    assert got[1].geometry == "yolo"
    assert got[1].box == (140, 205, 880, 275)


def test_an_anchor_stops_a_drift_above_it_from_crossing_it():
    """The point of the whole mechanism. The reading has one more prose line
    than the page has prose rows above the formula, so the plain walk has to
    misplace something; with an anchor the damage is confined to the band
    above, and every line below the formula is right."""
    items = [prose(), prose(), prose(), display(), prose(), prose()]
    rows = [row(100, 130), row(140, 170),          # two rows, three items
            row(300, 380),                          # the display
            row(420, 450), row(460, 490)]
    displays = [(100, 300, 900, 380)]
    got = gr.align_anchored(items, rows, page_width=1000, displays=displays,
                            line_height=30)
    assert got[3].box == (100, 300, 900, 380)
    # the two prose lines BELOW the formula get the two rows below it
    assert got[4].box == (100, 420, 900, 450)
    assert got[5].box == (100, 460, 900, 490)


def test_one_detector_box_holding_several_written_displays_is_divided():
    """The model writes the rows of one printed system as separate `$$`
    blocks; the detector boxes the system once. Divided along the ink rows
    inside the box when the counts agree."""
    items = [prose(), display("$$x = 1$$"), display("$$y = 2$$"), prose()]
    rows = [row(100, 130), row(300, 330), row(340, 370), row(420, 450)]
    got = gr.align_anchored(items, rows, page_width=1000,
                            displays=[(100, 295, 900, 375)], line_height=30)
    assert [p.geometry for p in got[1:3]] == ["yolo-row", "yolo-row"]
    assert got[1].box == (100, 300, 900, 330)
    assert got[2].box == (100, 340, 900, 370)


def test_a_group_the_rows_disagree_with_is_divided_evenly():
    """When the ink inside the box does not give one row per written display,
    an even division is still a box per display and says so in `geometry`."""
    items = [display("$$a$$"), display("$$b$$"), display("$$c$$")]
    rows = [row(300, 400)]                       # one row, three displays
    got = gr.align_anchored(items, rows, page_width=1000,
                            displays=[(100, 300, 900, 400)], line_height=30)
    assert [p.geometry for p in got] == ["yolo-even"] * 3
    assert [p.box[1] for p in got] == [300, 333, 366]
    assert got[-1].box[3] == 400


def test_two_anchors_make_three_bands_each_walked_on_its_own_rows():
    items = [prose(), display(), prose(), display(), prose()]
    rows = [row(100, 130), row(200, 260), row(320, 350), row(400, 460),
            row(520, 550)]
    displays = [(100, 200, 900, 260), (100, 400, 900, 460)]
    got = gr.align_anchored(items, rows, page_width=1000, displays=displays,
                            line_height=30)
    assert [p.geometry for p in got] == ["ink", "yolo", "ink", "yolo", "ink"]
    assert [p.box for p in got] == [(100, 100, 900, 130), (100, 200, 900, 260),
                                    (100, 320, 900, 350), (100, 400, 900, 460),
                                    (100, 520, 900, 550)]


# --------------------------------------------------------------------------- #
#  Monotonicity, which is not optional
# --------------------------------------------------------------------------- #

def test_the_matching_cannot_cross():
    """Both sequences are in reading order. A matching that may cross is a
    matching that will, and a crossed pair makes a band with a negative row
    range — the walk inside it would place boxes above the formula that
    precedes them."""
    items = [display("$$first$$"), display("$$second$$")]
    rows = [row(100, 160), row(300, 360)]
    got = gr.align_anchored(items, rows, page_width=1000,
                            displays=[(100, 100, 900, 160),
                                      (100, 300, 900, 360)],
                            line_height=30)
    assert got[0].box[1] < got[1].box[1]


def test_an_anchor_whose_rows_run_backwards_is_dropped_not_obeyed():
    """A detector box that holds no ink row, or whose rows lie before the
    previous anchor's, is discarded and the band is walked instead."""
    items = [prose(), display(), prose()]
    rows = [row(100, 130), row(200, 260), row(320, 350)]
    # a box in a gap with no ink row in it at all
    got = gr.align_anchored(items, rows, page_width=1000,
                            displays=[(100, 270, 900, 300)], line_height=30)
    assert got[1].geometry != "yolo"
    assert all(p.box is None or p.box[1] >= 0 for p in got)


def test_an_item_in_a_band_with_no_rows_gets_no_box_rather_than_a_wrong_one():
    items = [display(), prose(), display()]
    rows = [row(100, 160), row(300, 360)]
    got = gr.align_anchored(items, rows, page_width=1000,
                            displays=[(100, 100, 900, 160),
                                      (100, 300, 900, 360)],
                            line_height=30)
    assert got[0].geometry == "yolo" and got[2].geometry == "yolo"
    assert got[1].box is None and got[1].geometry == "none"


def test_a_container_in_a_rowless_band_stays_a_container():
    """Its box comes from its children, so "no rows here" must not relabel
    it as unplaced."""
    kid = prose()
    parent = Item("footnote", "", md="", children=[kid])
    kid.parent = parent
    items = [display(), parent, display()]
    rows = [row(100, 160), row(300, 360)]
    got = gr.align_anchored(items, rows, page_width=1000,
                            displays=[(100, 100, 900, 160),
                                      (100, 300, 900, 360)],
                            line_height=30)
    assert got[1].geometry == "container"


# --------------------------------------------------------------------------- #
#  Degenerate input
# --------------------------------------------------------------------------- #

def test_no_rows_is_no_boxes_and_not_a_crash():
    got = gr.align_anchored([prose(), display()], [], page_width=1000,
                            displays=[(1, 2, 3, 4)])
    assert all(p.box is None for p in got)


def test_no_items_is_an_empty_result():
    assert gr.align_anchored([], [row(1, 2)], page_width=1000,
                             displays=[(1, 2, 3, 4)]) == []


def test_place_by_order_gives_the_kth_unboxed_item_the_kth_box():
    """By ORDER and not by position, because these are exactly the items for
    which no position was derived."""
    items = [Item("equation_number", "(1)", md="(1)"),
             prose(),
             Item("equation_number", "(2)", md="(2)")]
    placed = [gr.Placed(items[0], None, "pending-split"),
              gr.Placed(items[1], (0, 0, 10, 10), "ink"),
              gr.Placed(items[2], None, "pending-split")]
    n = gr.place_by_order(placed, items, [(900, 100, 950, 120),
                                          (900, 300, 950, 320)],
                          types=("equation_number",), geometry="yolo")
    assert n == 2
    assert placed[0].box == (900, 100, 950, 120)
    assert placed[2].box == (900, 300, 950, 320)
    assert placed[1].box == (0, 0, 10, 10)      # already placed, untouched


def test_place_by_order_leaves_a_surplus_on_either_side_alone():
    items = [Item("equation_number", "(1)", md="(1)")]
    placed = [gr.Placed(items[0], None, "pending-split")]
    assert gr.place_by_order(placed, items, [(1, 2, 3, 4), (5, 6, 7, 8)],
                             types=("equation_number",),
                             geometry="yolo") == 1
    items2 = [Item("equation_number", "(1)", md="(1)"),
              Item("equation_number", "(2)", md="(2)")]
    placed2 = [gr.Placed(i, None, "pending-split") for i in items2]
    assert gr.place_by_order(placed2, items2, [(1, 2, 3, 4)],
                             types=("equation_number",),
                             geometry="yolo") == 1
    assert placed2[1].box is None


# --------------------------------------------------------------------------- #
#  Whitening, which the ink pass depends on
# --------------------------------------------------------------------------- #

def test_whitening_a_figure_keeps_its_ink_out_of_the_row_banding():
    """MEASURED as the cause of the 97x3413 gutter band that collapsed a
    whole Hilbert page to a single ink row: a large connected mass belonging
    to no printed line is handed to whatever item is passing."""
    np = pytest.importorskip("numpy")
    from pdfdrill import inkbox
    gray = np.full((400, 400), 255, dtype="uint8")
    gray[50:60, 100:300] = 0                    # a printed line
    gray[100:380, 20:380] = 0                   # a figure
    assert len(inkbox.rows(inkbox.components(gray))) >= 1
    clean = gr._whiten_array(gray, [(20, 100, 380, 380)])
    comps = inkbox.components(clean)
    assert len(comps) == 1
    assert comps[0][1] == 50 and comps[0][3] == 60


def test_whitening_nothing_returns_the_very_same_array():
    """So a page with no figures costs no copy."""
    np = pytest.importorskip("numpy")
    gray = np.full((10, 10), 255, dtype="uint8")
    assert gr._whiten_array(gray, []) is gray


# --------------------------------------------------------------------------- #
#  A figure nobody wrote down
# --------------------------------------------------------------------------- #

def test_a_detected_figure_the_model_passed_over_still_gets_a_line():
    """Once a figure is whitened before the read there is nothing on the page
    for the model to transcribe, so saying nothing about it is the COMMON
    case. MEASURED on penev_A: 1 of 14 `diagram` and 2 of 11 `chart`
    reference lines boxed without this, 13 and 11 with it. A figure the
    detector found and the reading does not mention is a hole nothing
    downstream can see — `inspect` draws no box and `model` builds no object,
    so the page looks complete and is not."""
    items = [prose(), prose()]
    placed = [gr.Placed(items[0], (100, 100, 900, 130), "ink"),
              gr.Placed(items[1], (100, 700, 900, 730), "ink")]
    assert gr.emit_figures(placed, [(120, 200, 880, 600)]) == 1
    assert [p.item.type for p in placed] == ["text", "diagram", "text"]
    fig = placed[1]
    assert fig.box == (120, 200, 880, 600) and fig.geometry == "yolo"
    assert fig.item.described is True and fig.item.text == ""


def test_an_emitted_figure_goes_in_reading_order_not_at_the_end():
    """`line` numbers a page top to bottom, and a reader sent to a figure
    listed after the footnotes is being told something false."""
    items = [prose(), prose(), prose()]
    placed = [gr.Placed(items[0], (0, 100, 10, 130), "ink"),
              gr.Placed(items[1], (0, 500, 10, 530), "ink"),
              gr.Placed(items[2], (0, 900, 10, 930), "ink")]
    gr.emit_figures(placed, [(0, 600, 10, 800), (0, 200, 10, 400)])
    tops = [p.box[1] for p in placed]
    assert tops == sorted(tops), tops


def test_a_figure_below_everything_is_appended():
    items = [prose()]
    placed = [gr.Placed(items[0], (0, 100, 10, 130), "ink")]
    gr.emit_figures(placed, [(0, 500, 10, 700)])
    assert placed[-1].item.type == "diagram"


def test_emitting_no_figures_changes_nothing():
    items = [prose()]
    placed = [gr.Placed(items[0], (0, 100, 10, 130), "ink")]
    assert gr.emit_figures(placed, []) == 0
    assert len(placed) == 1


def test_an_emitted_figure_survives_page_lines_with_valid_ids():
    """Insertion is safe only because every cross-reference between items is
    an object reference and not an index; this is the test that holds that."""
    kid = prose()
    parent = Item("footnote", "", md="", children=[kid])
    kid.parent = parent
    placed = [gr.Placed(parent, (0, 800, 10, 860), "container"),
              gr.Placed(kid, (0, 800, 10, 830), "ink")]
    gr.emit_figures(placed, [(0, 100, 10, 300)])
    lines = gr.page_lines(placed, 1)
    assert [l["type"] for l in lines] == ["diagram", "footnote", "text"]
    assert [l["line"] for l in lines] == [1, 2, 3]
    by_id = {l["id"]: l for l in lines}
    par = next(l for l in lines if l["type"] == "footnote")
    assert par["children_ids"] and all(c in by_id for c in par["children_ids"])
    assert by_id[par["children_ids"][0]]["parent_id"] == par["id"]
