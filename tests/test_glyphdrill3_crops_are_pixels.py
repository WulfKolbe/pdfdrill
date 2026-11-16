"""
P9-20 (T-0145, found while fixing P9-18): a glyph-reader crop was asked for in
points, and its regions are 400 dpi pixels.

`_PAGE_PIXEL_SOURCES` held ("mathpix", "pdf2mmd2"). `glyphdrill3` was not in
it, so `image_ref` took the everything-else branch and appended `units=pt` to
the crop URL. Measured on 0001124 p9, a 612 x 792 pt page the glyph reader
reads at 400 dpi (page_width 3400, page_height 4400, px_per_pt 5.555556), the
first Equation's region is

    top_left_x 536, top_left_y 897, width 1855, height 182

and the URL built from it was

    /cropped/27fca2fa4e9371fb-9.png?height=182&width=1855&top_left_y=897
      &top_left_x=536&units=pt

897 pt is off the bottom of a 792 pt page and 1855 pt is three times its width,
so every equation crop of a glyph reading was a crop of nothing. This is the
defect 897 is about, recurring for a reader that did not exist when the list
was written: "the frame has to be carried per reader, or declared per reading."

The reading DOES declare it -- `px_per_pt` sits beside `page_width` in every
glyphdrill3 page -- and that is the frame this should eventually read, at a
call site that has the reading. Until then the reader is named here, which is
the same answer pdf2mmd2 got.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.mathpix import _is_page_pixel_source, image_ref

# 0001124 p9, the first Equation, verbatim from the model.
REGION = {"top_left_x": 536, "top_left_y": 897, "width": 1855, "height": 182}
IMAGE_ID = "27fca2fa4e9371fb-9"


def test_the_glyph_reader_is_a_page_pixel_source():
    assert _is_page_pixel_source("glyphdrill3")


def test_a_glyph_reading_crop_is_not_asked_for_in_points():
    url = image_ref(IMAGE_ID, REGION, "glyphdrill3")
    assert "units=pt" not in url, \
        f"400 dpi pixels asked for as points: {url}"
    assert "top_left_y=897" in url, "the region itself must pass through"


def test_the_readers_that_are_in_points_still_are():
    url = image_ref(IMAGE_ID, REGION, "pdfminer-docmodel")
    assert "units=pt" in url, \
        "the pdfminer reading's regions ARE points; nothing here changes that"


def test_mathpix_still_goes_to_the_cdn():
    assert image_ref(IMAGE_ID, REGION, "mathpix").startswith("http")


def test_a_suffixed_glyph_source_counts_too():
    """`_is_page_pixel_source` matches `name-suffix`, which is how a reader
    names a variant; a variant of the glyph reader is in the same frame."""
    assert _is_page_pixel_source("glyphdrill3-regroup")
