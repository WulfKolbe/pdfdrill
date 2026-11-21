r"""A list item's continuation is never many em LEFT of its own marker.

T-0154. `ListProcessor` claims a lexical marker line and then folds in every
following line whose `subtype` says `continues_line_*`. The reading states
that join and the module trusts it, which is right — except that the reading
also stamps it across a centred heading onto the body prose underneath.

MEASURED on the ten-document Gemma4 set at 6980ef0 (inklines), over all 24
lexical items that have a stated tail. The quantity is how many em the tail's
left edge stands LEFT of the marker's, em being the page's median line height
as `page_edges._body_edges` measures it:

    18.8 em   lib:d68e p88   '9. Communication Between Systems 77'   16 lines
    10.3 em   BH3 p155       '1. Konsequenzen und Fragen'            31 lines
     9.5 em   BH3 p37        '1. Projektionen in Zeit und Raum'      15 lines
    ----------------------------------------------------------------- gap
     1.8 em   lib:d68e p372  '2005. Springer.'                        2 lines
     1.5 em   lib:c9daf p236 '* If \(u\) is invertible ...'           2 lines
     1.2 em   lib:008d p334  '• Der Äther, ein ubiquitäres ...'       6 lines
      ...     and seventeen more, all under 1 em

The three above the gap are a chapter heading, a chapter heading and a running
head with its folio; each stands alone, centred, and the body column beneath
it begins at the column's own left edge. Each had the WHOLE REST OF THE PAGE
folded into it: on BH3 p37 the ListItem read "Projektionen in Zeit und Raum
Aus der Exponentenmenge ..." and 48 of the page's lines sat inside two items.

The threshold is not tuned. The population holds nothing between 1.8 em and
9.5 em, so every value in that range answers identically; 4 em is one of them.

WHAT IS REFUSED, AND WHAT IS NOT. Only the TAIL. The marker line stays a
one-line item and the prose goes back to the paragraph builder, which has its
own measured rules for where a paragraph starts (`_is_first_line`,
e518e375). Whether a centred `1. ` line is a heading rather than a list item
at all is a different question and is left open here: this fixes the 46 lines
of body text, not the one line of heading.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document
from docmodel.modules.list_items import ListProcessor

EM = 40.0            # the page's line height, so one em is 40 units


def _doc(lines):
    doc = Document()
    st = doc.ensure_stream("mathpix_lines")
    for l in lines:
        st.append(**l)
    return doc


def _proc():
    p = ListProcessor.__new__(ListProcessor)
    p.bibkey = "T"
    p.LINES_STREAM = "mathpix_lines"
    p.counters = {}
    return p


def _line(i, x, text, subtype=None, y=None):
    """One prose line of a one-column page, 40 units tall."""
    d = {"id": f"l{i}", "type": "text", "text": text, "_page": 1,
         "_line_index": i,
         "region": {"top_left_x": x, "top_left_y": y if y is not None else 100 + 60 * i,
                    "width": 800, "height": EM}}
    if subtype:
        d["subtype"] = subtype
    return d


def _page(marker_x, *, marker="1.", body_x=150.0, n_body=12):
    """A page whose body column recurs at `body_x`, with one marker line
    standing at `marker_x` and `n_body` stated continuations under it.

    The body lines are what make the column's edge measurable: `_body_edges`
    is keyed by page and needs the page's own statistics, so a handful of
    lines is not a page (the vacuous-fixture trap, hit three times in this
    task).
    """
    out = [_line(0, marker_x, f"{marker} Projektionen in Zeit und Raum")]
    for i in range(1, n_body + 1):
        out.append(_line(i, body_x + (i % 3), f"Zeile {i} der laufenden Prosa",
                         subtype="continues_line_space"))
    return out


def test_a_centred_marker_does_not_take_the_body_prose():
    """The measured defect: BH3 p37's shape, 9.5 em of outdent."""
    items = _proc().find_items(_doc(_page(marker_x=150.0 + 9.5 * EM)))
    assert len(items) == 1, items
    assert items[0]["content"] == "Projektionen in Zeit und Raum", items[0]
    assert items[0]["child_ids"] == [], (
        "the body prose was folded into the item: %r" % (items[0]["child_ids"],))


def test_the_prose_is_left_for_the_paragraph_builder():
    """Refusing the tail is only a gain if the lines are released: an
    item that does not take them must not mark them taken either."""
    doc = _doc(_page(marker_x=150.0 + 9.5 * EM))
    _proc().find_items(doc)
    st = doc.streams["mathpix_lines"]
    taken = [p.get("id") for p in st.payload.values() if p.get("_in_list_item")]
    assert taken == ["l0"], taken


def test_an_ordinary_indented_marker_still_takes_its_tail():
    """1.5 em of outdent is the page's own indent, not a heading. This is
    lib:c9daf p236 and lib:008d p334, and the pass must keep working."""
    items = _proc().find_items(_doc(_page(marker_x=150.0 + 1.5 * EM,
                                          marker="•", n_body=6)))
    assert len(items) == 1, items
    assert len(items[0]["child_ids"]) == 6, items[0]
    assert items[0]["content"].endswith("Prosa"), items[0]["content"]


def test_a_hanging_indent_still_takes_its_tail():
    """The bibliography shape: the marker sits at the edge and the tail is
    indented RIGHT of it. Nothing about this is an outdent."""
    lines = [_line(0, 150.0, "- assertions, 143")]
    for i in range(1, 5):
        lines.append(_line(i, 190.0, f"Zeile {i}", subtype="continues_line_space"))
    for i in range(5, 12):                     # body, to make the edge measurable
        lines.append(_line(i, 150.0, f"Prosa {i}"))
    items = _proc().find_items(_doc(lines))
    assert len(items) == 1 and len(items[0]["child_ids"]) == 4, items


def test_a_page_with_no_measurable_edge_keeps_the_old_answer():
    """Abstention, not a guess: four lines are not a page, so `em` cannot be
    measured and nothing is refused on that evidence."""
    lines = [_line(0, 900.0, "1. Ein Titel"),
             _line(1, 150.0, "Prosa eins", subtype="continues_line_space"),
             _line(2, 150.0, "Prosa zwei", subtype="continues_line_space")]
    items = _proc().find_items(_doc(lines))
    assert len(items) == 1 and len(items[0]["child_ids"]) == 2, items
