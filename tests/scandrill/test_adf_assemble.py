"""Does assembly embed the DESKEWED pages, or silently the raw ones?

`apply_deskew` repoints `Page.src` at `proc/`, and `assemble` resolves `Page.src`
against the job dir — so it *should* follow. That is a load-bearing assumption
worth an actual test rather than a reading of the code: getting it wrong would
ship visibly skewed PDFs while every skew test still passed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pikepdf
import pytest
from PIL import Image

from pdfdrill.scandrill.assemble import assemble, resolve_srcs
from pdfdrill.scandrill.config import Config
from pdfdrill.scandrill.manifest import Manifest
from pdfdrill.scandrill.producers import adf
from pdfdrill.scandrill.tools import DEFAULT as DEFAULT_TOOLS

needs_bt = pytest.mark.skipif(
    DEFAULT_TOOLS._blobtracker() is None, reason="BlobTracker not available"
)


def _ruled_page(angle: float = 0.0, size=(850, 1100)) -> Image.Image:
    arr = np.full((size[1], size[0]), 255, dtype=np.uint8)
    for y in range(150, size[1] - 150, 80):
        arr[y:y + 3, 80:size[0] - 80] = 0
    im = Image.fromarray(arr, "L")
    if angle:
        im = im.rotate(angle, resample=Image.BILINEAR, fillcolor=255)
    return im


@pytest.fixture
def deskewed_job(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    _ruled_page(2.0).save(raw / "raw_1.png")      # front, clearly skewed
    # a genuinely blank back (all white) — it must be dropped, not assembled
    Image.fromarray(np.full((1100, 850), 255, dtype=np.uint8), "L").save(raw / "raw_2.png")
    m = Manifest(job="asm", created="2026-07-15T00:00:00+02:00", lang="de-DE")
    pages = adf.ingest_raw_dir(m, raw, device="d", rel_to=raw)
    adf.measure_skew(pages, job_dir=raw)
    rotated = adf.apply_deskew(pages, job_dir=raw, cfg=Config())
    return tmp_path, raw, m, pages, rotated


@needs_bt
def test_apply_deskew_repoints_src_into_proc(deskewed_job):
    _tmp, raw, _m, pages, rotated = deskewed_job
    assert rotated == 1
    front = pages[0]
    assert front.src.startswith("proc/"), f"src still {front.src!r}"
    assert front.extra["raw_src"] == "raw_1.png"
    assert (raw / front.src).exists()
    assert (raw / "raw_1.png").exists(), "raw must survive"


@needs_bt
def test_resolve_srcs_points_at_proc_not_raw(deskewed_job):
    _tmp, raw, m, _pages, _r = deskewed_job
    srcs = resolve_srcs(m, job_dir=raw)
    assert len(srcs) == 1, "the blank back must not be assembled"
    assert srcs[0].parent.name == "proc"
    assert srcs[0].exists()


@needs_bt
def test_assembled_pdf_contains_the_deskewed_pixels(deskewed_job):
    """The decisive check: compare the PDF's embedded image against BOTH the raw
    and the deskewed file. It must match the deskewed one and differ from raw."""
    tmp_path, raw, m, pages, _r = deskewed_job
    out = assemble(m, tmp_path / "out.pdf", job_dir=raw, title="Deskewed")

    front = pages[0]
    deskewed_px = np.asarray(Image.open(raw / front.src).convert("L"))
    raw_px = np.asarray(Image.open(raw / front.extra["raw_src"]).convert("L"))
    assert not np.array_equal(deskewed_px, raw_px), "fixture is not discriminating"

    with pikepdf.open(out) as pdf:
        assert len(pdf.pages) == 1
        page = pdf.pages[0]
        img = pikepdf.PdfImage(page.images[next(iter(page.images))])
        embedded = np.asarray(img.as_pil_image().convert("L"))

    assert np.array_equal(embedded, deskewed_px), \
        "PDF embedded something other than the deskewed page"
    assert not np.array_equal(embedded, raw_px), \
        "PDF embedded the RAW (still-skewed) page — deskew never reached assembly"


@needs_bt
def test_deskewed_page_embeds_losslessly(deskewed_job):
    """Deskewing must not cost the lossless-embed guarantee: the rotated PNG's
    pixels still land in the PDF bit-for-bit."""
    tmp_path, raw, m, pages, _r = deskewed_job
    out = assemble(m, tmp_path / "out.pdf", job_dir=raw)
    src_px = np.asarray(Image.open(raw / pages[0].src).convert("L"))
    with pikepdf.open(out) as pdf:
        page = pdf.pages[0]
        img = pikepdf.PdfImage(page.images[next(iter(page.images))])
        assert np.array_equal(np.asarray(img.as_pil_image().convert("L")), src_px)
