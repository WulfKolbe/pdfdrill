"""An image URL pdfdrill cannot place is not a Picture sitting on body text.

The owner found it on a Gemma reading of 0864: a box labelled "Picture" lay
across the sentence "e.g., [Huhtala et al., 1999; ...], ne-". The reading had
written a body text line as `![Figure 1: ...](https://example.com/figure1.png)`,
and PictureProcessor turned it into a Picture whose only anchor is that text
line -- so the page drew a picture box one text line tall, and stored
`https://example.com/figure1.png`, a URL nothing ever fetched, as the image.

`_MD_IMG` accepted any `http(s)` URL, while this module's own contract says the
trusted inline form is a MathPix crop of a page we have: `![](<cdn>)` with the
rectangle in the query string. That rectangle is the test. With one, the URL
addresses a region of the page and the Picture is real; without one, pdfdrill
has neither the file nor a place to put it, and inventing both is worse than
keeping nothing.

What is kept is the alt text. On that document it reads "Figure 1:
Dependency-by-chance. ..." while the page's real Diagram carries no caption at
all, so the refused image's alt text is exactly the caption that was missing.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.base_module import ModuleConfig
from docmodel.core import Document
from docmodel.modules.page import ingest_lines_json, PageProcessor
from docmodel.modules.diagram import DiagramProcessor
from docmodel.modules.picture import PictureProcessor

CDN = ("https://cdn.mathpix.com/cropped/abc-1.jpg"
       "?height=400&width=800&top_left_y=100&top_left_x=50")
INVENTED = "https://example.com/figure1.png"


def _mod(cls):
    return cls(ModuleConfig(title=cls.__name__, classname=cls.__name__, proc_order=0), "T")


def _doc(lines, page=1):
    doc = Document()
    doc.meta["bibkey"] = "T"
    for i, ln in enumerate(lines):
        ln.setdefault("id", "l%d" % i)
        ln.setdefault("region", {"top_left_x": 10, "top_left_y": 20 + 40 * i,
                                 "width": 800, "height": 32})
    ingest_lines_json(doc, {"pages": [{"page": page, "image_id": "im-01",
                                       "page_width": 2125, "page_height": 2750,
                                       "lines": lines}]})
    _mod(PageProcessor).process_document(doc)
    return doc


def test_an_invented_url_in_a_text_line_makes_no_picture():
    doc = _doc([{"type": "text",
                 "text": "![Figure 1: Dependency-by-chance.](%s)" % INVENTED}])
    _mod(PictureProcessor).process_document(doc)
    assert doc.objects_of_type("Picture") == [], (
        "a URL with no rectangle cannot be placed, so it is not a Picture")


def test_the_invented_url_is_never_an_image_url():
    """The rule is about the IMAGE url, not about the reading's own text.

    A Paragraph legitimately keeps the line text it was built from, and on the
    real 0864 two paragraphs quote the whole `![...](...)` run — that is the
    reading's content, and stripping it would be pdfdrill falsifying what the
    reader said. What must never happen is pdfdrill presenting that URL as an
    image it has.
    """
    doc = _doc([{"type": "text", "text": "![Figure 1: x](%s)" % INVENTED}])
    _mod(PictureProcessor).process_document(doc)
    for obj in doc.objects.values():
        for key in ("url", "image_url", "src", "cdn_url"):
            assert INVENTED not in str((obj.props or {}).get(key) or ""), (
                "%s.%s presents a URL pdfdrill never fetched as an image"
                % (obj.type, key))
    for cand in doc.meta.get("image_caption_candidates") or []:
        assert INVENTED not in str(cand)


def test_a_figure_caption_does_not_land_on_a_table():
    """0864 p3 has a captionless Table and a captionless Diagram, and the alt
    text is "Figure 2: ...". It belongs to the Diagram."""
    doc = _doc([
        {"type": "table", "text": "\\begin{tabular}{cc} a & b \\end{tabular}",
         "region": {"top_left_x": 100, "top_left_y": 900, "width": 800, "height": 600}},
        {"type": "diagram", "text": "", "image_id": "im-01",
         "region": {"top_left_x": 100, "top_left_y": 200, "width": 800, "height": 600}},
        {"type": "text", "text": "![Figure 2: Base transformation.](%s)" % INVENTED},
    ])
    from docmodel.modules.table import TableProcessor
    _mod(TableProcessor).process_document(doc)
    _mod(DiagramProcessor).process_document(doc)
    _mod(PictureProcessor).process_document(doc)
    dia = doc.objects_of_type("Diagram")
    assert len(dia) == 1 and dia[0].props["caption"] == "Base transformation."
    for tbl in doc.objects_of_type("Table"):
        assert "Base transformation" not in (tbl.props.get("caption") or "")


def test_a_mathpix_crop_in_a_text_line_is_still_a_picture():
    """The regression guard: a URL that carries its own rectangle is real."""
    doc = _doc([{"type": "text", "text": "see ![](%s) above" % CDN}])
    _mod(PictureProcessor).process_document(doc)
    pics = doc.objects_of_type("Picture")
    assert len(pics) == 1
    assert pics[0].props["url"] == CDN
    assert pics[0].props["region"].get("width") == "800"


def test_the_refused_alt_text_captions_the_pages_captionless_image():
    """0864 p1: the Diagram has no caption and the refused alt text is it."""
    doc = _doc([
        {"type": "diagram", "text": "", "image_id": "im-01",
         "region": {"top_left_x": 100, "top_left_y": 200, "width": 800, "height": 600}},
        {"type": "text",
         "text": "![Figure 1: Dependency-by-chance. Estimated fraction.](%s)" % INVENTED},
    ])
    _mod(DiagramProcessor).process_document(doc)
    _mod(PictureProcessor).process_document(doc)
    dia = doc.objects_of_type("Diagram")
    assert len(dia) == 1
    assert dia[0].props["caption"] == "Dependency-by-chance. Estimated fraction."
    assert dia[0].props["kind"] == "Figure"
    assert str(dia[0].props["refnum"]) == "1"


def test_a_caption_already_there_is_not_overwritten():
    doc = _doc([
        {"type": "diagram", "text": "\\caption{The real caption}", "image_id": "im-01",
         "region": {"top_left_x": 100, "top_left_y": 200, "width": 800, "height": 600}},
        {"type": "text", "text": "![Figure 9: not this one](%s)" % INVENTED},
    ])
    _mod(DiagramProcessor).process_document(doc)
    _mod(PictureProcessor).process_document(doc)
    assert doc.objects_of_type("Diagram")[0].props["caption"] == "The real caption"


def test_the_candidate_is_recorded_even_with_nothing_to_caption():
    doc = _doc([{"type": "text", "text": "![Figure 1: orphan](%s)" % INVENTED}])
    _mod(PictureProcessor).process_document(doc)
    cands = doc.meta.get("image_caption_candidates") or []
    assert len(cands) == 1
    assert cands[0]["caption"] == "orphan"
    assert cands[0]["page"] == 1
    assert "url" not in cands[0], "the refused URL must not survive in meta either"
