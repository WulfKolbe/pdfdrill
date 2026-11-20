r"""`px_per_pt: null` is the reading declaring nothing, not a number.

The queued question was why every inspect manifest reports
`px_per_pt=undeclared`. Measured, and the manifest is honest: EVERY page of
EVERY reading in the Gemma4 inspect set (2957de8, yolo) carries
`px_per_pt: None` -- 1317 pages over ten documents, 0864 5, 1805.01788 10,
2312.11532 11, lib:5a5c76391c9c 14, US6100897A 18, BH3 174,
lib:c9daf79960c3 288, lib:008d43e5db48 370, lib:d68e0271bd4d 425,
lib:9027b2a8b957 2. And it is not a Gemma4 gap: the MathPix references for
0864, 1805.01788 and 2312.11532 declare None on all 26 of their pages too.

So the KEY IS PRESENT AND ITS VALUE IS NULL, which is the shape that breaks
a reader testing for presence. `Pages._load_lines` did

    if "px_per_pt" in pg:
        self.px_per_pt[int(n)] = float(pg["px_per_pt"])

and `float(None)` raises TypeError. The enclosing `try` catches only
`(OSError, ValueError)` around the file read, so the TypeError propagates out
of `Pages.__init__` -- the pdf2mmd crop server (`pdfreader/inspectserver.py`)
cannot start against any reading in the corpus. Not a hypothetical input:
this is every lines.json we have.

A reading that states no scale is handled the way `docinspect`'s manifest
already states it -- undeclared -- and the server falls back to the ratio it
measures from the image, which is what `assume_pixels` and the `ratio <=
1.05` test below it are for.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _pages(tmp_path, px_per_pt):
    """A `Pages` built over one page image and one lines.json."""
    Image = pytest.importorskip("PIL.Image")
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    Image.new("RGB", (40, 60), "white").save(pages_dir / "p1.png")
    page = {"page": 1, "page_width": 1494, "page_height": 2292,
            "image_id": "x1"}
    if px_per_pt is not _ABSENT:
        page["px_per_pt"] = px_per_pt
    lines = tmp_path / "d.lines.json"
    lines.write_text(json.dumps({"pages": [page]}), encoding="utf-8")
    from pdfreader.inspectserver import Pages
    return Pages(str(pages_dir), lines=[str(lines)])


_ABSENT = object()


def test_a_null_scale_does_not_stop_the_server(tmp_path):
    """The whole corpus has this shape, so this is the case that matters."""
    p = _pages(tmp_path, None)
    assert p.px_per_pt == {}, "a null scale must not be recorded as a number"
    assert p.dims.get(1) == (1494.0, 2292.0), "the page size still loads"


def test_a_declared_scale_is_still_read(tmp_path):
    p = _pages(tmp_path, 250.0 / 72.0)
    assert p.px_per_pt[1] == pytest.approx(250.0 / 72.0)


def test_an_absent_key_is_the_same_as_a_null_one(tmp_path):
    p = _pages(tmp_path, _ABSENT)
    assert p.px_per_pt == {}


def test_a_scale_that_is_not_a_number_is_refused_not_raised(tmp_path):
    """A reading is an input, so a string or a list where a float belongs is
    bad data to decline, never a crash."""
    p = _pages(tmp_path, "250/72")
    assert p.px_per_pt == {}
