"""
P9-14 (T-0145, 0001124 p9): a paragraph must not begin with an equation number.

WHAT THE PAGE DOES. 0001124 p9 prints seven display-equation numbers down the
right margin, each 95 px wide at x=2347, while the body column runs from x=482
to x=2442. A reader that does not type them `equation_number` emits them as
`text`, and then _body_edges' own principle works against it: an edge is an x
the page RETURNS TO, the page returns to x=2347 seven times, so that x was
admitted as a body edge. Every number then measured 0.1 em from "its own
column's edge", read as a continuation line, and joined the prose — the
inspect page showed a Paragraph beginning `C13J` (the reader's rendering of
`(13)`) followed by the sentence beneath the equation. The owner reported it as
"C13J hrmula (13) is 9imply n book-keeping dev".

THE RULE, and why repetition and not single-line geometry. A single line's
geometry cannot separate a stranded equation number from the last line of a
right column whose edge fell below the frequency floor: measured over 300
library readings (405,890 prose lines), "more than half the column span right
of the edge and under a fifth of it wide" catches 6,159 lines of which 304 are
real prose ('f is contained in', 'significance.', 'John Stillwell').

Repetition can. An x the page returns to, where EVERY line is narrower than
4 em and the column sits in the right half of the body span, is a fragment
column — an equation-number gutter — and none of its lines is prose. Measured
over 900 readings / 1,296,572 prose lines: 128 pages of 34,939 (0.37%) declare
one, holding 853 lines (0.066% of prose), of which 24 (2.8%) contain a word of
four letters or more, and those are table-column fragments ('Drawdown',
'Stabilized'), not running prose. A two-column page cannot trip it: its right
column's lines are wide.

NOTHING IS LOST. The line stays in the mathpix_lines stream, and
UnclaimedLineProcessor (procOrder 998) gives every record no module claimed its
own ReadingRecord object with its own type and region, byte for byte. The
number does not vanish from the model; it stops being a sentence.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document
from docmodel.modules.page import ingest_lines_json
from docmodel.modules.paragraph import ParagraphProcessor
from docmodel.base_module import ModuleConfig

EM = 60


def _mod():
    return ParagraphProcessor(
        ModuleConfig(title="ParagraphProcessor",
                     classname="ParagraphProcessor", proc_order=13), "T")


def _line(lid, text, x, y, w, h=EM, ltype="text"):
    return {"id": lid, "type": ltype, "text": text, "text_display": text,
            "region": {"top_left_x": x, "top_left_y": y,
                       "width": w, "height": h}}


def _paragraphs(lines):
    doc = Document()
    ingest_lines_json(doc, {"source": "glyphdrill3", "pages": [
        {"page": 9, "image_id": "t-9", "page_width": 3400,
         "page_height": 4400, "lines": lines}]})
    # a paragraph item's "lines" are (anchor, text, payload) triples
    return [[t for _, t, _ in it["lines"]]
            for it in _mod().find_items(doc)]


def _p9_lines():
    """The shape of 0001124 p9: prose at the body edge, equation numbers in the
    right gutter, each number following the prose block it belongs to."""
    lines, y = [], 560
    for blk in range(7):
        for i in range(2):
            lines.append(_line(f"l{blk}_{i}",
                               f"prose line {blk}.{i} running to the margin",
                               482, y, 1960))
            y += 74
        lines.append(_line(f"n{blk}", f"C1{blk}J", 2347, y, 95))
        y += 120
    return lines


def test_an_equation_number_gutter_never_enters_a_paragraph():
    paras = _paragraphs(_p9_lines())
    assert paras, "the page's prose must still become paragraphs"
    joined = ["".join(p) for p in paras]
    for text in joined:
        assert not text.lstrip().startswith("C1"), \
            f"a paragraph begins with an equation number: {text[:60]!r}"
        assert "C1" not in text, \
            f"an equation number rode into a paragraph: {text[:80]!r}"


def test_the_prose_itself_survives_in_full():
    lines = _p9_lines()
    want = {l["text"] for l in lines if l["text"].startswith("prose")}
    got = {t for p in _paragraphs(lines) for t in p}
    assert want <= got, f"prose lost: {sorted(want - got)[:3]}"


def test_a_two_column_page_is_not_a_fragment_column():
    """The control the single-line rule failed: a right column whose short last
    line looks stranded. Its column's lines are wide, so it is not a gutter."""
    lines, y = [], 560
    for i in range(6):
        lines.append(_line(f"L{i}", f"left column line {i} to the margin",
                           100, y, 800))
        lines.append(_line(f"R{i}", f"right column line {i} to the margin",
                           1000, y, 800))
        y += 74
    lines.append(_line("Rlast", "right column tail.", 1000, y, 200))
    got = {t for p in _paragraphs(lines) for t in p}
    assert "right column tail." in got, \
        "a short last line of a right column must stay prose"
    assert "right column line 3 to the margin" in got


def test_a_page_without_a_gutter_is_unchanged():
    """No recurring narrow right-margin column: every prose line contributes,
    so the rule costs nothing on an ordinary page."""
    lines, y = [], 560
    for i in range(8):
        lines.append(_line(f"p{i}", f"ordinary prose line {i}", 482, y, 1960))
        y += 74
    got = [t for p in _paragraphs(lines) for t in p]
    assert len(got) == 8, f"expected all 8 prose lines, got {len(got)}"


def test_a_page_of_only_narrow_columns_keeps_its_edges():
    """The fallback. If every recurring column on a page is narrower than
    `_GUTTER_EM`, there is no text column to measure a gutter against, so the
    narrowness says nothing -- and dropping those edges would switch the indent
    rule off for the page. 10 pages of 35,095 in the 900-reading sample reach
    this branch; they must keep behaving as they did."""
    from docmodel.modules.paragraph import _body_edges, _PROSE_TYPES

    class _Stream:
        def __init__(self, payload):
            self.payload = payload
            self.anchors = list(payload)

    payload, y = {}, 560
    for i in range(8):                       # two narrow columns, 2 em wide
        for col, x in enumerate((100, 400)):
            payload[f"a{i}{col}"] = {
                "type": "text", "_page": 1,
                "region": {"top_left_x": x, "top_left_y": y,
                           "width": 2 * EM, "height": EM}}
        y += 74
    edges = _body_edges(_Stream(payload), _PROSE_TYPES)
    assert 1 in edges, "the page lost its edges entirely"
    cols, em, gutters, lines_at = edges[1]
    assert len(cols) == 2, cols
    assert gutters == [], "a page with no text column declares no gutter"
    #: The counts travel with the edges on this branch too -- a page that
    #: reaches it must not arrive upstairs without its evidence, or
    #: `_is_first_line` is back to guessing which edge is the body.
    assert set(lines_at) == set(cols), lines_at
    assert all(n >= 1 for n in lines_at.values()), lines_at
