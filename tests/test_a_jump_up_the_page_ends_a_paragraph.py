r"""A paragraph ends at a big vertical jump, upwards as well as downwards.

`find_items` ends a paragraph at an oversized vertical gap:

    gap = y - current["_last_y"]
    if ref and gap > 1.6 * ref: flush()

That is a DOWNWARD test. Reading order jumps UP the page at every column
break -- the foot of the left column to the head of the right -- and a jump up
gives a NEGATIVE gap, so the rule never fires and the paragraph runs on across
the break.

Measured on lib:d68e0271bd4d p400, the book's index, where obj_e390e3cade20
holds three lines:

    y=1937  x=801  'in OMDoc 1.2), 328--330'
    y=1973  x=770  'HETCASL 288'
    y= 322  x=768  'heterogeneous'          <- 1651 px UP, no flush

Its union box is then the whole column, and it overlaps every object between:
pagecheck counts 441 overlap_model findings on that book, 15 of them on p400
alone, where one such object accounts for most of a page's overlaps.

The gap is evidence of a break whichever way it goes, and upwards it is
stronger: running text never jumps back up the page.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.base_module import ModuleConfig  # noqa: E402
from docmodel.core import Document  # noqa: E402
from docmodel.modules.page import ingest_lines_json  # noqa: E402
from docmodel.modules.paragraph import ParagraphProcessor  # noqa: E402


def _paras(rows):
    """rows: (x, y, text) in STREAM order, which is reading order."""
    lines = [{"id": "l%d" % i, "type": "text", "text": t, "text_display": t,
              "region": {"top_left_x": x, "top_left_y": y,
                         "width": 300, "height": 30}}
             for i, (x, y, t) in enumerate(rows)]
    doc = Document()
    ingest_lines_json(doc, {"source": "glyphdrill3", "pages": [
        {"page": 1, "image_id": None, "page_width": 2125,
         "page_height": 2750, "lines": lines}]})
    ParagraphProcessor(ModuleConfig(title="ParagraphProcessor",
                                    classname="ParagraphProcessor",
                                    proc_order=13), "T").process_document(doc)
    return [o.props.get("text") or "" for o in doc.objects_of_type("Paragraph")]


def test_a_jump_to_the_head_of_the_next_column_ends_the_paragraph():
    """lib:d68e0271bd4d p400's shape: the foot of one column, then the head
    of the next, 1651 px up."""
    paras = _paras([
        (801, 1877, "a line near the foot of the column"),
        (801, 1907, "in OMDoc 1.2), 328 to 330"),
        (770, 1937, "HETCASL 288"),
        (768, 322, "heterogeneous"),
        (768, 352, "specification, 286"),
    ])
    joined = [p for p in paras
              if "HETCASL" in p and "heterogeneous" in p]
    assert not joined, "the paragraph ran on across a jump up the page"


def test_an_ordinary_downward_gap_still_ends_it():
    """The rule's existing half, unchanged."""
    paras = _paras([
        (224, 100, "the first paragraph of the page runs"),
        (224, 130, "to a second line and stops here."),
        (224, 400, "a new block begins after a wide band"),
        (224, 430, "and continues to its own second line"),
    ])
    joined = [p for p in paras
              if "stops here" in p and "a new block begins" in p]
    assert not joined, "a wide downward band must still end the paragraph"


def test_consecutive_lines_stay_one_paragraph():
    """What must not break: ordinary running text."""
    paras = _paras([
        (224, 100, "running text that continues"),
        (224, 130, "onto a second line and then"),
        (224, 160, "onto a third without a break"),
    ])
    whole = [p for p in paras
             if "running text" in p and "without a break" in p]
    assert whole, "three consecutive lines are one paragraph"
