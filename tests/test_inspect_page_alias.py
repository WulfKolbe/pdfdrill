"""The inspector's page image must track the rasterizer, not freeze at first use.

`_inspect_pages_dir` renders to `page-<NNNN>.png` and hardlinks each to the
`p{N}.png` name the inspector reads. The link was created only `if not
target.exists()`, so once `p8.png` existed it was never refreshed: re-rendering
at a different DPI updated the canonical file and left the alias behind. The
inspector then showed an old render of the page while a current one sat beside
it, with no error anywhere.

Reproduced on 2409.18839 page 8 — canonical 5100x6600, alias still 3400x4400.
Found by the external audit's per-page test case (T4/T6); the mechanism here is
measured, not inferred.

The hardlink alone cannot hold this together: `rasterize` finalises with
`src.replace(dest)`, a rename onto a NEW inode, so the pair is unlinked after
the first re-render even when the bytes still agree.
"""
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import commands


def _png(path: Path, w: int, h: int):
    """A minimal but structurally valid PNG whose IHDR carries w x h."""
    ihdr = struct.pack(">II", w, h) + b"\x08\x02\x00\x00\x00"
    chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + b"\x00\x00\x00\x00"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk)


def _dims(path: Path):
    d = path.read_bytes()[:24]
    return struct.unpack(">II", d[16:24])


def _fake_rasterize(tmp, w, h):
    """Stand in for pdf_reading.rasterize — including how it FINALISES.

    The real one renders to a temp directory and finishes with
    `src.replace(dest)`, a rename that puts a NEW INODE behind the canonical
    name. A fake that writes the file in place shares the hardlinked inode, so
    the alias appears to update itself and the test passes while the product is
    broken. It did, on the first version of this file.
    """
    def _r(pdf, out_dir, *, pages=None, dpi=400, fmt="png"):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        made = []
        for n in (pages or [1]):
            staging = out_dir / f".staging-{n:04d}.png"
            _png(staging, w, h)
            dest = out_dir / f"page-{n:04d}.png"
            staging.replace(dest)                 # rename: new inode, link broken
            made.append(dest)
        return made
    return _r


class _SC:
    def __init__(self, blob):
        self.blob_dir = Path(blob)
        self.page_count = 12


def test_the_alias_follows_a_re_render_at_a_different_dpi(tmp_path, monkeypatch):
    sc = _SC(tmp_path)
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    pages = tmp_path / "inspect" / "pages"

    import pdfdrill.pdf_reading as pr
    monkeypatch.setattr(pr, "rasterize", _fake_rasterize(tmp_path, 3400, 4400))
    monkeypatch.setattr(pr, "parse_pages", lambda spec, n: [8])
    commands._inspect_pages_dir(pdf, sc, "8", 400)
    assert _dims(pages / "p8.png") == (3400, 4400)

    monkeypatch.setattr(pr, "rasterize", _fake_rasterize(tmp_path, 5100, 6600))
    commands._inspect_pages_dir(pdf, sc, "8", 600)
    assert _dims(pages / "page-0008.png") == (5100, 6600)
    assert _dims(pages / "p8.png") == (5100, 6600), \
        "the inspector's page image is frozen at the DPI first used"


def test_an_unrelated_page_is_not_disturbed(tmp_path, monkeypatch):
    sc = _SC(tmp_path)
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    pages = tmp_path / "inspect" / "pages"
    pages.mkdir(parents=True)
    _png(pages / "p3.png", 1, 1)                     # a page nobody re-rendered

    import pdfdrill.pdf_reading as pr
    monkeypatch.setattr(pr, "rasterize", _fake_rasterize(tmp_path, 5100, 6600))
    monkeypatch.setattr(pr, "parse_pages", lambda spec, n: [8])
    commands._inspect_pages_dir(pdf, sc, "8", 600)
    assert _dims(pages / "p3.png") == (1, 1)


def test_the_alias_and_the_canonical_file_agree_after_every_render(tmp_path, monkeypatch):
    """The property that matters, independent of how it is achieved — the
    hardlink cannot provide it, because `rasterize` renames onto a new inode."""
    sc = _SC(tmp_path)
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    pages = tmp_path / "inspect" / "pages"
    import pdfdrill.pdf_reading as pr
    monkeypatch.setattr(pr, "parse_pages", lambda spec, n: [8])
    for w, h in ((3400, 4400), (5100, 6600), (1700, 2200)):
        monkeypatch.setattr(pr, "rasterize", _fake_rasterize(tmp_path, w, h))
        commands._inspect_pages_dir(pdf, sc, "8", 400)
        assert _dims(pages / "p8.png") == _dims(pages / "page-0008.png") == (w, h)
