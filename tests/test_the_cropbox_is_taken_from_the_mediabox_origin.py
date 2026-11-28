r"""The CropBox in the glyphs' frame: relative to the MediaBox origin.

pdfminer lays a page out from the MediaBox's lower-left corner, so a region
placed `x - crop.x0` with the CropBox as stated subtracted that corner a
second time. Held-out draw: lib:477e5c4130b0 p407 (MediaBox = CropBox =
46.63 34.58 551.20 754.58) had every region 162 px left of its ink, residual
1.44 -> 0.11 after; lib:7e9f02b4f39f p287 1.37 -> 0.54.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

dm = pytest.importorskip("pdfreader.docmodel_six")


def test_a_cropbox_equal_to_a_shifted_mediabox_starts_at_zero():
    media = (46.6299, 34.5827, 551.197, 754.583)
    out = dm._crop_in_layout_frame(media, media, 0)
    assert out == pytest.approx((0.0, 0.0, 551.197 - 46.6299, 754.583 - 34.5827))


def test_a_mediabox_at_the_origin_leaves_the_cropbox_as_stated():
    # lib:d68e0271bd4d p334, where the CropBox frame was first measured
    assert dm._crop_in_layout_frame((43, 87, 473, 747), (0, 0, 595, 842), 0) \
        == (43.0, 87.0, 473.0, 747.0)


def test_a_cropbox_inside_a_shifted_mediabox():
    assert dm._crop_in_layout_frame((60, 50, 500, 700), (10, 20, 600, 800), 0) \
        == (50.0, 30.0, 490.0, 680.0)


def test_a_rotated_page_keeps_the_stated_box():
    assert dm._crop_in_layout_frame((60, 50, 500, 700), (10, 20, 600, 800), 90) \
        == (60.0, 50.0, 500.0, 700.0)
