r"""The model lane: geometry by alignment, the MathPix-shaped writer, and the
budget gate on the one stage that spends money.

NOTHING HERE MAKES A NETWORK CALL. That is the design under test as much as
anything else: `assemble` is pure (Markdown + ink in, lines.json out) so that
every change to the geometry or the contract is verifiable against readings
already on disk, against a 10 EUR account with 0.28 EUR already spent.
"""
from __future__ import annotations

import json

import pytest

np = pytest.importorskip("numpy")

from pdfdrill import gemma_reader as gr
from pdfdrill import pagemd


# ── the file contract: the same names, in the same place, as MathPix ───────

def test_the_outputs_go_where_mathpix_would_have_put_them():
    from pdfdrill import mathpix_client
    ours = gr.expected_outputs("/docs/paper.pdf")
    theirs = mathpix_client.expected_outputs("/docs/paper.pdf")
    assert ours["lines.json"] == theirs["lines.json"]
    assert ours["md"] == theirs["md"]


def test_the_source_says_the_reading_was_not_bought(tmp_path):
    """Admitted to `_TYPED_GEOMETRY_SOURCES` — it carries MathPix's types in
    page pixels — and still not a MathPix purchase, which is the question the
    money-spending call sites ask."""
    from pdfdrill import commands
    p = tmp_path / "d.lines.json"
    gr.write_lines(gr.assemble(
        [(1, "<!-- page 1 | Head -->\n\n$$a=b$$\n\nhello\n", None)]), p)
    assert gr.is_gemma_lines(p)
    assert commands._is_typed_geometry_lines(p) is True
    assert commands._is_mathpix_lines(p) is False


def test_the_gate_needs_the_types_too_and_not_just_an_admitted_source(tmp_path):
    """Both halves are checked, and that is deliberate: a source admitted on
    the strength of its geometry still has to BE a typed reading. A reading
    carrying nothing but `text` lines does not pass on its name alone."""
    from pdfdrill import commands
    p = tmp_path / "plain.lines.json"
    gr.write_lines(gr.assemble([(1, "just prose, no math\n", None)]), p)
    assert gr.is_gemma_lines(p)
    assert commands._is_typed_geometry_lines(p) is False


def test_the_gemma_source_is_admitted_to_the_typed_geometry_gate():
    from pdfdrill import commands
    assert gr.SOURCE in commands._TYPED_GEOMETRY_SOURCES


# ── the budget gate ────────────────────────────────────────────────────────

def test_a_read_that_would_exceed_the_declared_budget_is_refused():
    """A fixed prepayment is not a rate limit: when it empties the endpoint
    stops answering mid-document, and a half-read document is worse than an
    unread one."""
    ok, level, msg = gr.read_preflight(100000, budget_eur=1.0)
    assert ok is False and level == "refuse"
    assert "remains" in msg


def test_a_read_well_inside_the_budget_is_allowed_and_priced():
    ok, level, msg = gr.read_preflight(48, budget_eur=9.72)
    assert ok is True and level == "ok"
    assert "48 pages" in msg and "EUR" in msg


def test_a_read_eating_a_quarter_of_the_budget_warns():
    ok, level, _msg = gr.read_preflight(4000, budget_eur=9.72)
    assert ok is True and level == "warn"


def test_without_a_declared_budget_the_cost_is_still_reported(monkeypatch):
    monkeypatch.delenv(gr.BUDGET_ENV, raising=False)
    ok, _level, msg = gr.read_preflight(48)
    assert ok is True and "no ceiling enforced" in msg


def test_the_budget_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv(gr.BUDGET_ENV, "0.001")
    ok, level, _msg = gr.read_preflight(48)
    assert ok is False and level == "refuse"


def test_an_unknown_page_count_warns_rather_than_guessing():
    ok, level, msg = gr.read_preflight(None)
    assert ok is True and level == "warn" and "cannot be estimated" in msg


# ── alignment ──────────────────────────────────────────────────────────────

def _rows(n, *, y0=100, step=50, x0=100, w=800):
    """n single-component rows, evenly spaced, all the same width."""
    return [[(x0, y0 + i * step, x0 + w, y0 + i * step + 30)] for i in range(n)]


def test_each_line_gets_its_own_row_when_the_counts_agree():
    items = pagemd.items("one line here\ntwo lines here\nthree lines here\n")
    placed = gr.align(items, _rows(3), page_width=1000)
    assert [p.geometry for p in placed] == ["ink"] * 3
    assert [p.box[1] for p in placed] == [100, 150, 200]


def test_the_assignment_is_monotone_so_a_box_never_comes_from_above():
    items = pagemd.items("\n".join(f"line number {i}" for i in range(8)) + "\n")
    placed = gr.align(items, _rows(8), page_width=1000)
    ys = [p.box[1] for p in placed]
    assert ys == sorted(ys)


def test_more_lines_than_rows_still_places_the_ones_it_can():
    """THE MEASURED FAILURE. Without a 'this item gets no row' move the page
    is infeasible, and an infeasible page yielded ZERO boxes for every line
    on it — 34 placed of 311 on the reference 10-page document."""
    items = pagemd.items("\n".join(f"line {i}" for i in range(12)) + "\n")
    placed = gr.align(items, _rows(6), page_width=1000)
    got = [p for p in placed if p.box is not None]
    assert len(got) == 6, "a page with more lines than rows placed nothing"
    assert all(p.geometry == "ink" for p in got)


def test_a_display_may_consume_several_rows_but_prose_may_not():
    """MathPix groups a multi-line display into ONE `math` line, so the
    reader must be able to; a `text` line swallowing six rows would be six
    printed lines lost."""
    assert gr._max_rows(pagemd.Item("math", "x")) == gr.MAX_ROWS_BLOCK
    assert gr._max_rows(pagemd.Item("text", "x")) == gr.MAX_ROWS_PROSE
    items = pagemd.items("$$\\begin{aligned} a &= b \\\\ c &= d\\end{aligned}$$\n")
    placed = gr.align(items, _rows(4), page_width=1000)
    assert placed[0].box is not None
    assert placed[0].box[3] - placed[0].box[1] > 30, "the display got one row"


def test_a_container_consumes_no_ink_row_of_its_own():
    """A container that is allowed to consume a row steals it from the line
    actually printed there and shifts every box below it — which cost 7 text
    lines and 4 displays the first time this was keyed off a type list."""
    items = pagemd.items("## § 3.\n\nThe Title Here\n\nbody line one\n")
    assert items[0].type == "section_header" and items[0].children
    placed = gr.align(items, _rows(3), page_width=1000)
    assert placed[0].geometry == "container" and placed[0].box is None
    assert [p.box[1] for p in placed[1:]] == [100, 150, 200]


def test_a_parents_box_is_the_union_of_its_children():
    items = pagemd.items("## § 3.\n\nThe Title Here\n")
    placed = gr.align(items, _rows(2), page_width=1000)
    gr.close_containers(placed, items)
    assert placed[0].box == (100, 100, 900, 180)
    assert placed[0].geometry == "container"


# ── splitting a shared row ─────────────────────────────────────────────────

def test_split_into_cuts_at_the_widest_gaps():
    comps = [(0, 0, 10, 10), (12, 0, 22, 10),          # cluster A
             (200, 0, 210, 10),                        # cluster B
             (400, 0, 410, 10), (412, 0, 420, 10)]     # cluster C
    parts = gr.split_into(comps, 3)
    assert [len(p) for p in parts] == [2, 1, 2]


def test_split_into_refuses_when_there_are_fewer_components_than_pieces():
    assert gr.split_into([(0, 0, 5, 5)], 3) is None


def test_the_equation_number_is_the_narrow_cluster_across_the_margin():
    """MEASURED against MathPix: its number boxes are 3.6-3.7% of page width
    and ONE line tall, while the display beside them is 27-54% wide and may
    be six rows tall. A geometric fraction of the host misses on both axes —
    the first version of this scored 1 of 51."""
    items = pagemd.items("$$x = y \\tag{3}$$\n")
    number = [(40, 100, 85, 140)]                       # the margin label
    body = [(400, 100, 900, 140)]                       # the display
    placed = gr.align(items, [number + body], page_width=1000)
    assert gr.split_numbers(placed, items, page_width=1000,
                            line_height=40.0) == 1
    num = next(p for p in placed if p.item.type == "equation_number")
    host = next(p for p in placed if p.item.type == "math")
    assert num.box == (40, 100, 85, 140)
    assert host.box == (400, 100, 900, 140)
    assert num.geometry == host.geometry == "ink-split"


def test_a_number_is_not_cut_out_of_an_aligned_blocks_own_column_gap():
    """An `aligned` block's column separation can exceed a line height. The
    narrowness requirement is what stops half the equation being handed to
    the number."""
    items = pagemd.items("$$a &= b \\tag{3}$$\n")
    wide_left = [(100, 100, 480, 140)]
    wide_right = [(600, 100, 900, 140)]
    placed = gr.align(items, [wide_left + wide_right], page_width=1000)
    assert gr.split_numbers(placed, items, page_width=1000,
                            line_height=40.0) == 0


def test_an_inter_word_gap_is_not_a_margin():
    items = pagemd.items("$$x = y \\tag{3}$$\n")
    comps = [(400, 100, 440, 140), (450, 100, 900, 140)]   # a 10px gap
    placed = gr.align(items, [comps], page_width=1000)
    assert gr.split_numbers(placed, items, page_width=1000,
                            line_height=40.0) == 0


def test_the_folio_and_the_running_head_get_separate_boxes():
    """MEASURED: MathPix never emits one box spanning that row."""
    md = "<!-- page 5 | Zusammensetzung von Gruppen. II. -->\n\nbody line\n"
    items = pagemd.items(md)
    head_row = [(60, 60, 110, 95)] + [(400, 60, 950, 95)]
    placed = gr.align(items, [head_row] + _rows(1, y0=200), page_width=1000)
    assert gr.split_furniture(placed, items, page_width=1000) == 1
    folio, head = placed[0], placed[1]
    assert folio.box == (60, 60, 110, 95)
    assert head.box == (400, 60, 950, 95)


def test_each_table_cell_gets_its_own_box_cut_from_its_printed_row():
    items = pagemd.items("| A | B | C |\n")
    row = [(100, 100, 150, 140), (400, 100, 450, 140), (800, 100, 850, 140)]
    placed = gr.align(items, [row], page_width=1000)
    assert gr.split_cells(placed, items, page_width=1000) == 1
    cells = [p for p in placed if p.item.type == "simple_cell"]
    assert [c.box for c in cells] == row
    assert all(c.geometry == "ink-split" for c in cells)


# ── the writer: MathPix's keys, exactly ────────────────────────────────────

def _page(md="a line of prose\n"):
    return gr.assemble_page(md, None, 1)


def test_a_page_carries_every_key_mathpix_puts_on_a_page():
    pg = _page()
    for key in ("page", "page_width", "page_height", "lines", "image_id",
                "parse_status", "fallback_count", "page_confidence",
                "languages_detected"):
        assert key in pg, key


def test_a_line_carries_every_key_mathpix_puts_on_a_line():
    """A consumer of a bought reading reads these; one that is absent is read
    as empty, silently."""
    line = _page()["lines"][0]
    for key in ("cnt", "region", "line", "column", "is_printed",
                "is_handwritten", "id", "type", "conversion_output",
                "text", "text_display", "confidence", "confidence_rate",
                "text_confidence", "layout_confidence"):
        assert key in line, key


def test_the_confidences_are_null_and_not_invented():
    """A model gives no per-line confidence. None means unknown; a number
    would be a claim this reader cannot justify."""
    line = _page()["lines"][0]
    assert line["confidence"] is None
    assert line["confidence_rate"] is None


def test_cnt_is_the_region_as_a_four_point_polygon():
    pg = gr.assemble_page("x\n", None, 1)
    line = pg["lines"][0]
    assert line["cnt"] == []                     # no box -> no polygon
    placed = [gr.Placed(pagemd.Item("text", "x"), (10, 20, 30, 50), "ink")]
    rec = gr.page_lines(placed, 1)[0]
    assert rec["region"] == {"top_left_x": 10, "top_left_y": 20,
                             "width": 20, "height": 30}
    assert rec["cnt"] == [[10, 20], [30, 20], [30, 50], [10, 50]]


def test_furniture_and_numbers_are_not_conversion_output():
    """MEASURED on both reference readings."""
    pg = gr.assemble_page("<!-- page 3 | Head -->\n\n$$a=b \\tag{1}$$\n", None, 3)
    by = {(l["type"], l["text"]): l for l in pg["lines"]}
    assert by[("page_info", "3")]["conversion_output"] is False
    assert by[("equation_number", "(1)")]["conversion_output"] is False
    assert [l for l in pg["lines"]
            if l["type"] == "math"][0]["conversion_output"] is True


def test_a_container_and_its_children_are_wired_by_id():
    pg = gr.assemble_page("[^1]: a note\nsecond line\n", None, 1)
    parent = [l for l in pg["lines"] if l["type"] == "footnote"][0]
    kids = [l for l in pg["lines"] if l.get("parent_id") == parent["id"]]
    assert parent["children_ids"] == [k["id"] for k in kids]
    assert len(kids) == 2
    assert parent["text"] == ""


def test_a_page_with_no_render_still_yields_its_lines_and_says_so():
    """A reading whose text is right and whose boxes are missing is still a
    reading `model` can build prose from. Saying so beats refusing the whole
    document because one page failed to rasterize."""
    pg = gr.assemble_page("one\ntwo\n", None, 4)
    assert pg["parse_status"] == "no_render"
    assert pg["fallback_count"] == len(pg["lines"]) == 2
    assert all(l["region"]["width"] == 0 for l in pg["lines"])


def test_the_document_declares_its_reader_and_its_prompt():
    doc = gr.assemble([(1, "x\n", None)], prompt_name="page-ocr-markdown",
                      model="google/gemma-4-26B-A4B")
    assert doc["source"] == gr.SOURCE
    assert doc["ocr"]["prompt"] == "page-ocr-markdown"
    assert doc["ocr"]["model"] == "google/gemma-4-26B-A4B"
    assert doc["ocr"]["dpi"] == gr.DPI


def test_write_lines_is_atomic_and_leaves_no_part_file(tmp_path):
    out = tmp_path / "x.lines.json"
    gr.write_lines(gr.assemble([(1, "a\n", None)]), out)
    assert json.loads(out.read_text(encoding="utf-8"))["source"] == gr.SOURCE
    assert not list(tmp_path.glob("*.part"))


def test_the_markdown_leaves_out_furniture_and_numbers():
    doc = gr.assemble([(1, "<!-- page 2 | H -->\n\nbody\n\n$$a=b \\tag{1}$$\n",
                        None)])
    md = gr.markdown(doc)
    assert "body" in md and "(1)" not in md and "page 2" not in md


# ── geometry, end to end on a synthetic page ───────────────────────────────

def test_boxes_are_measured_from_the_pages_own_ink(tmp_path):
    """The only end-to-end geometry test that needs no document: three bars
    of ink at known places, three lines of Markdown, and each line must come
    back with the bar's own box."""
    Image = pytest.importorskip("PIL.Image")
    g = np.full((600, 800), 255, dtype=np.uint8)
    bars = [(100, 100, 700, 130), (100, 200, 500, 230), (100, 300, 300, 330)]
    for x0, y0, x1, y1 in bars:
        g[y0:y1, x0:x1] = 0
    png = tmp_path / "page-0001.png"
    Image.fromarray(g).save(png)

    md = "a line that is quite long indeed and runs on\na shorter line\nshort\n"
    pg = gr.assemble_page(md, png, 1)
    assert (pg["page_width"], pg["page_height"]) == (800, 600)
    assert pg["parse_status"] == "parsed" and pg["fallback_count"] == 0
    got = [(l["region"]["top_left_x"], l["region"]["top_left_y"],
            l["region"]["top_left_x"] + l["region"]["width"],
            l["region"]["top_left_y"] + l["region"]["height"])
           for l in pg["lines"]]
    assert got == bars
    assert all(l["geometry"] == "ink" for l in pg["lines"])


def test_strips_cover_the_page_and_overlap(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    png = tmp_path / "page-0001.png"
    Image.new("L", (400, 1200), 255).save(png)
    pieces = gr.page_strips(png, tmp_path / "s", strips=6)
    assert len(pieces) == 6
    heights = []
    for f in pieces:
        with Image.open(f) as im:
            assert im.size[0] == 400
            heights.append(im.size[1])
    assert sum(heights) > 1200, "the strips do not overlap"
    assert all(h > 1200 / 6 for h in heights)


def test_the_source_is_declared_in_the_first_bytes_of_the_file(tmp_path):
    """`commands._lines_json_source` is the cheap reader every routing
    decision uses and it searches only the first 8,192 bytes — "both
    producers emit `source` near the top". A 1.3 MB reading that declares its
    producer at the END declares it to nobody: measured, the lane's own cache
    check missed and the command set out to buy a reading already on disk.
    """
    from pdfdrill import commands
    out = tmp_path / "big.lines.json"
    gr.write_lines(
        gr.assemble([(n, "a line of prose\n" * 40, None) for n in range(1, 60)]),
        out)
    assert out.stat().st_size > 8192 * 10
    assert gr.is_gemma_lines(out)
    assert commands._lines_json_source(out) == gr.SOURCE


def test_a_cached_reading_is_never_re_read(tmp_path, monkeypatch):
    """Idempotent in the same way the MathPix lane is: a reading on disk
    costs nothing, and `force` is the only way to spend again."""
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    gr.write_lines(gr.assemble([(1, "<!-- page 1 | H -->\n\n$$a=b$$\n", None)]),
                   tmp_path / "d.lines.json")

    def explode(*a, **k):
        raise AssertionError("a cached reading was re-read — that is a bill")

    monkeypatch.setattr(gr, "read_page", explode)
    res = gr.fetch_gemma(pdf)
    assert res["status"] == "cached"
