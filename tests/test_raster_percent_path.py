"""Ghostscript reads `%` in `-sOutputFile` as a format specifier.

A document downloaded by URL keeps its percent-encoding in the filename, so its
drill folder is a path full of `%E2%80%8B`-style escapes. Handed that as an
output path, gs consumed the escapes as format specifiers, wrote NOTHING, printed
"Page drawing error occurred" to stdout — and exited **0**. `check=True` saw a
clean exit, `rasterize` globbed an empty directory and returned `[]`, and every
caller read that as "this document has no pages".

Nothing raised. Nothing logged. `pdfdrill inspect` on such a document produced a
boxes-only inspector, `ocr`/`vision`/`visionocr` silently had no images to work
on, and a corpus run counted the document as rendered-ok with zero pages.

Two defences, because either alone still fails quietly:
  * gs is never shown a caller-supplied path in its output template
  * a shard that renders nothing says so instead of returning empty
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import pdf_reading

_HAVE_GS = shutil.which("gs") is not None

# The real shape: percent-escapes as produced by URL-encoding a title.
_NASTY = "%E2%80%8B%EF%BB%BFPaper%20%E2%80%94%20Title%2C%20v2"


def _pdf(tmp_path: Path, pages: int = 3) -> Path:
    pypdf = pytest.importorskip("pypdf")
    w = pypdf.PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=200, height=200)
    p = tmp_path / "src.pdf"
    with open(p, "wb") as fh:
        w.write(fh)
    return p


@pytest.mark.skipif(not _HAVE_GS, reason="ghostscript not installed")
def test_rasterize_into_a_path_containing_percent_escapes(tmp_path):
    pdf = _pdf(tmp_path, pages=3)
    out = tmp_path / _NASTY / "inspect" / "pages"
    imgs = pdf_reading.rasterize(pdf, out, pages=[1, 3], dpi=400)
    assert [p.name for p in imgs] == ["page-0001.png", "page-0003.png"]
    assert all(p.stat().st_size > 0 for p in imgs)


@pytest.mark.skipif(not _HAVE_GS, reason="ghostscript not installed")
def test_rasterize_from_a_pdf_whose_own_name_has_percent_escapes(tmp_path):
    """The INPUT filename carries the escapes too — that is where they come
    from — so both sides of the gs command line have to survive them."""
    pdf = _pdf(tmp_path, pages=2)
    nasty_pdf = tmp_path / f"{_NASTY}.pdf"
    nasty_pdf.write_bytes(pdf.read_bytes())
    imgs = pdf_reading.rasterize(nasty_pdf, tmp_path / "out", pages=[2], dpi=400)
    assert [p.name for p in imgs] == ["page-0002.png"]


@pytest.mark.skipif(not _HAVE_GS, reason="ghostscript not installed")
def test_render_page_into_a_percent_path(tmp_path):
    pdf = _pdf(tmp_path, pages=2)
    target = tmp_path / _NASTY / "crop.png"
    got = pdf_reading.render_page(pdf, 2, target, dpi=400)
    assert got.exists() and got.stat().st_size > 0


@pytest.mark.skipif(not _HAVE_GS, reason="ghostscript not installed")
def test_a_plain_path_still_works(tmp_path):
    """The fix routes every render through a new output path — the ordinary
    case must be unchanged, including the true page numbering."""
    pdf = _pdf(tmp_path, pages=5)
    imgs = pdf_reading.rasterize(pdf, tmp_path / "out", pages=[2, 3, 5], dpi=400)
    assert [p.name for p in imgs] == ["page-0002.png", "page-0003.png",
                                      "page-0005.png"]


def test_a_shard_that_renders_nothing_raises(tmp_path, monkeypatch):
    """gs exiting 0 having written no file is the failure mode that hid this for
    good. A clean exit is not evidence of output, so the shard checks."""
    def _no_output(*a, **k):
        return subprocess.CompletedProcess(a[0] if a else [], 0, b"", b"")
    monkeypatch.setattr(pdf_reading.subprocess, "run", _no_output)

    with pytest.raises(RuntimeError) as ei:
        pdf_reading._render_shard(["gs"], tmp_path / "x.pdf", [1, 2],
                                  tmp_path / "out", "png", 4)
    msg = str(ei.value).lower()
    assert "ghostscript" in msg or "gs " in msg
    assert "1" in msg and "2" in msg          # names the pages it failed on


def test_a_shard_that_renders_nothing_reports_the_gs_output(tmp_path, monkeypatch):
    """gs puts its explanation on stdout, not stderr, and exits 0 — so the
    message has to carry stdout or the error says nothing useful."""
    def _no_output(*a, **k):
        return subprocess.CompletedProcess(a[0] if a else [], 0,
                                           b"**** Error: Page drawing error occurred.", b"")
    monkeypatch.setattr(pdf_reading.subprocess, "run", _no_output)

    with pytest.raises(RuntimeError) as ei:
        pdf_reading._render_shard(["gs"], tmp_path / "x.pdf", [1],
                                  tmp_path / "out", "png", 4)
    assert "Page drawing error" in str(ei.value)


@pytest.mark.skipif(not _HAVE_GS, reason="ghostscript not installed")
def test_a_relative_pdf_path_still_resolves(tmp_path, monkeypatch):
    """gs now runs with `cwd` set to a temp directory so it never parses a
    caller path. A RELATIVE input path — what a caller working inside the drill
    folder passes — then resolved against that temp dir instead of the caller's
    cwd, and gs failed with 'file not found' on a PDF sitting right there."""
    pdf = _pdf(tmp_path, pages=2)
    monkeypatch.chdir(tmp_path)
    imgs = pdf_reading.rasterize(Path("src.pdf"), Path("out"), pages=[1], dpi=400)
    assert [p.name for p in imgs] == ["page-0001.png"]

    got = pdf_reading.render_page(Path("src.pdf"), 2, Path("out/one.png"), dpi=400)
    assert got.exists() and got.stat().st_size > 0
