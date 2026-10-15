"""T-0024 — a crop comes from the page it says it does.

`rasterize` returned `sorted(out_dir.glob("page-*.png"))`: every page in the
directory, not the pages the caller asked for. Three callers share one
directory across calls, two of them took `imgs[0]`, and so each crop after the
first came from the LOWEST page number present — at its own region's
coordinates, scaled by its own page's dimensions. Nothing failed; the crops
looked like crops. On one measured document 131 of 138 rows were cropped from
the wrong page, and the "lowest page so far" model reproduced the stored
signatures 138 of 138.

The tests below are of the contract, not of a document: a caller that names
pages is handed those pages, and a caller that names ONE page crops THAT page.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from pdfdrill import pdf_reading


# ── the contract: only what was asked for ──────────────────────────────────

def _page(dir_: Path, n: int, ext: str = "png") -> Path:
    f = dir_ / f"page-{n:04d}.{ext}"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(b"")
    return f


def test_page_of_reads_the_number_back(tmp_path):
    assert pdf_reading.page_of(_page(tmp_path, 7)) == 7
    assert pdf_reading.page_of(tmp_path / "page-11232.png") == 11232
    assert pdf_reading.page_of(tmp_path / "scan.png") is None


def test_a_shared_directory_does_not_leak_the_previous_call(tmp_path, monkeypatch):
    """Two calls, one directory — the second is handed page 5, not pages 3+5.

    This is refine's shape: `<doc>/refine/_pages` is shared by every row of a
    run and is not cleared between runs.
    """
    out = tmp_path / "_pages"
    rendered: list[list[int]] = []

    def fake_shard(base, pdf, pages, out_dir, ext, pad):
        rendered.append(list(pages))
        for n in pages:
            _page(out_dir, n, ext)

    monkeypatch.setattr(pdf_reading, "_require_gs", lambda: "gs")
    monkeypatch.setattr(pdf_reading, "_render_shard", fake_shard)

    first = pdf_reading.rasterize(tmp_path / "x.pdf", out, pages=[3], dpi=400)
    assert [p.name for p in first] == ["page-0003.png"]

    second = pdf_reading.rasterize(tmp_path / "x.pdf", out, pages=[5], dpi=400)
    assert [p.name for p in second] == ["page-0005.png"], (
        "the previous call's page came back as this call's")
    assert pdf_reading.page_of(second[0]) == 5
    # The file itself is left alone — the defect was the return value.
    assert (out / "page-0003.png").is_file()


def test_the_pages_come_back_in_page_order(tmp_path, monkeypatch):
    """Not filename order: page-11232 sorts before page-9999 as a string."""
    out = tmp_path / "_pages"
    monkeypatch.setattr(pdf_reading, "_require_gs", lambda: "gs")
    monkeypatch.setattr(
        pdf_reading, "_render_shard",
        lambda base, pdf, pages, out_dir, ext, pad: [
            _page(out_dir, n, ext) for n in pages])
    got = pdf_reading.rasterize(tmp_path / "x.pdf", out,
                                pages=[11232, 9999, 2], dpi=400)
    assert [pdf_reading.page_of(f) for f in got] == [2, 9999, 11232]


def test_a_page_another_document_left_behind_is_not_served(tmp_path, monkeypatch):
    out = tmp_path / "_pages"
    _page(out, 1)                      # a crashed run's leftover
    monkeypatch.setattr(pdf_reading, "_require_gs", lambda: "gs")
    monkeypatch.setattr(
        pdf_reading, "_render_shard",
        lambda base, pdf, pages, out_dir, ext, pad: [
            _page(out_dir, n, ext) for n in pages])
    monkeypatch.setattr(pdf_reading, "_page_count", lambda pdf: 2)
    got = pdf_reading.rasterize(tmp_path / "x.pdf", out, pages=[2], dpi=400)
    assert [pdf_reading.page_of(f) for f in got] == [2]


# ── the two croppers: a row from page k is cropped from page k ─────────────

def _solid(path: Path, size, colour) -> None:
    Image = pytest.importorskip("PIL.Image")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, colour).save(path)


@pytest.fixture()
def pages_of_known_colour(tmp_path, monkeypatch):
    """A fake rasterizer: page N is a solid page whose red channel is N.

    So a crop's own pixels say which page it was taken from — the question the
    defect made unanswerable from the output alone.
    """
    Image = pytest.importorskip("PIL.Image")

    def fake_rasterize(pdf, out_dir, *, pages=None, dpi=400, fmt="png",
                       gray=False, use_cropbox=False):
        out_dir = Path(out_dir)
        for n in (pages or []):
            f = out_dir / f"page-{n:04d}.png"
            if not f.is_file():
                _solid(f, (400, 800), (n, 0, 0))
        # The defect, deliberately: EVERY page in the directory, lowest first.
        return sorted(out_dir.glob("page-*.png"))

    monkeypatch.setattr(pdf_reading, "rasterize", fake_rasterize)
    return Image


def test_scan_crop_takes_the_row_s_own_page(tmp_path, pages_of_known_colour):
    from pdfdrill import refine

    region = {"top_left_x": 10, "top_left_y": 20, "width": 50, "height": 40}
    work = tmp_path / "refine"

    first = refine.scan_crop(tmp_path / "x.pdf", 3, region,
                             work / "EQ0001.scan.png",
                             page_width=200, page_height=400, dpi=400)
    assert first is not None
    assert pages_of_known_colour.open(first).getpixel((0, 0))[0] == 3

    # Page 7, with page 3 already sitting in the shared `_pages` directory.
    second = refine.scan_crop(tmp_path / "x.pdf", 7, region,
                              work / "EQ0002.scan.png",
                              page_width=200, page_height=400, dpi=400)
    assert second is not None
    assert pages_of_known_colour.open(second).getpixel((0, 0))[0] == 7, (
        "the row's crop came from a page it does not sit on")


def test_scan_crop_refuses_rather_than_crop_a_neighbour(tmp_path, monkeypatch):
    """The page could not be rendered: None, not the page next to it."""
    from pdfdrill import refine
    pytest.importorskip("PIL.Image")

    def only_page_3(pdf, out_dir, *, pages=None, **kw):
        out_dir = Path(out_dir)
        _solid(out_dir / "page-0003.png", (400, 800), (3, 0, 0))
        return sorted(out_dir.glob("page-*.png"))

    monkeypatch.setattr(pdf_reading, "rasterize", only_page_3)
    assert refine.scan_crop(
        tmp_path / "x.pdf", 7,
        {"top_left_x": 1, "top_left_y": 2, "width": 5, "height": 5},
        tmp_path / "r" / "EQ.scan.png",
        page_width=200, page_height=400, dpi=400) is None


def test_snip_crops_the_page_it_was_asked_for(tmp_path, pages_of_known_colour):
    from pdfdrill import commands

    class _SC:
        blob_dir = tmp_path / ".drill"

    first = commands._deliver_region_crop(tmp_path / "x.pdf", _SC(), 3,
                                          (0, 0, 20, 20), ppi=400)
    assert pages_of_known_colour.open(first).getpixel((0, 0))[0] == 3

    second = commands._deliver_region_crop(tmp_path / "x.pdf", _SC(), 7,
                                           (0, 0, 20, 20), ppi=400)
    assert pages_of_known_colour.open(second).getpixel((0, 0))[0] == 7, (
        "snip delivered a crop of another page under this page's name")
