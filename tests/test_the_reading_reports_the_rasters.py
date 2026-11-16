"""
A raster the page paints is content, and the born-digital route reported none.

THE DEFECT, reported by the owner on arxiv.2209.02970 (2026-11-16) as "images
not separated". Measured on that reading: 1,555 `text` records, 1 `math`, and
NO image record of any kind on any of its 21 pages — while the pages paint
three 6x6 pt images on p1, a 454 x 114 pt raster on p9, and more on p10 and
p16. `pdfdrill` already wrote `probe-pdfimages-list.txt` beside the document
naming every one of them, so the information was in the folder and not in the
reading.

AFTER: 8 `figure` records over 4 pages, with the boxes the pages paint.

    page 1    3 records, 6 x 6 pt at x=311.3, 391.4, 462.8
    page 9    1 record, 454 x 114 pt at x=70.9, y=70.9
    page 10   3 records, 6 x 6 pt
    page 16   1 record, 454 x 114 pt

`figure` is the type `PictureProcessor` claims; `diagram` is
`DiagramProcessor`'s and is for vector art. The record carries the BOX and no
pixels — a crop is taken from the page at whatever resolution the caller wants,
and inventing text for a raster would be a reading nobody made.

WHAT THIS DOES NOT FIX, stated here because the owner's report was about an
inspect page: on a document whose model comes from the arXiv LaTeX source
(`source_path: "main.tex (LaTeX source, no OCR)"`), the model's `Picture`
objects come from `\\includegraphics` and are placed by reading-order
interpolation. The reading now holds the rasters, but a LaTeX-lane model does
not build its objects from the reading. That is the merge step's business and a
separate defect.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import chars_to_lines as C

PH, PW = 841.89, 595.28


def _char(x0, y_top, text):
    return {"x0": x0, "x1": x0 + 5.0,
            "y0": PH - (y_top + 9.0), "y1": PH - y_top,
            "text": text, "fontname": "Times-Roman", "upright": True, "turn": 0}


def _prose(n=4, y0=200.0):
    out = []
    for i in range(n):
        for j, ch in enumerate("prose line here"):
            out.append(_char(70.9 + j * 5.0, y0 + i * 12.0, ch))
    return out


def _image(x0, y_top, w, h, name="Im1"):
    """In the input's bottom-left origin, as the char dump is."""
    return {"x0": x0, "x1": x0 + w,
            "y0": PH - (y_top + h), "y1": PH - y_top, "name": name}


def _page(chars, images=()):
    return {"page_number": 1, "width": PW, "height": PH,
            "chars": chars, "images": list(images)}


def _whole(chars, images=()):
    return C.chars_to_lines_json({"source": "pdfminer-chars", "total_pages": 1,
                                  "pages": [_page(chars, images)]})


def _streamed(chars, images=()):
    return C.lines_json_streaming(iter([_page(chars, images)]),
                                  source="pdfminer-chars")


def _figures(js):
    return [l for p in js["pages"] for l in p.get("lines") or []
            if l.get("type") == "figure"]


def test_a_painted_raster_becomes_a_record():
    js = _whole(_prose(), [_image(70.9, 70.9, 454.0, 114.0)])
    figs = _figures(js)
    assert len(figs) == 1, f"expected 1 figure record, got {len(figs)}"
    r = figs[0]["region"]
    assert (round(r["width"]), round(r["height"])) == (454, 114), \
        f"the box is not the one the page paints: {r}"
    assert round(r["top_left_x"], 1) == 70.9 and round(r["top_left_y"], 1) == 70.9, \
        f"the box is in the wrong place: {r}"


def test_the_type_is_the_one_a_processor_claims():
    """`PictureProcessor.find_items` keys on type == 'figure'. A type nothing
    reads would look like a fix and build no object."""
    from docmodel.modules import picture
    js = _whole(_prose(), [_image(100.0, 300.0, 200.0, 150.0)])
    assert _figures(js)[0]["type"] == "figure"
    assert "figure" not in picture._SKIP_TYPES


def test_the_raster_carries_no_invented_text():
    js = _whole(_prose(), [_image(100.0, 300.0, 200.0, 150.0)])
    f = _figures(js)[0]
    assert (f.get("text") or "") == "" and (f.get("text_display") or "") == "", \
        f"text was invented for a raster: {f.get('text')!r}"


def test_the_prose_is_untouched():
    js = _whole(_prose(n=4), [_image(100.0, 300.0, 200.0, 150.0)])
    prose = [l for p in js["pages"] for l in p.get("lines") or []
             if l.get("type") != "figure"]
    assert len(prose) == 4, f"expected 4 prose lines, got {len(prose)}"


def test_both_routes_agree():
    """`tests/test_chars_streaming.py` holds the streaming route to being
    byte-identical to the whole-document one. Image records must not be the
    exception."""
    chars, images = _prose(), [_image(70.9, 70.9, 454.0, 114.0),
                               _image(300.0, 400.0, 50.0, 50.0)]
    a, b = _whole(chars, images), _streamed(chars, images)
    assert a["pages"] == b["pages"], \
        "the two assembler routes disagree once images are in play"


def test_a_page_of_nothing_but_a_raster_still_appears():
    """A full-page plate has no glyphs, so the assembler emits no page for it.
    Without its own entry the one thing a reading of that page can show would
    be missing."""
    js = _whole([], [_image(0.0, 0.0, PW, PH)])
    figs = _figures(js)
    assert len(figs) == 1, "a page of only a raster produced no record"
    assert js["pages"], "a page of only a raster produced no page entry"


def test_a_degenerate_box_is_not_a_record():
    """A zero-area image is a paint instruction, not a picture."""
    js = _whole(_prose(), [_image(100.0, 300.0, 0.0, 150.0),
                           _image(100.0, 300.0, 200.0, 0.0)])
    assert not _figures(js), "a zero-area image became a figure record"


def test_a_reading_with_no_images_is_unchanged():
    with_key = _whole(_prose(), [])
    without = C.chars_to_lines_json(
        {"source": "pdfminer-chars", "total_pages": 1,
         "pages": [{"page_number": 1, "width": PW, "height": PH,
                    "chars": _prose()}]})
    assert with_key["pages"] == without["pages"], \
        "the images key changed a reading that has none"
