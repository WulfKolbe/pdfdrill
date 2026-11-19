r"""A paragraph ends at a blank band, not only inside a caption.

0864 p4, the owner's page, read by glyphdrill3. One Paragraph object came out
holding this:

    ...where the lowest a values where used, i.e., 0.05, 0.1 , and 0.35.
    6 Conclusion
    We investigated the algorithmic aspect of discovering dependencies...

-- the results paragraph, a SECTION HEADING, and the Conclusion paragraph, as
one object whose rectangle is 1479 px tall and covers half the column. The
same weld was reported on lib:5a5c76391c9c p12, where a Conclusion paragraph
and an "Acknowledgements" block became one 15-line Paragraph.

WHY NOTHING STOPPED IT. `find_items` starts a new paragraph on an indent, on a
group change, or at a caption start. The heading is typed `text` by that
reading, so it is prose; it is not indented; and the reading states no
`block_num`/`par_num`, so the group test is skipped by its own guard. The
vertical-gap rule existed already but was gated to `kind == "caption"`.

The gap is the signal that IS in the data: the right column's pitch is about
61 px, the band above the heading 187 px (3.1x) and above the Conclusion
137 px (2.2x). The same 1.6x rule the caption path already used therefore
splits both, and it is now applied to prose as well.

WHAT MUST NOT BREAK: a paragraph whose lines are merely set a little loosely
stays one paragraph. A display equation between two prose runs already splits
the paragraph today -- `find_items` flushes on any non-prose line type -- so
that case does not depend on this rule and is not changed by it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.base_module import ModuleConfig  # noqa: E402
from docmodel.core import Document  # noqa: E402
from docmodel.modules.page import ingest_lines_json  # noqa: E402
from docmodel.modules.paragraph import ParagraphProcessor  # noqa: E402


def _paras(rows):
    """One page of prose lines at the given y positions, then its paragraphs."""
    lines = [{"id": "l%d" % i, "type": "text", "text": t, "text_display": t,
              "region": {"top_left_x": 1750, "top_left_y": y,
                         "width": 1350, "height": 42}}
             for i, (y, t) in enumerate(rows)]
    doc = Document()
    ingest_lines_json(doc, {"source": "glyphdrill3", "pages": [
        {"page": 1, "image_id": None, "page_width": 3400,
         "page_height": 4400, "lines": lines}]})
    ParagraphProcessor(ModuleConfig(title="ParagraphProcessor",
                                    classname="ParagraphProcessor",
                                    proc_order=13), "T").process_document(doc)
    return [o.props.get("text") or "" for o in doc.objects_of_type("Paragraph")]


def test_a_band_of_three_pitches_ends_the_paragraph():
    """The 0864 p4 shape: body, a heading after a wide band, then a new body."""
    paras = _paras([
        (2990, "differences between the two algorithms is for the 3 datasets"),
        (3051, "where the lowest alpha values where used, i.e., 0.05 and 0.35."),
        (3238, "6 Conclusion"),
        (3375, "We investigated the algorithmic aspect of discovering"),
        (3436, "dependencies in data using the reliable fraction of"),
    ])
    joined = [p for p in paras
              if "lowest alpha" in p and "We investigated" in p]
    assert not joined, "the band must end the paragraph, not be swallowed"
    assert len(paras) >= 3, "body, heading and the new body are three paragraphs"


def test_a_normally_set_paragraph_is_not_split():
    """The half that must not be lost: an ordinary pitch keeps one paragraph."""
    paras = _paras([
        (2990, "differences between the two algorithms is for the 3 datasets"),
        (3051, "where the lowest alpha values where used, and also the ones"),
        (3112, "with the lowest number of features, which leads to a more"),
        (3173, "effective optimization with branch-and-bound in general."),
    ])
    whole = [p for p in paras
             if "differences between" in p and "effective optimization" in p]
    assert whole, "four lines at one pitch are one paragraph"
