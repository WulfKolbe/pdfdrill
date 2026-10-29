r"""The second column was found at an equation's indent, so a two-column paper
was read across its gutter.

MEASURED 2026-10-29 on 2009tiplabeling page 1 (612x792 pt, text 49..563, the
gutter at about 313), through the reader itself:

    _column_edge(115 rows, (0,0,612,792))  ->  278.2
    _split_at_columns                      ->  115 rows became 122

Seven cuts on a page that needed about forty, all of them in the wrong place,
and 10 of the 88 finished lines still spanned the whole measure — one of them
reading

    F4-icgo.n1n.ecEtixvaitmyp(lbe)saonfdbﬁinnaarlylyim8-acgoendneepctiicvtiintyg(tce)xt(a),itslabeli...

which is two pieces of text at one baseline, interleaved. Across the fifteen
CCL readings, 2,165 of 9,688 body lines on the twelve two-column papers crossed
their page's own gutter — 22.3%, and 44.3% on 2018icpr.

THE RULE WAS "THE FIRST MODE PAST THE MIDDLE", not "the mode that looks like a
second column". `_column_edge` walks the left-edge modes in ascending x and
returns the first one clearing three guards, and a display equation's indent in
the LEFT column clears all three: it is past `0.9 * mid`, past
`first + 0.25 * page_width`, and carries two rows or more. It is then returned
as the gutter, and every row straddling it is cut while the real gutter is
never looked at.

The guards stay — each was bought with a defect, 748's one-column page cut at
280.8 among them. What changes is the CHOICE among the modes that pass them:
the two columns of a paper are the same width by construction, so the second
column starts near the middle of the text measure. Pick the candidate nearest
to that, not the first one encountered.
"""
import pytest

from pdfreader import docmodel_six as D

PAGE = (0, 0, 612.0, 792.0)
SIZE = 9.6


def _row(x0: float, x1: float, y: float, n: int = 40):
    """A row of `n` glyphs spanning x0..x1 — enough to pass `len(r) <= 8`."""
    step = (x1 - x0) / n
    return [D.GlyphNode(id=f"g{y}_{i}", page=1,
                        rect=(x0 + i * step, y, x0 + (i + 1) * step - 0.4,
                              y + SIZE),
                        text="x", cid=120, glyphname="x",
                        fontname="F1", family="F", size=SIZE,
                        tex=None, stream=i)
            for i in range(n)]


def _two_column_page(*, with_equation_indent: bool):
    """Left column 49..295, right column 313..563 — the real measurements from
    2009tiplabeling. Optionally a display equation indented to 283 in the LEFT
    column, which is the mode that won."""
    rows = []
    y = 700.0
    for i in range(20):
        rows.append(_row(49.0, 295.0, y - i * 12))
        rows.append(_row(313.0, 563.0, y - i * 12))
    if with_equation_indent:
        for i in range(3):
            rows.append(_row(283.0, 295.0, 300.0 - i * 12, n=10))
    return rows


def test_the_gutter_is_found_and_not_the_equation_indent():
    """THE CASE BUILT TO FAIL."""
    edge = D._column_edge(_two_column_page(with_equation_indent=True), PAGE)
    assert edge is not None, "no second column found at all"
    assert 300 <= edge <= 320, (
        f"the edge came back at {edge:.1f}; the gutter is at 313 and 283 is a "
        f"display equation's indent inside the LEFT column")


def test_the_gutter_is_still_found_without_the_decoy():
    edge = D._column_edge(_two_column_page(with_equation_indent=False), PAGE)
    assert edge is not None and 300 <= edge <= 320, edge


def test_a_one_column_page_still_has_no_second_column():
    """748's defect, and the reason the guards stay. A single column with an
    indented display equation must not acquire a gutter — every row straddling
    the invented one was cut, and equation 4's denominator came out as
    `\\frac{p_{0\\mid0}}{- p}`."""
    rows = [_row(85.0, 510.0, 700.0 - i * 12) for i in range(20)]
    rows += [_row(280.0, 330.0, 400.0 - i * 12, n=10) for i in range(3)]
    assert D._column_edge(rows, PAGE) is None


def test_no_finished_line_spans_both_columns():
    """What the fix is FOR, at the level the reader's consumers see. A row that
    still holds glyphs from both columns is the defect the Claude.ai chat
    reported as mixed-up columns."""
    rows = _two_column_page(with_equation_indent=True)
    edge = D._column_edge(rows, PAGE)
    out = D._split_at_columns(rows, edge)
    straddling = [r for r in out
                  if r and min(g.rect[0] for g in r) < 295
                  and max(g.rect[2] for g in r) > 313]
    assert straddling == [], (
        f"{len(straddling)} of {len(out)} rows still hold both columns' glyphs")


# --------------------------------------------------------------------------- #
#  The cut itself: a gutter is not a word space, and the bar cannot be absolute
# --------------------------------------------------------------------------- #

def _shift(g, dx: float):
    """The same glyph, moved along x."""
    r = g.rect
    return D.GlyphNode(id=g.id, page=g.page,
                       rect=(r[0] + dx, r[1], r[2] + dx, r[3]),
                       text=g.text, cid=g.cid, glyphname=g.glyphname,
                       fontname=g.fontname, family=g.family, size=g.size,
                       tex=g.tex, stream=g.stream)


def _words(x0: float, y: float, *, words: int, word_pt: float,
           space_pt: float, size: float = SIZE):
    """A row of whole words with real spaces between them."""
    out, x, i = [], x0, 0
    for w in range(words):
        for c in range(4):
            out.append(D.GlyphNode(
                id=f"w{y}_{i}", page=1,
                rect=(x, y, x + word_pt / 4 - 0.2, y + size),
                text="x", cid=120, glyphname="x", fontname="F1", family="F",
                size=size, tex=None, stream=i))
            x += word_pt / 4
            i += 1
        x += space_pt
    return out


def test_a_six_point_gutter_is_a_gutter():
    r"""MEASURED on 2009tiplabeling: the body is 9.6 pt, the second column's
    mode is 300, the left column's text ends at 295 — a gutter of about 6 pt.
    The bar was `gap >= 0.8 * max(g.size for g in row)`, i.e. 7.7 pt for a body
    row and more for any row carrying a big delimiter, so the real gutter never
    cleared it: the edge was found at exactly 295.0 and 9 of 88 lines still
    held both columns.

    An absolute bar cannot do this job — justification stretches a word space
    to 6 pt and more, so no constant separates the two. What separates them is
    that a gutter is the row's OWN widest gap by a clear margin, while a line
    of running text has word spaces that are all much of a muchness."""
    # the left column FILLS its measure, 49..295, and the right starts at 301:
    # a gutter of exactly 6.0 pt. (Shifted into place rather than computed, so
    # the fixture cannot drift away from the number it is named for — the
    # first version of this test left a 53 pt gap and passed against the bug.)
    left = _words(49.0, 700.0, words=7, word_pt=31.0, space_pt=3.2)
    dx = 295.0 - max(g.rect[2] for g in left)
    left = [_shift(g, dx) for g in left]
    row = left + _words(301.0, 700.0, words=7, word_pt=31.0, space_pt=3.2)
    assert max(g.rect[2] for g in left) == pytest.approx(295.0)
    assert min(g.rect[0] for g in row if g.rect[0] > 295) == pytest.approx(301.0)
    out = D._split_at_columns([row], 295.0)
    assert len(out) == 2, (
        f"a 6 pt gutter between two columns of 9.6 pt text was not cut "
        f"({len(out)} row(s) out)")
    assert max(g.rect[2] for g in out[0]) <= 296
    assert min(g.rect[0] for g in out[1]) >= 300


def test_a_full_width_line_of_running_text_is_left_whole():
    """The defect the old bar was protecting against, and it must stay
    protected: a title or caption running straight across the measure has a
    word space over the gutter like any other, and cutting there gives
    `Fig. 6: A heatma` / `p comparing the normalized execution`."""
    row = _words(49.0, 700.0, words=14, word_pt=30.0, space_pt=4.0)
    assert len(D._split_at_columns([row], 295.0)) == 1


def test_a_stretched_justified_space_over_the_gutter_is_left_whole():
    """THE HARD CASE, and why the bar is relative. Full justification stretches
    every space in the line, so the one over the gutter is wide — but so are
    all the others, and that is the evidence."""
    row = _words(49.0, 700.0, words=12, word_pt=28.0, space_pt=7.0)
    assert len(D._split_at_columns([row], 295.0)) == 1


# --------------------------------------------------------------------------- #
#  The edge is a POSITION, and the mode it is chosen by is a 12 pt BUCKET
# --------------------------------------------------------------------------- #

def _measured_page():
    """2009tiplabeling page 1, at the numbers measured off the glyphs.

    Occupancy per 2 pt bin over x: 40-odd glyphs through 300..302, then 0 from
    304 to 310, then 40 again from 310. The left column's text ends at 300.02
    and the right column starts at 311.97 — a gutter 11.95 pt wide on a 10.0 pt
    body.
    """
    rows = []
    for i in range(31):
        rows.append(_row(49.0, 300.02, 700.0 - i * 12, n=45))
        rows.append(_row(311.97, 563.0, 700.0 - i * 12, n=45))
    return rows


def test_the_edge_lands_in_the_gutter_and_not_inside_a_column():
    """THE BUG THIS CASE WAS BUILT FOR.

    `_column_edge` chooses a left-edge mode and the modes are 12 pt buckets:
    `int(311.97 // 12) * 12` is 300. What stood here then returned
    `float(k) - 0.5 * size` — 300 - 5 = 295.0 — reading the bucket LABEL as a
    coordinate and subtracting a margin from it. 295.0 is four points inside
    the left column, whose text ends at 300.02.

    What that cost, measured through the reader: every body row has contiguous
    glyphs across 295 (`t`[287.8,290.6] `h`[290.6,295.6] `e`[295.6,300.0] in
    "...is normally to be part of the foreground..."), so `_split_at_columns`
    found no gap bracketing the edge on 11 of the 13 straddling rows and 15 of
    88 finished lines carried both columns. The splitter was never the fault.
    """
    edge = D._column_edge(_measured_page(), PAGE)
    assert edge is not None
    assert 300.02 < edge < 311.97, (
        f"the edge came back at {edge:.2f}; the left column ends at 300.02 and "
        f"the right starts at 311.97, so anything outside that band is inside "
        f"a column and no row can be cut there")


def test_the_merged_rows_of_the_measured_page_are_cut_at_the_gutter():
    """The page AS THE READER IS HANDED IT. On 2009tiplabeling page 1 thirteen
    of the rows arrived spanning 49..563 and the rest were already one column
    each — which is why the detector has a mode at 312 to find at all. All
    thirteen must come apart, and the clean rows must be left alone.

    (A page whose rows are ALL merged finds no second mode here: the only other
    evidence is a row's own widest internal gap, and that is admitted at
    `1.5 * size`, 14.4 pt against this gutter's 11.95. That bar is a separate
    question and this page does not reach it.)
    """
    rows = [_row(49.0, 300.02, 700.0 - i * 12, n=45)
            + _row(311.97, 563.0, 700.0 - i * 12, n=45)
            for i in range(13)]
    for i in range(13, 31):
        rows.append(_row(49.0, 300.02, 700.0 - i * 12, n=45))
        rows.append(_row(311.97, 563.0, 700.0 - i * 12, n=45))
    edge = D._column_edge(rows, PAGE)
    assert edge is not None and 300.02 < edge < 311.97, edge
    out = D._split_at_columns(rows, edge)
    straddling = [r for r in out
                  if r and min(g.rect[0] for g in r) < 300.0
                  and max(g.rect[2] for g in r) > 312.0]
    assert straddling == [], (
        f"{len(straddling)} of {len(out)} rows still hold both columns "
        f"(edge {edge})")
    assert len(out) == len(rows) + 13, (
        f"13 merged rows should each cut in two: {len(rows)} in, "
        f"{len(out)} out")
