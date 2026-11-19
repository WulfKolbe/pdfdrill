r"""A paragraph is one column's. A line from the other column ends it.

0864 p5's references, read from the page's own text layer, came out with
entries like these — and the tails are not typographical oddities, they are
the OTHER COLUMN:

    '[Brown et al., 2012] Gavin Brown, Adam Pocock, Ming-Jie ings'
    '[Giannella and Robertson, 2004] Chris Giannella and Ed- [Web'

`ings` is the end of a right-column word and `[Web` the start of a
right-column entry. glyphdrill4's object check calls this CROSSES gutter and
SPANS, and on that page it is most of what it flags: 53 of 85 objects.

Nothing in `find_items` looked at columns. It starts a new paragraph on an
indent, on a `block_num`/`par_num` change, at a caption, and at a blank band.
The first needs the page's edges, the second is stated by MathPix and
tesseract but NOT by the readers that state no grouping at all, and neither
of the last two says anything about x. So a reading whose lines interleave
the columns — which is what reading order does on a two-column page — welds
them.

`_body_edges` already groups its edges into columns, for `_is_first_line`.
The same grouping answers "which column is this line in", so a change of
column could end the paragraph -- geometry every reading carries, not a field
only some of them state.

NOT IMPLEMENTED, AND THE MEASUREMENT IS WHY. That flush was written and run
on the three ratchet documents, text-layer lane, against glyphdrill4's object
check:

    0864         85 objects / 53 CROSSES / 21 SPANS  ->  93 / 57 / 21
    1805.01788  276 /  38 / 27                       -> 347 / 38 / 27
    2312.11532  191 /  28 / 25                       -> 195 / 25 / 21

It splits paragraphs (objects rise) and 2312.11532 improves, but CROSSES
RISES ON THE OWNER'S PAGE, which is the opposite of the point. A paragraph
confined to one column cannot span a gutter, so either the flush is not
firing where it should or CROSSES does not mean what it is assumed to mean
here -- and objcheck's JSON records no object type, so the flagged objects
could not be attributed from this side.

The weld is real: the two tests below fail without the flush. What is missing
is an understanding of the check that is supposed to confirm the cure. Fixing
that first is the next step, not a third threshold.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.base_module import ModuleConfig  # noqa: E402
from docmodel.core import Document  # noqa: E402
from docmodel.modules.page import ingest_lines_json  # noqa: E402
from docmodel.modules.paragraph import ParagraphProcessor  # noqa: E402


def _paras(rows):
    """rows: (x, y, text). One page, 32 px em, two columns far apart."""
    lines = [{"id": "l%d" % i, "type": "text", "text": t, "text_display": t,
              "region": {"top_left_x": x, "top_left_y": y,
                         "width": 800, "height": 32}}
             for i, (x, y, t) in enumerate(rows)]
    doc = Document()
    ingest_lines_json(doc, {"source": "glyphdrill3", "pages": [
        {"page": 1, "image_id": None, "page_width": 2125,
         "page_height": 2750, "lines": lines}]})
    ParagraphProcessor(ModuleConfig(title="ParagraphProcessor",
                                    classname="ParagraphProcessor",
                                    proc_order=13), "T").process_document(doc)
    return [o.props.get("text") or "" for o in doc.objects_of_type("Paragraph")]


@pytest.mark.xfail(strict=True, reason=(
    "the column flush raises CROSSES on 0864 (53 -> 57); see this file's "
    "docstring before implementing it"))
def test_a_right_column_line_does_not_join_a_left_column_paragraph():
    """The lines interleave by y, as reading order gives them.

    Enough lines per column that `_body_edges` can find an edge at all: it
    needs at least three at one x before it calls that x an edge, so a
    four-line fixture has no columns to respect and tests nothing.
    """
    rows = []
    y = 100
    for left, right in (("Gavin Brown, Adam Pocock, Ming-Jie",
                         "ings of the Twenty-Ninth Conference"),
                        ("Zhao and Mikel Lujan. Conditional",
                         "on Uncertainty in Artificial"),
                        ("likelihood maximisation: a unifying",
                         "Intelligence, pages 109 to 116,"),
                        ("framework for information theoretic",
                         "Arlington, Virginia, 2012. AUAI"),
                        ("feature selection. Journal of Machine",
                         "Press. ISBN 978 to 0 to 9749039,")):
        rows.append((224, y, left))
        rows.append((1136, y + 10, right))
        y += 40
    paras = _paras(rows)
    welded = [p for p in paras if "Ming-Jie" in p and "ings of the" in p]
    assert not welded, "a paragraph took a line from the other column"


def test_a_single_column_page_is_unaffected():
    """Four lines at one edge stay one paragraph."""
    paras = _paras([
        (224, 100, "differences between the two algorithms is for"),
        (224, 140, "the three datasets where the lowest alpha"),
        (224, 180, "values were used, and also the ones with the"),
        (224, 220, "lowest number of features, which leads to"),
        (224, 260, "a more effective optimization with branch"),
        (224, 300, "and bound in general, and particularly for"),
    ])
    whole = [p for p in paras
             if "differences between" in p and "lowest number" in p]
    assert whole, "one column's consecutive lines are one paragraph"
