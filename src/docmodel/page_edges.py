"""
page_edges — the page's own geometry, in one place, because two modules read it.

AN EDGE IS AN X THE PAGE RETURNS TO. That one sentence is the whole principle:
the left edges of a page's prose lines are bucketed, and a bucket the page
returns to often enough is a body edge. It works in points (a text layer, ~11
pt lines), in MathPix pixels (~42) and in the glyph reader's 400 dpi pixels
(60), because every threshold here is expressed in `em` -- the median line
height -- and never in absolute units nor as a fraction of a page width that
nobody passed in.

`ParagraphProcessor` (procOrder 13) found these rules; `EquationProcessor`
(procOrder 11) now reads the same ones to decide which declined rows carry an
equation number. Two copies of a measured rule drift, so there is one. The
measurements and the defect behind each constant stay in the docstrings below,
where the rule is, rather than in whichever module happened to need it first.
"""
from __future__ import annotations

import re
import statistics


# P9-14 — a fragment column: every line at a recurring x narrower than this
# many em, and the column standing this far along the body span. Both chosen by
# measurement over 900 library readings; `_body_edges` carries the numbers.
_GUTTER_EM = 4.0
_GUTTER_FRAC = 0.5


def _body_edges(stream, prose_types) -> dict:
    """Per page: the body text's LEFT EDGES -- one per column -- the distance a
    line has to clear to read as a paragraph's FIRST line, and the page's
    FRAGMENT COLUMNS.

    A paragraph break is a typographic fact, and the reading may not state it.
    MathPix states it with a leading blank in `text_display`; the enriched
    keyless OCR path states it with `par_num`. THE PDF'S OWN TEXT LAYER STATES
    NEITHER, so every prose line on a page joined one paragraph: 11 pages of a
    two-column paper came out as 12 Paragraph objects, and the markdown was 13
    lines at a median of 1,688 characters (arxiv.2602.06992, 2026-11-10).

    What the page itself states is the INDENT. A first line starts an em or two
    right of its column's body edge; a continuation starts at the edge. An edge
    is an x the page RETURNS TO, so it is found by frequency -- a first-line
    indent is used once per paragraph and never dominates.

    The threshold is the median line HEIGHT, which is one em in whatever units
    the reading uses: points for the text layer (~11pt), pixels for MathPix
    (~42px). So no page width is needed and both readings are measured alike.

    AN X THE PAGE RETURNS TO IS NOT ALWAYS A COLUMN OF TEXT (P9-14). 0001124 p9
    prints seven display-equation numbers down the right margin, each 95 px
    wide at x=2347, and a reader that types them `text` rather than
    `equation_number` makes that x one the page returns to seven times -- so it
    was admitted here as a body edge, every number then measured 0.1 em from
    "its own column's edge", read as a continuation line, and joined the prose.
    The owner saw a Paragraph beginning `C13J`, the reader's rendering of
    `(13)`, welded to the sentence under the equation.

    So a recurring x is split in two. It is a BODY EDGE when the lines there
    are lines of text, and a FRAGMENT COLUMN when EVERY line there is narrower
    than `_GUTTER_EM` and the column stands right of the middle of the body
    span (`_GUTTER_FRAC` of the distance from the leftmost edge to the furthest
    ink). The second kind is an equation-number gutter and holds no prose.

    REPETITION IS THE SIGNAL, and single-line geometry is not. Measured over
    300 library readings (405,890 prose lines), the single-line form of this
    test -- more than half the column span right of the edge and under a fifth
    of it wide -- catches 6,159 lines of which 304 are real prose: `f is
    contained in`, `significance.`, `John Stillwell`, all of them lines of a
    right column whose own edge fell below the frequency floor. Requiring the
    narrowness to RECUR costs that nothing: over 900 readings (1,296,572 prose
    lines) 128 pages of 34,939 (0.37%) declare a gutter, holding 853 lines
    (0.066% of prose), of which 24 (2.8%) contain a word of four letters or
    more -- and those are table-column fragments (`Drawdown`, `Stabilized`),
    not running prose. A two-column page cannot trip it: its right column's
    lines are wide, so the column fails the width test and stays a body edge.
    """
    per_page: dict = {}
    for anchor in stream.anchors:
        payload = stream.payload[anchor]
        if payload.get("type") not in prose_types:
            continue
        region = payload.get("region") or {}
        x, h = region.get("top_left_x"), region.get("height")
        if x is None:
            continue
        per_page.setdefault(payload.get("_page"), []).append(
            (float(x), float(h or 0), float(region.get("width") or 0)))

    out: dict = {}
    for page, rows in per_page.items():
        xs = [x for x, _, _ in rows]
        hs = [h for _, h, _ in rows if h > 0]
        rows = [(x, w) for x, _, w in rows]
        if not hs or len(xs) < 4:
            continue
        em = statistics.median(hs)
        if em <= 0:
            continue
        step = max(em * 0.5, 0.5)

        buckets: dict = {}
        for x, w in rows:
            buckets.setdefault(int(round(x / step)), []).append(w)
        floor = max(3, int(0.10 * len(xs)))
        recurring = {k: ws for k, ws in buckets.items() if len(ws) >= floor}
        edges = sorted(k * step for k, ws in recurring.items()
                       if max(ws) > _GUTTER_EM * em)
        if not edges:
            # EVERY recurring column on this page is narrow, so there is no
            # text column to measure a gutter against and the narrowness says
            # nothing. Keep what the frequency test alone found and declare no
            # gutter, rather than leaving the page with no edges at all: that
            # would silently switch the indent rule off for it. 10 pages of
            # 35,095 in the 900-reading sample reach this branch (0.03%) --
            # narrow-column pages in two reference works and a review article.
            narrow = sorted(k * step for k in recurring)
            out[page] = (narrow, em, [],
                         {k * step: len(ws) for k, ws in recurring.items()})
            continue
        # The furthest ink on the page, not the page width: the frame is the
        # data's, and a reading states its own units (eqlist's declared frame).
        reach = max(x + w for x, w in rows)
        span = reach - edges[0]
        gutters = sorted(
            k * step for k, ws in recurring.items()
            if max(ws) <= _GUTTER_EM * em
            and span > 0 and (k * step - edges[0]) / span > _GUTTER_FRAC)
        #: THE COUNT IS EVIDENCE AND IT TRAVELS WITH THE EDGE.
        #:
        #: An edge is an x the page RETURNS TO, and how often it returns is
        #: what tells a BODY edge from a first-line INDENT: body text uses its
        #: edge on every line, an indent once per paragraph. That number is
        #: computed here, in `recurring`, and it used to be dropped on the
        #: floor -- so every caller got a bare list of x values and had to
        #: guess which one was the body.
        #:
        #: `_is_first_line` guessed "the rightmost", which is right for a
        #: hanging indent and exactly wrong for an ordinary one. On
        #: lib:008d43e5db48 the edges are 464 with 27 lines and 512 with 9:
        #: the body is 464, the rightmost is the indent, and the guess turned
        #: 370 pages of prose into one paragraph per line (2,501 objects ->
        #: 7,904, and +56 % over the ten-document set). Reverted in af1e996b.
        #:
        #: A lower layer that can only offer CANDIDATES must say so by handing
        #: up the evidence, not by picking one and hoping. This dict is that
        #: evidence: edge x -> the number of prose lines that start there.
        out[page] = (edges, em, gutters,
                     {k * step: len(ws) for k, ws in recurring.items()})
    return out


def _in_a_gutter(x, page, edges: dict) -> bool:
    """True when the line stands in one of its page's fragment columns -- an
    equation-number gutter, not prose. See `_body_edges`."""
    if x is None or page not in edges:
        return False
    _cols, em, gutters = edges[page][:3]
    return any(abs(float(x) - g) <= em * 0.5 for g in gutters)


#: P9-21 — a word, for the purpose of deciding whether a line is a sentence:
#: three or more letters in a row. Not digits, not single letters, not
#: punctuation. `17` is not a word; `2m2G` is not a word; `From` is.
_SENTENCE_WORD = re.compile(r"[^\W\d_]{3,}", re.UNICODE)


def _at_an_edge(x, page, edges: dict) -> bool:
    """True when the line starts at one of its page's body edges — which every
    line of a paragraph does, because an edge IS an x the page returns to."""
    if x is None or page not in edges:
        return False
    cols, em, _gutters = edges[page][:3]
    return any(abs(float(x) - c) <= em * 0.5 for c in cols)


def _edge_bands(stream, prose_types) -> dict:
    """page -> the y-bands of the records that DO stand at a body edge.

    A record that shares its band with a line of running text is part of that
    row — a stub at the end of a paragraph, a label beside prose — and is not
    judged alone. Nothing here depends on the record's own text.
    """
    out: dict = {}
    edges = _body_edges(stream, prose_types)
    for a in stream.anchors:
        payload = stream.payload[a] or {}
        if payload.get("type") not in prose_types:
            continue
        page = payload.get("_page")
        region = payload.get("region") or {}
        x, y, h = (region.get("top_left_x"), region.get("top_left_y"),
                   region.get("height"))
        if x is None or y is None or not _at_an_edge(x, page, edges):
            continue
        out.setdefault(page, []).append((float(y), float(y) + float(h or 0)))
    return out


def _shares_a_band(y, h, page, bands: dict) -> bool:
    if y is None:
        return False
    y0 = float(y)
    y1 = y0 + float(h or 0)
    return any(b0 < y1 and b1 > y0 for b0, b1 in bands.get(page, ()))


def _is_not_a_sentence(text, x, y, h, page, edges: dict, bands: dict) -> bool:
    """P9-21 — the line is NOT PROSE, and the test never guesses what it is.

    Three conditions, all of them necessary:

      1. it holds no word of three or more letters;
      2. it starts at none of its page's body edges — every line of a
         paragraph starts at one, by the definition of an edge;
      3. no line that DOES start at an edge shares its band.

    `EquationProcessor.EQ_TYPES` is {"equation", "math"}, so a display row the
    reader typed `text` can never become an Equation; `ParagraphProcessor`
    runs two slots later and used to take it as prose. On page 9 of 0001124
    that is `l16` (equation 14, one record) and `l35`/`l36`/`l37` (equation 20,
    three records on one row), plus the page number `9`.

    WHAT THIS RULE REFUSES TO DO is decide that such a row is mathematics.
    Measured over 33 random library documents, a promoting rule — inset,
    alone, few long words — picked 500 lines of which about half were display
    maths and ABOUT A THIRD WERE PAGE NUMBERS (`17`, `18`, `31`, `244`, `ii`),
    plus a bare equation number and two empty records. Nothing in a line
    separates `17` from `2m2G`; what separates them is that a page number
    recurs at the same place across pages, which is `HeaderProcessor`'s
    business. A rule that promoted both would be worse than the defect.

    So this one only declines. The record then reaches
    `UnclaimedLineProcessor` (procOrder 998) and becomes a `ReadingRecord`
    with its own type and region, byte for byte, which is the honest label for
    a display row and for a page number alike until something can tell them
    apart. Nothing is lost, and nothing is asserted.

    The calibration that produced the numbers above also produced a retraction
    worth leaving here: labelling these records by the library's own
    `*.equations.json` regions inverts them — the reference calls
    `doi:10.1145/1198555.1198667.` a display equation and
    `g(x,y) := kx - yk. (1-6)` prose. Those regions do not align with these
    readings, so no count derived from them is usable.
    """
    if _SENTENCE_WORD.search(text or ""):
        return False
    # NO GEOMETRY IS NOT EVIDENCE OF INSET GEOMETRY. A record with no region,
    # or a page whose records have none, cannot be judged by where it stands,
    # and `_at_an_edge` answers False for both -- which this rule would
    # otherwise read as "stands at no edge", the opposite of what is known.
    # tests/test_basic.py::test_paragraph_grouping_breaks_on_non_text_lines
    # carries four region-less text lines and caught this: every one of them
    # was declined and the page produced 0 paragraphs instead of 2. Readings
    # without regions are real, so the guard is not about the test.
    if x is None or y is None or page not in edges:
        return False
    if _at_an_edge(x, page, edges):
        return False
    return not _shares_a_band(y, h, page, bands)


