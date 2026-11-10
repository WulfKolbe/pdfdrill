"""A region written as a decimal string is a region, not a missing region.

`render_crops` parsed its geometry with `int(t["top_left_x"])`. For the
readings whose regions are written as decimal STRINGS -- every
`pdfminer-chars` reading does, e.g. 1609.03457 page 007:

    {"page": "007", "top_left_x": "89.56", "top_left_y": "232.73",
     "width": "450.44", "height": "11.95"}

-- `int("89.56")` raises ValueError, and the `except` branch was written for
a row that carries NO geometry at all: it trusts a file that exists and
counts a missing one as `skipped`. So the row silently never got a crop,
and the counter called it skipped rather than failed. Measured across the
library: 11,200 cuttable rows in 53 documents have decimal geometry and no
CDN uri, so there was no route to a crop for any of them -- 5.7% of the
196,378 cuttable rows. Worst: Srednicki QFT 2,894 rows, Baier/Katoen 2,149,
Tensors/Riemannian 1,868, qftbook 1,447, hep-th_0604151 1,385.

THE FRAME IS NOT THE DEFECT, and it was checked before this was called a
parse bug. The decimal regions are in the reading's own frame -- 1609.03457
records page_width 612.0 x page_height 792.0, US Letter in points -- and
`refine.mathpix_page_dims` reports that same frame, which is what
`render_crops` scales by. So parsing the decimals puts the crop where the
row says it is; it does not unlock 11,200 crops cut in the wrong place.

ROUNDING, NOT TRUNCATION, and the top-left and the extent round in
OPPOSITE directions. `int()` truncates, which pulls the left edge in and
shrinks the width: at 400 dpi one point is 5.56 raster pixels, so dropping
0.56 pt off a left edge clips 3 pixels off a glyph. The box is therefore
floored at the top-left and ceilinged at the bottom-right, so a fractional
region never loses ink.

AND AN INTEGRAL REGION MUST PARSE TO EXACTLY WHAT IT DID BEFORE. The
parsed numbers are the `crops.geometry.json` cache key (671): if this
changed them, every crop in the library would compare unequal to its
recorded geometry and re-render. floor/ceil of an integer is that integer,
so the key is stable and no document re-renders for this change.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest

from pdfdrill import report_tex as rt

from test_render_crops import _FakeImage, _tid, patched      # noqa: F401


def _decimal_tid(title="d_TAB_001", page="007"):
    """1609.03457 page 007's own row, verbatim but for the title.

    `page` is a parameter because the shared `patched` fixture rasterizes
    pages 3 and 4 only; a row on any other page is skipped by the caller for
    want of page dimensions, which is correct behaviour and not what these
    tests are about. The decimal values are the document's own either way.
    """
    return {"title": title, "page": page, "top_left_x": "89.56",
            "top_left_y": "232.73", "width": "450.44", "height": "11.95"}


# --------------------------------------------------------------- the parse

def test_a_decimal_string_region_is_parsed_not_refused():
    # 89.56..540.00 across -> floor 89, ceil 540, width 451
    # 232.73..244.68 down  -> floor 232, ceil 245, height 13
    assert rt._region_px(_decimal_tid()) == (7, 89, 232, 451, 13)


def test_the_top_left_floors_and_the_extent_ceilings_so_no_ink_is_lost():
    t = {"page": 1, "top_left_x": "10.9", "top_left_y": "20.9",
         "width": "5.2", "height": "5.2"}
    page, x, y, w, h = rt._region_px(t)
    assert (x, y) == (10, 20), "the top-left must not move INTO the ink"
    assert x + w >= 10.9 + 5.2, "the right edge must not cut the ink"
    assert y + h >= 20.9 + 5.2, "the bottom edge must not cut the ink"


def test_an_integral_region_parses_to_exactly_what_int_gave():
    """The cache key must not move, or the whole library re-renders."""
    for t in ({"page": 3, "top_left_x": 100, "top_left_y": 200,
               "width": 300, "height": 120},
              {"page": "003", "top_left_x": "100", "top_left_y": "200",
               "width": "300", "height": "120"},
              {"page": 3.0, "top_left_x": 100.0, "top_left_y": 200.0,
               "width": 300.0, "height": 120.0}):
        assert rt._region_px(t) == (3, 100, 200, 300, 120)


@pytest.mark.parametrize("t", [
    {"page": None},
    {"page": 1, "top_left_x": "abc", "top_left_y": "1", "width": "1",
     "height": "1"},
    {"page": 1, "top_left_x": "1", "top_left_y": "1", "width": "1"},
    {"page": 1, "top_left_x": "", "top_left_y": "1", "width": "1",
     "height": "1"},
    {"page": "", "top_left_x": "1", "top_left_y": "1", "width": "1",
     "height": "1"},
    {"page": 1, "top_left_x": float("nan"), "top_left_y": 1, "width": 1,
     "height": 1},
])
def test_a_row_that_really_carries_no_region_still_says_so(t):
    """None, not an exception: the caller's fallback path is unchanged."""
    assert rt._region_px(t) is None


# ------------------------------------------------- and through render_crops

def test_a_decimal_region_row_is_rendered_not_skipped(patched, tmp_path):
    ok, cached, skipped = rt.render_crops(
        [_decimal_tid(page="003")], tmp_path / "crops", tmp_path / "d.pdf")
    assert (ok, cached, skipped) == (1, 0, 0)
    assert (tmp_path / "crops" / "d_TAB_001.jpg").is_file()


def test_the_decimal_row_lands_where_the_row_says_it_does(monkeypatch,
                                                          tmp_path):
    """612x792 points, raster 3400x4400 -> 400/72 on both axes."""
    _FakeImage.calls = []
    from pdfdrill import pdf_reading, refine

    def fake_rasterize(pdf, out_dir, *, pages=None, dpi=400, **kw):
        out_dir = pathlib.Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        made = []
        for n in pages:
            f = out_dir / ("page-%04d.png" % n)
            f.write_bytes(b"")
            made.append(f)
        return sorted(made)

    monkeypatch.setattr(pdf_reading, "rasterize", fake_rasterize)
    monkeypatch.setattr(refine, "mathpix_page_dims",
                        lambda d: {7: (612.0, 792.0)})
    import PIL.Image
    monkeypatch.setattr(PIL.Image, "open",
                        lambda p: _FakeImage((3400, 4400)))
    monkeypatch.setattr(PIL.Image, "LANCZOS", 1, raising=False)

    rt.render_crops([_decimal_tid()], tmp_path / "crops", tmp_path / "d.pdf")
    assert _FakeImage.calls, "nothing was cropped"
    left, top, right, bottom = _FakeImage.calls[0]["box"]
    sx, sy = 3400 / 612.0, 4400 / 792.0
    # the ink runs 89.56..540.00 across and 232.73..244.68 down
    assert left <= 89.56 * sx and right >= 540.0 * sx
    assert top <= 232.73 * sy and bottom >= 244.68 * sy


def test_an_unchanged_decimal_row_caches_instead_of_rerendering(patched,
                                                                tmp_path):
    """The parsed numbers are the 671 cache key; a second call must hit it."""
    crops = tmp_path / "crops"
    first = rt.render_crops([_decimal_tid(page="003")], crops,
                            tmp_path / "d.pdf")
    second = rt.render_crops([_decimal_tid(page="003")], crops,
                             tmp_path / "d.pdf")
    assert first == (1, 0, 0)
    assert second == (0, 1, 0), "a decimal row re-rendered on every call"
