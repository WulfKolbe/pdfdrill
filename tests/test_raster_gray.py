"""Analysis pages are rendered as raw grayscale, and streamed.

Measured, 8 pages at 400 DPI of the 110-page Infineon handbook, render then
read into numpy:

    device     render     read    total   MB/8pp
    png16m      2362m     875m    3236m      2.9     <- what analysis used
    pnggray     1060m     260m    1319m      1.7
    pgmraw       323m      89m     413m    118.0

7.8x. Half of that is not the encoder at all — dropping RGB for grayscale is
2.5x on its own, and analysis never wanted colour. The other half is the PNG
encode/decode round trip, which only pays off if someone looks at the file.

The catch is in the last column: 14.75 MB per page. Writing a whole document
as pgmraw is not an option (the corpus's largest is 11232 pages = 165 GB), so
raw pages are STREAMED — rendered in blocks, consumed, deleted. Peak disk is
the block, not the document.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import pdf_reading as pr


def _dev(args):
    return next(a.split("=", 1)[1] for a in args if a.startswith("-sDEVICE="))


def test_the_device_follows_the_extension():
    """png16m for anything a person opens; pgmraw for pixels nobody looks at."""
    assert _dev(pr._gs_base("gs", 400, "png")) == "png16m"
    assert _dev(pr._gs_base("gs", 400, "jpg")) == "jpeg"
    assert _dev(pr._gs_base("gs", 400, "pgm")) == "pgmraw"


def test_grayscale_png_is_available_without_giving_up_the_encoder():
    """For a consumer that must hand a real PNG to a library but does not need
    colour: 2.5x for free, and half the bytes."""
    assert _dev(pr._gs_base("gs", 400, "png", gray=True)) == "pnggray"
    assert _dev(pr._gs_base("gs", 400, "pgm", gray=True)) == "pgmraw"


def test_a_raw_page_is_not_asked_for_jpeg_quality():
    assert not any("JPEGQ" in a for a in pr._gs_base("gs", 400, "pgm"))


# ------------------------------------------------------------------ streaming
class _FakeRender:
    """Stands in for Ghostscript: writes the files a real render would."""

    def __init__(self, out_root):
        self.blocks = []
        self.out_root = out_root

    def __call__(self, pdf, out_dir, *, pages, dpi, fmt):
        self.blocks.append(list(pages))
        made = []
        for p in pages:
            f = Path(out_dir) / f"page-{p:04d}.{fmt}"
            f.write_bytes(b"P5\n1 1\n255\n\x00")
            made.append(f)
        return made


def test_streaming_yields_pages_in_order_with_their_true_numbers(tmp_path, monkeypatch):
    fake = _FakeRender(tmp_path)
    monkeypatch.setattr(pr, "rasterize", fake)
    got = [(n, p.name) for n, p in pr.stream_pages(Path("x.pdf"), [3, 4, 5],
                                                   dpi=400, block=2)]
    assert got == [(3, "page-0003.pgm"), (4, "page-0004.pgm"), (5, "page-0005.pgm")]
    assert fake.blocks == [[3, 4], [5]]         # rendered in blocks, not one by one


def test_a_consumed_page_is_deleted_so_peak_disk_is_the_block(tmp_path, monkeypatch):
    """14.75 MB/page at 400 DPI: on the corpus's largest document, keeping them
    all would be 165 GB. This is the property that makes raw output usable."""
    monkeypatch.setattr(pr, "rasterize", _FakeRender(tmp_path))
    live = []
    for _n, p in pr.stream_pages(Path("x.pdf"), list(range(1, 7)), dpi=400, block=2):
        assert p.exists()                        # the current page is there ...
        live.append(sum(1 for f in Path(p).parent.glob("*.pgm")))
    assert max(live) <= 2                        # ... and at most one block is
    assert live[-1] >= 1


def test_the_scratch_directory_does_not_survive_the_stream(tmp_path, monkeypatch):
    monkeypatch.setattr(pr, "rasterize", _FakeRender(tmp_path))
    seen = None
    for _n, p in pr.stream_pages(Path("x.pdf"), [1, 2], dpi=400, block=2):
        seen = Path(p).parent
    assert seen is not None and not seen.exists()


def test_abandoning_the_stream_early_still_cleans_up(tmp_path, monkeypatch):
    """A caller that breaks out — found its QR code on page 2 of 900 — must not
    leave gigabytes behind."""
    monkeypatch.setattr(pr, "rasterize", _FakeRender(tmp_path))
    gen = pr.stream_pages(Path("x.pdf"), list(range(1, 20)), dpi=400, block=4)
    n, p = next(gen)
    scratch = Path(p).parent
    assert scratch.exists()
    gen.close()
    assert not scratch.exists()


@pytest.mark.skipif(pr.gs_binary() is None, reason="ghostscript not installed")
def test_a_real_pgm_page_is_grayscale_and_readable(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    np = pytest.importorskip("numpy")
    Image = pytest.importorskip("PIL.Image")

    w = pypdf.PdfWriter()
    w.add_blank_page(width=200, height=200)
    pdf = tmp_path / "one.pdf"
    with open(pdf, "wb") as fh:
        w.write(fh)

    pages = list(pr.stream_pages(pdf, [1], dpi=400, block=1))
    assert len(pages) == 1
    n, p = pages[0]
    # consumed inside the loop in real use; here we only need the shape it had
    assert n == 1 and p.suffix == ".pgm"
