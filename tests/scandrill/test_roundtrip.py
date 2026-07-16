"""End-to-end prototype proof:

1. synthesize page images (two content pages + one blank),
2. ingest the folder → the blank is auto-dropped,
3. assemble the kept pages into a PDF,
4. verify the embed is LOSSLESS — extracted page pixels are bit-identical to the
   source images, and an embedded JPEG stream is byte-identical.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pikepdf
import pytest
from PIL import Image

from pdfdrill.scandrill import ingest as ing
from pdfdrill.scandrill.assemble import assemble
from pdfdrill.scandrill.manifest import Manifest, PENDING, REMOVED_BLANK


def _content_page(seed: int, size=(1240, 1754)) -> Image.Image:  # ~150 dpi A4
    rng = np.random.default_rng(seed)
    arr = np.full((size[1], size[0], 3), 255, dtype=np.uint8)
    # scatter dark rectangles so the page is clearly non-blank
    for _ in range(40):
        x = rng.integers(0, size[0] - 200)
        y = rng.integers(0, size[1] - 40)
        arr[y:y + rng.integers(10, 40), x:x + rng.integers(50, 200)] = rng.integers(0, 60)
    return Image.fromarray(arr, "RGB")


def _blank_page(size=(1240, 1754)) -> Image.Image:
    arr = np.full((size[1], size[0], 3), 255, dtype=np.uint8)
    arr[0:5, 0:5] = 250  # a few near-white specks, still "blank" by mean>0.999
    return Image.fromarray(arr, "RGB")


@pytest.fixture
def job(tmp_path: Path):
    raw = tmp_path / "raw"
    raw.mkdir()
    # page 1: JPEG (tests verbatim DCT passthrough); page 2: PNG; page 3: blank PNG
    _content_page(1).save(raw / "scan_0001.jpg", quality=92)
    _content_page(2).save(raw / "scan_0002.png")
    _blank_page().save(raw / "scan_0003.png")
    return tmp_path, raw


def test_blank_dropped_on_ingest(job):
    tmp_path, raw = job
    m = Manifest(job="t", created="2026-07-15T00:00:00+02:00")
    pages = ing.add_folder(m, raw, order="name", rel_to=raw)
    assert [p.status for p in pages] == [PENDING, PENDING, REMOVED_BLANK]
    kept = m.kept_pages()
    assert len(kept) == 2
    assert {Path(p.src).name for p in kept} == {"scan_0001.jpg", "scan_0002.png"}
    # blank page carries a high mean; content pages do not
    blank = next(p for p in pages if p.status == REMOVED_BLANK)
    assert blank.blank_mean > 0.999


def test_manifest_roundtrip(tmp_path, job):
    _, raw = job
    m = Manifest(job="t", created="2026-07-15T00:00:00+02:00", lang="de-DE")
    ing.add_folder(m, raw, order="name", rel_to=raw)
    p = tmp_path / "t.ingest.json"
    m.save(p)
    m2 = Manifest.load(p)
    assert m2.lang == "de-DE"
    assert [pg.sha256 for pg in m2.pages] == [pg.sha256 for pg in m.pages]


def test_assembly_is_lossless(job):
    tmp_path, raw = job
    m = Manifest(job="t", created="2026-07-15T00:00:00+02:00", lang="de-DE")
    ing.add_folder(m, raw, order="name", rel_to=raw)
    out = assemble(m, tmp_path / "out.pdf", job_dir=raw, title="Prototype")

    kept = sorted(m.kept_pages(), key=lambda pg: pg.seq)
    assert len(kept) == 2

    with pikepdf.open(out) as pdf:
        assert str(pdf.Root.Lang) == "de-DE"
        assert len(pdf.pages) == 2
        # compare decoded pixels of each embedded image to the source image
        for page_obj, src_page in zip(pdf.pages, kept):
            img_key = next(iter(page_obj.images))
            pdfimg = pikepdf.PdfImage(page_obj.images[img_key])
            emb = pdfimg.as_pil_image().convert("RGB")
            src = Image.open(raw / src_page.src).convert("RGB")
            assert np.array_equal(np.asarray(emb), np.asarray(src)), \
                f"pixels differ for {src_page.src}"

        # the JPEG page must be embedded VERBATIM (DCTDecode, identical bytes)
        jpg_page = pdf.pages[0]
        raw_stream = pikepdf.PdfImage(
            jpg_page.images[next(iter(jpg_page.images))]
        ).obj.read_raw_bytes()
        disk_bytes = (raw / "scan_0001.jpg").read_bytes()
        # the stored DCT stream is exactly the file's compressed image data
        assert raw_stream == disk_bytes, "JPEG was re-encoded, not embedded verbatim"


def test_pagelabels_present(job):
    tmp_path, raw = job
    m = Manifest(job="t", created="2026-07-15T00:00:00+02:00")
    ing.add_folder(m, raw, order="name", rel_to=raw)
    out = assemble(m, tmp_path / "out.pdf", job_dir=raw)
    with pikepdf.open(out) as pdf:
        assert "/PageLabels" in pdf.Root
