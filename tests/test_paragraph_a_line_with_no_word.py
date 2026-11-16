"""
P9-21 (T-0145, 0001124 p9): a line with no word in it is not a sentence.

WHAT THE PAGE DOES. `EquationProcessor.EQ_TYPES` is {"equation", "math"}, so a
display row the reader typed `text` can never become an Equation;
`ParagraphProcessor` runs two slots later (11 -> 13) and took it as prose. On
page 9 of 0001124 that is `l16` (equation 14, one record, "G(x,y;g;t) = ..."),
`l35`/`l36`/`l37` (equation 20, three records on ONE row), `l21` (the second
half of equation 16) and the page number `9`. The owner reported it as "mots
boxes are labeled as paragraph which is wrong".

THE RULE DECLINES AND NEVER PROMOTES, and the measurement is why. A promoting
rule -- inset, alone in its band, few long words, re-typed to `math` so
EquationProcessor would claim it -- was calibrated first and abandoned. Over 33
random library documents it picked 500 lines: about half were display maths
rows or fragments of them ('eta := eta [iota - eta(iota)] (3.1)', 'A-P S =
-sqrt(A2 +RS) (6.3)'), and ABOUT A THIRD WERE PAGE NUMBERS -- 17, 18, 31, 10,
39, 244, ii -- plus a bare equation number '(2.8)' and two empty records.
Promoting a page number to an Equation is worse than the defect it was meant to
fix. Nothing inside a line separates `17` from `2m2G`; what separates them is
that a page number recurs at the same place across pages, which is
`HeaderProcessor`'s business and not a content test's.

So this rule only takes the wrong label off. Three necessary conditions:
no word of three or more letters; the line starts at NONE of its page's body
edges (every line of a paragraph starts at one, by the definition of an edge --
an edge is an x the page returns to); and no line that DOES start at an edge
shares its band. The record then reaches UnclaimedLineProcessor (procOrder 998)
and becomes a ReadingRecord with its own type and region, byte for byte, which
is the honest label for a display row and for a page number alike until
something can tell them apart.

MEASURED, over 120 random library readings (294,318 prose-typed records):
10,868 declined, 3.69%. A random 40 of them were read by hand and NOT ONE is a
real sentence -- maths rows and fragments, page numbers, equation numbers,
Miller indices '(011)' '(200)', brace glyphs, bare letters.

AND A RETRACTION, left here because the number was published before it was
checked: labelling these records by the library's own `*.equations.json`
display regions INVERTS them. The reference calls
'doi:10.1145/1198555.1198667.' and 'R. Loll \\({ }^{1}\\)' display equations,
and 'g(x,y) := kx - yk. (1-6)' and '< x | x > >= 0 (1-8)' prose. Those regions
do not align with these readings, so the "10,819 display rows landing in prose"
derived from them is void. A ratio computed from a wrong label looks exactly
like a ratio computed from a right one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document
from docmodel.modules.page import ingest_lines_json
from docmodel.modules.paragraph import ParagraphProcessor
from docmodel.base_module import ModuleConfig

EM = 60
EDGE = 482          # the body column's left edge, as on 0001124 p9
BODY_W = 1960


def _mod():
    return ParagraphProcessor(
        ModuleConfig(title="ParagraphProcessor",
                     classname="ParagraphProcessor", proc_order=13), "T")


def _line(lid, text, x, y, w, h=EM, ltype="text"):
    return {"id": lid, "type": ltype, "text": text, "text_display": text,
            "region": {"top_left_x": x, "top_left_y": y,
                       "width": w, "height": h}}


def _items(lines):
    doc = Document()
    ingest_lines_json(doc, {"source": "glyphdrill3", "pages": [
        {"page": 9, "image_id": "t-9", "page_width": 3400,
         "page_height": 4400, "lines": lines}]})
    return _mod().find_items(doc)


def _texts(lines):
    # a paragraph item's "lines" are (anchor, text, payload) triples
    return [[t for _, t, _ in it["lines"]] for it in _items(lines)]


def _prose(n=8, start=560):
    """n lines of running text at the body edge -- enough for the frequency
    rule to find the edge (floor = max(3, 10% of the lines))."""
    out, y = [], start
    for i in range(n):
        out.append(_line(f"p{i}", f"prose line {i} running to the right margin",
                         EDGE, y, BODY_W))
        y += 74
    return out


def test_a_display_row_the_reader_typed_text_leaves_the_prose():
    """0001124 p9 l16: equation 14, one record, inset and alone on its row."""
    lines = _prose()
    lines.append(_line("l16", "G(x,y;g;t) = G(gx,y;g;t-1).", 895, 1640, 1135))
    lines += [_line(f"q{i}", f"more prose {i} running to the right margin",
                    EDGE, 1800 + 74 * i, BODY_W) for i in range(3)]
    joined = ["".join(p) for p in _texts(lines)]
    assert joined, "the prose must still become paragraphs"
    for text in joined:
        assert "G(x,y;g;t)" not in text, \
            f"a display row rode into a paragraph: {text[:80]!r}"


def test_three_records_on_one_row_all_leave():
    """0001124 p9 l35/l36/l37: equation 20 is three records in ONE band. A rule
    that judged only the first would leave two of them in the prose."""
    lines = _prose()
    y = 1640
    for lid, txt, x in (("l35", "A = 1 - F2t+2,", 640),
                        ("l36", "B = F(1 - F2t),", 1130),
                        ("l37", "C = F2(1 - F2t-2).", 1650)):
        lines.append(_line(lid, txt, x, y, 420))
    joined = ["".join(p) for p in _texts(lines)]
    for text in joined:
        for frag in ("A = 1 -", "B = F(1", "C = F2(1"):
            assert frag not in text, \
                f"{frag!r} rode into a paragraph: {text[:80]!r}"


def test_the_page_number_is_not_a_sentence_either():
    """And that is correct. A page number is not prose; ReadingRecord is the
    honest label for it until HeaderProcessor's recurrence test names it."""
    lines = _prose()
    lines.append(_line("l1", "9", 2420, 420, 30))
    joined = "".join("".join(p) for p in _texts(lines))
    assert "9" not in joined.replace("prose line 9", ""), \
        "the page number stayed in the prose"


def test_the_prose_itself_survives_in_full():
    lines = _prose(n=10)
    lines.append(_line("l16", "F(x) = x.", 1200, 1200, 300))
    kept = " ".join(t for p in _texts(lines) for t in p)
    for i in range(10):
        assert f"prose line {i} running" in kept, \
            f"prose line {i} was lost"


def test_a_line_at_a_body_edge_is_never_declined():
    """Every line of a paragraph starts at a body edge, so the edge test is
    what protects paragraph interiors. A short wordless line AT the edge --
    'x = 5' ending a paragraph -- stays where the page put it."""
    lines = _prose(n=6)
    lines.append(_line("e1", "x = 5", EDGE, 560 + 74 * 6, 240))
    lines += [_line(f"r{i}", f"tail prose {i} running to the right margin",
                    EDGE, 1200 + 74 * i, BODY_W) for i in range(3)]
    joined = "".join("".join(p) for p in _texts(lines))
    assert "x = 5" in joined, \
        "a wordless line at the body edge was declined; paragraph interiors " \
        "are no longer safe"


def test_a_wordless_line_sharing_a_band_with_prose_is_kept():
    """A stub beside running text is part of that row, not a display line."""
    lines = _prose(n=8)
    y = 560 + 74 * 3                       # the band of prose line 3
    lines.append(_line("stub", "(a)", 2500, y, 120))
    joined = "".join("".join(p) for p in _texts(lines))
    assert "(a)" in joined, \
        "a stub sharing its band with prose was declined"


def test_nothing_is_claimed_to_be_mathematics():
    """The rule declines; it does not re-type. The record keeps the type the
    reader gave it, so procOrder 998 can hand it on byte for byte."""
    lines = _prose()
    lines.append(_line("l16", "G(x,y;g;t) = G(gx,y;g;t-1).", 895, 1640, 1135))
    doc = Document()
    ingest_lines_json(doc, {"source": "glyphdrill3", "pages": [
        {"page": 9, "image_id": "t-9", "page_width": 3400,
         "page_height": 4400, "lines": lines}]})
    _mod().find_items(doc)
    stream = doc.stream(ParagraphProcessor.LINES_STREAM)
    types = {(stream.payload[a] or {}).get("type") for a in stream.anchors}
    assert types == {"text"}, \
        f"the rule re-typed a record instead of declining it: {types}"


def test_the_counter_names_what_happened():
    lines = _prose()
    lines.append(_line("l16", "G(x,y;g;t) = G(gx,y;g;t-1).", 895, 1640, 1135))
    mod = _mod()
    doc = Document()
    ingest_lines_json(doc, {"source": "glyphdrill3", "pages": [
        {"page": 9, "image_id": "t-9", "page_width": 3400,
         "page_height": 4400, "lines": lines}]})
    mod.find_items(doc)
    assert mod.counters.get("lines_with_no_word_are_not_prose") == 1, \
        f"counter missing or wrong: {dict(mod.counters)}"


def test_a_reading_with_no_regions_keeps_its_paragraphs():
    """NO GEOMETRY IS NOT EVIDENCE OF INSET GEOMETRY, and this is the bug the
    first version of the rule shipped with.

    `_at_an_edge` answers False for a record with no region and for a page that
    has no edges, which the rule read as "stands at no edge" -- the opposite of
    what is known. tests/test_basic.py's four region-less text lines were all
    declined and the page produced 0 paragraphs instead of 2. The full suite
    caught it; the 9 tests above did not, because every one of them builds
    regions.
    """
    lines = [{"id": i, "type": "text", "text": t, "text_display": t}
             for i, t in (("a", "A1"), ("b", "A2"), ("c", "B1"))]
    doc = Document()
    ingest_lines_json(doc, {"pages": [
        {"page": 1, "image_id": "i", "lines": lines}]})
    items = _mod().find_items(doc)
    kept = [t for it in items for _, t, _ in it["lines"]]
    assert kept == ["A1", "A2", "B1"], \
        f"region-less lines were declined: {kept}"
