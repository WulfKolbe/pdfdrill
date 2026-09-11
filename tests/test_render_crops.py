"""461 — the Tables Scan column, filled from the local render."""
import json, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest
from pdfdrill import report_tex as rt


def _tid(title, page=3, x=100, y=200, w=300, h=120, uri=None):
    t = {"title": title, "page": page, "top_left_x": x, "top_left_y": y,
         "width": w, "height": h}
    if uri:
        t["canonical_uri"] = uri
    return t


class _FakeImage:
    """Enough PIL surface for render_crops, recording what it was asked."""
    calls = []

    def __init__(self, size=(3400, 4400)):
        self.size = size
        self._box = None
        self._to = None

    def convert(self, mode):
        return self

    def crop(self, box):
        out = _FakeImage(self.size)
        out._box = box
        return out

    def resize(self, size, _filter=None):
        self._to = size
        return self

    def save(self, path, **kw):
        _FakeImage.calls.append({"box": self._box, "resize": self._to,
                                 "path": pathlib.Path(path)})
        pathlib.Path(path).write_bytes(b"\xff\xd8" + b"x" * 900)


@pytest.fixture
def patched(monkeypatch, tmp_path):
    _FakeImage.calls = []
    from pdfdrill import pdf_reading, refine
    pages_dir = {}

    def fake_rasterize(pdf, out_dir, *, pages=None, dpi=400, **kw):
        out_dir = pathlib.Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        made = []
        for n in pages:
            f = out_dir / ("page-%04d.png" % n)
            f.write_bytes(b"")
            made.append(f)
        pages_dir["asked"] = list(pages)
        return sorted(made)

    monkeypatch.setattr(pdf_reading, "rasterize", fake_rasterize)
    # fake raster is 3400x4400; MathPix page 1700x2200 -> both axes double
    monkeypatch.setattr(refine, "mathpix_page_dims",
                        lambda d: {3: (1700.0, 2200.0), 4: (1700.0, 2200.0)})
    import PIL.Image
    monkeypatch.setattr(PIL.Image, "open", lambda p: _FakeImage())
    monkeypatch.setattr(PIL.Image, "LANCZOS", 1, raising=False)
    return pages_dir


def test_a_tab_row_with_a_region_is_rendered(patched, tmp_path):
    ok, cached, skipped = rt.render_crops(
        [_tid("d_TAB_001")], tmp_path / "crops", tmp_path / "d.pdf")
    assert (ok, cached, skipped) == (1, 0, 0)
    assert (tmp_path / "crops" / "d_TAB_001.jpg").is_file()


def test_coordinates_are_scaled_by_that_pages_mathpix_dims(patched, tmp_path):
    # raster 3400x4400, MathPix page 1700x2200 -> every coordinate doubles
    # on BOTH axes
    rt.render_crops([_tid("d_TAB_001", x=100, y=200, w=300, h=120)],
                    tmp_path / "crops", tmp_path / "d.pdf")
    call = _FakeImage.calls[0]
    assert call["box"] == (200, 400, 800, 640)
    # and the saved image is resized BACK to the MathPix region size, because
    # crop_cell sizes it as jpg_width x px2mm and px2mm is per MathPix pixel
    assert call["resize"] == (300, 120)


def test_coordinates_scale_x_and_y_independently(monkeypatch, tmp_path):
    """654 — a single width-derived factor is wrong once the raster and
    MathPix's own page image disagree in aspect (a CropBox-inset page). Here
    the raster is 2x MathPix's width but 3x its height; a single factor
    (the pre-654 bug) would use 2x for y too and land the crop short."""
    from pdfdrill import pdf_reading, refine
    _FakeImage.calls = []

    def fake_rasterize(pdf, out_dir, *, pages=None, dpi=400, **kw):
        out_dir = pathlib.Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        f = out_dir / "page-0003.png"
        f.write_bytes(b"")
        return [f]

    monkeypatch.setattr(pdf_reading, "rasterize", fake_rasterize)
    monkeypatch.setattr(refine, "mathpix_page_dims", lambda d: {3: (100.0, 100.0)})
    import PIL.Image
    monkeypatch.setattr(PIL.Image, "open",
                        lambda p: _FakeImage(size=(200, 300)))
    monkeypatch.setattr(PIL.Image, "LANCZOS", 1, raising=False)

    rt.render_crops([_tid("d_TAB_001", x=10, y=10, w=5, h=5)],
                    tmp_path / "crops", tmp_path / "d.pdf")
    call = _FakeImage.calls[0]
    assert call["box"] == (20, 30, 30, 45)     # x2, y3 — not both x2


def test_a_page_with_no_recorded_width_is_skipped_not_defaulted(patched, tmp_path):
    ok, cached, skipped = rt.render_crops(
        [_tid("d_TAB_001", page=99)], tmp_path / "crops", tmp_path / "d.pdf")
    assert (ok, skipped) == (0, 1)
    assert not (tmp_path / "crops" / "d_TAB_001.jpg").exists()


def test_a_row_with_no_region_is_skipped(patched, tmp_path):
    t = {"title": "d_TAB_002", "page": None}
    ok, cached, skipped = rt.render_crops([t], tmp_path / "crops",
                                          tmp_path / "d.pdf")
    assert (ok, skipped) == (0, 1)


def test_a_row_the_cdn_already_serves_is_left_to_download_crops(patched, tmp_path):
    ok, cached, skipped = rt.render_crops(
        [_tid("d_TAB_001", uri="https://cdn.mathpix.com/cropped/x-003.jpg")],
        tmp_path / "crops", tmp_path / "d.pdf")
    assert (ok, cached, skipped) == (0, 0, 0)


def test_only_the_pages_actually_needed_are_rasterized(patched, tmp_path):
    rt.render_crops([_tid("d_TAB_001", page=4), _tid("d_TAB_002", page=4),
                     _tid("d_TAB_003", page=3)],
                    tmp_path / "crops", tmp_path / "d.pdf")
    # three rows, two pages, one rasterize call
    assert patched["asked"] == [3, 4]
    assert len(_FakeImage.calls) == 3


def test_an_existing_crop_is_cached_not_redrawn(patched, tmp_path):
    (tmp_path / "crops").mkdir()
    (tmp_path / "crops" / "d_TAB_001.jpg").write_bytes(b"x" * 900)
    ok, cached, skipped = rt.render_crops(
        [_tid("d_TAB_001")], tmp_path / "crops", tmp_path / "d.pdf")
    assert (ok, cached, skipped) == (0, 1, 0)
    assert not _FakeImage.calls


def test_the_page_comes_from_the_filename_not_the_request_order(patched,
                                                                tmp_path,
                                                                monkeypatch):
    """A stale page left in _pages must not shift every pairing by one."""
    from pdfdrill import pdf_reading

    def rasterize_with_a_stale_file(pdf, out_dir, *, pages=None, **kw):
        out_dir = pathlib.Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "page-0001.png").write_bytes(b"")   # not requested
        for n in pages:
            (out_dir / ("page-%04d.png" % n)).write_bytes(b"")
        return sorted(out_dir.glob("page-*.png"))

    monkeypatch.setattr(pdf_reading, "rasterize", rasterize_with_a_stale_file)
    ok, _c, _s = rt.render_crops([_tid("d_TAB_001", page=3)],
                                 tmp_path / "crops", tmp_path / "d.pdf")
    # zipping request against glob would have paired page 3 with page-0001
    assert ok == 1


def test_the_rasterized_pages_are_not_left_behind(patched, tmp_path):
    rt.render_crops([_tid("d_TAB_001")], tmp_path / "crops",
                    tmp_path / "d.pdf")
    assert not (tmp_path / "crops" / "_pages").exists()


# 671 — render_crops used to cache by TITLE alone: once a file existed it
# was served forever regardless of whether it was cut from the region the
# row now points at. These pin the fix: the cache key is (page, region).


def test_a_legacy_crop_with_no_recorded_geometry_is_trusted_once(patched,
                                                                  tmp_path):
    """A crop rendered before CROP_GEOMETRY_FILE existed has nothing to
    compare against — trust it (unchanged pre-671 behaviour) rather than
    guess, but backfill its provenance for the NEXT call."""
    (tmp_path / "crops").mkdir()
    (tmp_path / "crops" / "d_TAB_001.jpg").write_bytes(b"x" * 900)
    ok, cached, skipped = rt.render_crops(
        [_tid("d_TAB_001", page=3, x=100, y=200, w=300, h=120)],
        tmp_path / "crops", tmp_path / "d.pdf")
    assert (ok, cached, skipped) == (0, 1, 0)
    assert not _FakeImage.calls
    geom = json.loads((tmp_path / "crops" / rt.CROP_GEOMETRY_FILE).read_text())
    assert geom["d_TAB_001"] == [3, 100, 200, 300, 120]


def test_a_crop_whose_row_now_points_at_a_different_region_is_rerendered(
        patched, tmp_path):
    """671's actual defect: a title's row region moved (e.g. a host-line
    join) after the crop was cut. First call records the ORIGINAL region;
    a second call with a DIFFERENT region for the SAME title must not be
    served the stale file — it must be re-rendered."""
    crops = tmp_path / "crops"
    rt.render_crops([_tid("d_TAB_001", page=3, x=100, y=200, w=300, h=120)],
                    crops, tmp_path / "d.pdf")
    assert len(_FakeImage.calls) == 1
    first_box = _FakeImage.calls[0]["box"]

    # the row now points somewhere else on the SAME page
    ok, cached, skipped = rt.render_crops(
        [_tid("d_TAB_001", page=3, x=500, y=900, w=300, h=120)],
        crops, tmp_path / "d.pdf")
    assert (ok, cached, skipped) == (1, 0, 0)
    assert len(_FakeImage.calls) == 2
    assert _FakeImage.calls[1]["box"] != first_box
    geom = json.loads((crops / rt.CROP_GEOMETRY_FILE).read_text())
    assert geom["d_TAB_001"] == [3, 500, 900, 300, 120]


def test_a_crop_whose_row_moved_to_a_different_page_is_rerendered(patched,
                                                                   tmp_path):
    """The join can move a row to a different HOST PAGE entirely, not just
    a different rectangle on the same page — the worked example in the
    671 brief (0902.0431_FO0068: page 4, not page 177)."""
    crops = tmp_path / "crops"
    rt.render_crops([_tid("d_TAB_001", page=3)], crops, tmp_path / "d.pdf")
    ok, cached, skipped = rt.render_crops(
        [_tid("d_TAB_001", page=4)], crops, tmp_path / "d.pdf")
    assert (ok, cached, skipped) == (1, 0, 0)
    geom = json.loads((crops / rt.CROP_GEOMETRY_FILE).read_text())
    assert geom["d_TAB_001"][0] == 4


def test_an_unchanged_row_is_still_cached_after_a_render(patched, tmp_path):
    """The common case: render once, then ask again with the SAME region —
    must stay cached, not re-render on every call."""
    crops = tmp_path / "crops"
    rt.render_crops([_tid("d_TAB_001", page=3, x=100, y=200, w=300, h=120)],
                    crops, tmp_path / "d.pdf")
    assert len(_FakeImage.calls) == 1
    ok, cached, skipped = rt.render_crops(
        [_tid("d_TAB_001", page=3, x=100, y=200, w=300, h=120)],
        crops, tmp_path / "d.pdf")
    assert (ok, cached, skipped) == (0, 1, 0)
    assert len(_FakeImage.calls) == 1


def test_a_row_with_no_current_geometry_falls_back_to_trusting_the_file(
        patched, tmp_path):
    """671 must not regress the pre-existing skip/cache behaviour for a row
    that carries no page at all — there is nothing to compare, so an
    existing file is trusted and a missing one is skipped, exactly as
    before."""
    crops = tmp_path / "crops"
    crops.mkdir()
    (crops / "d_TAB_002.jpg").write_bytes(b"x" * 900)
    t = {"title": "d_TAB_002", "page": None}
    ok, cached, skipped = rt.render_crops([t], crops, tmp_path / "d.pdf")
    assert (ok, cached, skipped) == (0, 1, 0)
