"""
P9-22 (T-0145, 0001124 p9): a declined row with an equation NUMBER in its band
is an equation, and the number is the evidence.

`EquationProcessor.EQ_TYPES` is {"equation", "math"}, so a display row the
reader typed `text` could never become an Equation. P9-21 stopped calling such
a row prose, which was right and not enough: it ended as a `ReadingRecord`, and
the owner's report was that the boxes say paragraph where a formula is.

WHY THIS IS NOT THE RULE THAT WAS MEASURED AND THROWN AWAY. A line-local
promoting test -- inset, alone in its band, few long words -- was built first
and abandoned. Over 33 random library documents it picked 500 lines of which
about a third were PAGE NUMBERS (17, 18, 31, 244, ii). Nothing inside a line
separates `17` from `2m2G`.

So this pass asks a different question: not "does this line look like
mathematics" but "is there a printed equation number standing beside it". The
numbers come from P9-14's fragment column, itself a repetition rule -- an x the
page returns to where every line is narrow. A page number stands alone in a
header or footer with nothing beside it, so it cannot be promoted here.

AND THE NUMBER MUST LOOK LIKE A NUMBER, which the first version did not check.
Over 120 random library readings that version promoted 6 rows, all six from one
page (1511.08771 p65), and all six wrong: a table of tuples against counts,
`(010000),` paired with `351`. P9-14's column rule found the narrow recurring
numeric column and called it an equation-number gutter -- true of a page of
prose columns, not of a column of bare numbers. `351` is not an equation
number; `(13)` is. An equation number is printed in brackets, which is a
typesetting convention checkable in the ink. With the bracket test, the same
120 readings promote 0 rows and page 9 still promotes all 5.

MEASURED on page 9 (reading 6516bc35, pdfdrill with this pass): Equation 6 ->
11, ReadingRecord 13 -> 8, Paragraph 9 -> 9, total objects 31 -> 31 (nothing
lost), display rows that are NOT in an Equation box 2 -> 0, prose CER 0.33%
unchanged, 401/401 word boxes claimed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.base_module import ModuleConfig
from docmodel.core import Document
from docmodel.modules.equation import EquationProcessor
from docmodel.modules.page import ingest_lines_json

EM = 60
EDGE = 482
BODY_W = 1960
GUTTER_X = 2347          # the right margin, as on 0001124 p9


def _mod():
    return EquationProcessor(
        ModuleConfig(title="EquationProcessor",
                     classname="EquationProcessor", proc_order=11), "T")


def _line(lid, text, x, y, w, h=EM, ltype="text"):
    return {"id": lid, "type": ltype, "text": text, "text_display": text,
            "region": {"top_left_x": x, "top_left_y": y,
                       "width": w, "height": h}}


def _doc(lines):
    doc = Document()
    ingest_lines_json(doc, {"source": "glyphdrill3", "pages": [
        {"page": 9, "image_id": "t-9", "page_width": 3400,
         "page_height": 4400, "lines": lines}]})
    return doc


def _page(rows, numbers):
    """A page of prose with `rows` inset display rows and `numbers` in the
    right gutter. The gutter needs enough lines to recur (floor = max(3, 10%)).
    """
    lines, y = [], 560
    for i in range(8):
        lines.append(_line(f"p{i}", f"prose line {i} running to the margin",
                           EDGE, y, BODY_W))
        y += 74
    for lid, text, x, ry in rows:
        lines.append(_line(lid, text, x, ry, 1100))
    for lid, text, ry in numbers:
        lines.append(_line(lid, text, GUTTER_X, ry, 95))
    return lines


def _items(lines):
    return _mod().find_items(_doc(lines))


def _latex(items):
    return [it.get("latex_raw") or "" for it in items]


def test_a_display_row_with_a_number_in_its_band_becomes_an_equation():
    items = _items(_page(
        rows=[("l16", "G(x,y;g;t) = G(gx,y;g;t-1).", 895, 1640)],
        numbers=[("n14", "(13)", 1300), ("n15", "(14)", 1645),
                 ("n16", "(15)", 1900), ("n17", "(16)", 2150)]))
    assert "G(x,y;g;t) = G(gx,y;g;t-1)." in _latex(items), \
        f"the display row did not become an Equation: {_latex(items)}"


def test_the_number_in_the_band_is_the_one_it_carries():
    items = _items(_page(
        rows=[("l16", "G(x,y;g;t) = G(gx,y;g;t-1).", 895, 1640)],
        numbers=[("n14", "(13)", 1300), ("n15", "(14)", 1645),
                 ("n16", "(15)", 1900), ("n17", "(16)", 2150)]))
    got = [it for it in items if "G(x,y" in (it.get("latex_raw") or "")]
    assert got and got[0]["refnum"] == "(14)", \
        f"wrong number paired: {[(i.get('refnum')) for i in items]}"


def test_a_page_number_is_never_promoted():
    """The page number stands alone; nothing is beside it in the gutter."""
    lines = _page(rows=[("l1", "9", 2420, 420)],
                  numbers=[("n1", "(13)", 1300), ("n2", "(14)", 1645),
                           ("n3", "(15)", 1900), ("n4", "(16)", 2150)])
    assert "9" not in _latex(_items(lines)), \
        "a page number was promoted to an Equation"


def test_a_bare_number_in_the_gutter_is_not_an_equation_number():
    """1511.08771 p65: a table of tuples against counts. The first version
    promoted all six of its rows, in the only document it promoted anything at
    all. `351` is not an equation number."""
    lines = _page(
        rows=[("t1", "(010000),", 900, 1640), ("t2", "(1000),", 900, 1714),
              ("t3", "(01000),", 900, 1788), ("t4", "(10000),", 900, 1862)],
        numbers=[("c1", "351", 1640), ("c2", "5", 1714),
                 ("c3", "15", 1788), ("c4", "6", 1862)])
    got = _latex(_items(lines))
    assert not any("0000" in g for g in got), \
        f"a table row was promoted on the evidence of a bare count: {got}"


def test_several_rows_in_one_band_are_all_promoted_and_none_numbered():
    """Equation 20 on p9 is three records on one row. One number cannot label
    three Equations, and guessing which gets it would invent a fact."""
    lines = _page(
        rows=[("l35", "A = 1 - F2t+2,", 640, 1640),
              ("l36", "B = F(1 - F2t),", 1130, 1640),
              ("l37", "C = F2(1 - F2t-2).", 1650, 1640)],
        numbers=[("n1", "(13)", 1300), ("n2", "(20)", 1645),
                 ("n3", "(15)", 1900), ("n4", "(16)", 2150)])
    items = _items(lines)
    got = _latex(items)
    for frag in ("A = 1 -", "B = F(1", "C = F2(1"):
        assert any(frag in g for g in got), f"{frag!r} was not promoted: {got}"
    numbered = [it["refnum"] for it in items if it.get("refnum") == "(20)"]
    assert not numbered, \
        "one number was handed to one of three rows sharing its band"


def test_a_band_that_already_holds_maths_keeps_its_number_for_the_maths():
    """p9 equation 16 is `F_t(x) = …` typed `math` and `F_0(x) = x.` typed
    `text`, on one row. The declined row is promoted; the number stays with
    the reading's own maths."""
    lines = _page(rows=[("l21", "Fo(x) = x.", 1650, 1640)],
                  numbers=[("n1", "(13)", 1300), ("n2", "(16)", 1645),
                           ("n3", "(17)", 1900), ("n4", "(18)", 2150)])
    lines.append({"id": "m7", "type": "math", "text": "F_t(x)",
                  "text_display": r"\[ F_t(x) = \frac{g}{1-gF_{t-1}(x)} \]",
                  "region": {"top_left_x": 995, "top_left_y": 1630,
                             "width": 600, "height": 150}})
    items = _items(lines)
    promoted = [it for it in items if "Fo(x)" in (it.get("latex_raw") or "")]
    assert promoted, "the declined row was not promoted"
    assert promoted[0]["refnum"] == "", \
        f"the number was taken from the reading's own maths: {promoted[0]['refnum']!r}"


def test_a_row_with_no_number_beside_it_is_left_alone():
    lines = _page(rows=[("l9", "F(x) = x.", 1200, 1200)],
                  numbers=[("n1", "(13)", 1640), ("n2", "(14)", 1714),
                           ("n3", "(15)", 1788), ("n4", "(16)", 1862)])
    assert "F(x) = x." not in _latex(_items(lines)), \
        "a row with no number in its band was promoted anyway"


def test_a_reading_the_module_cannot_measure_promotes_nothing():
    """No regions, so no bands and no gutter: NO GEOMETRY IS NOT EVIDENCE.
    The same guard P9-21 shipped without and the suite caught."""
    lines = [{"id": i, "type": "text", "text": t, "text_display": t}
             for i, t in (("a", "A1"), ("b", "(13)"), ("c", "x = 1"))]
    items = _items(lines)
    assert not items, f"something was promoted without geometry: {_latex(items)}"
