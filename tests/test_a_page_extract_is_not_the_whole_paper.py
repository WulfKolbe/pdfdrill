"""T-0153 #4 — a one-page extract must not be widened into the whole paper.

`pdfdrill model` on a page extract named like an arXiv id built the WHOLE
paper from the author's e-print. Two separate things have to be true for that
not to happen, and only the first is about the filename.

(a) READING AN ID OFF A FILENAME IS ANCHORED. `_arxiv_id_for` falls back to
    `sources.parse_arxiv_id(pdf.stem)`, which SEARCHES: on the stem
    `1805.01788-p0003` it finds `1805.01788` and the document becomes that
    paper. `sources._BARE_ARXIV` is the same pattern anchored at the end and
    is already in the module -- `bare_arxiv_id` uses it -- and it answers None
    for every page-extract name and the correct id for every real one,
    including `2402.13444v1` and `arxiv.2408.15090`.

    This is NOT a rule about the board's `-p%04d` naming (which lives in
    another repo, `board_run.py:804`). It is a rule about what a filename can
    be evidence FOR: `<id>.pdf` is what arXiv and pdfdrill's own downloader
    name an e-print, and anything with text after the id is somebody's own
    name for their own file.

(b) AND THE ID MAY BE RIGHT WHILE THE DOCUMENT IS STILL ONE PAGE OF IT.
    `cmd_provenance` reads the arXiv STAMP off the page and records
    `source_arxiv_id`, and a page extract carries its parent paper's stamp --
    so (a) removes the trigger that was found, not the defect. The invariant
    that holds however the id was learned: a model may not hold more pages
    than the PDF has.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfdrill import sources                      # noqa: E402


# ------------------------------------------------------- (a) the filename
#: (stem, the id it may be evidence for)
NAMES = [
    # page extracts -- the whole point
    ("1805.01788-p0003", None),
    ("2312.11532-p0007", None),
    ("2311.09533v3-p0010", None),
    ("1511.08771-p2709", None),
    # somebody's own name for their own file
    ("2402.13444v1-final", None),
    ("2402.13444 (1)", None),
    ("1805.01788-notes", None),
    # real e-print names, which must keep working
    ("1805.01788", "1805.01788"),
    ("2402.13444v1", "2402.13444v1"),
    ("arxiv.2408.15090", "2408.15090"),
    ("0805.0311v3", "0805.0311v3"),
    ("math.GM/0405123", "math.GM/0405123"),
    # not arXiv at all
    ("0864-p0004", None),
    ("BH1-9add65ca-p0113", None),
    ("lib_025faeafae2f-p0153", None),
]


@pytest.mark.parametrize("stem,want", NAMES)
def test_an_id_read_off_a_filename_is_the_whole_stem(stem, want):
    got = sources.filename_arxiv_id(stem)
    assert got == want, (
        f"{stem!r}: filename gave {got!r}, expected {want!r}")


def test_the_unanchored_parser_is_untouched():
    """`parse_arxiv_id` still searches, because a URL or an `arXiv:...` token
    legitimately carries the id in the middle of a longer string. The change
    is about FILENAMES, so it is a different function."""
    assert sources.parse_arxiv_id(
        "https://arxiv.org/abs/1805.01788") == "1805.01788"
    assert sources.parse_arxiv_id("arXiv:1805.01788v2") == "1805.01788v2"
    assert sources.parse_arxiv_id("1805.01788-p0003") == "1805.01788", (
        "the searching parser was changed instead of the filename path")


def test_a_page_extract_has_no_arxiv_source_lane(tmp_path):
    """The lane asks the same question (`arxiv_source_for` -> `_arxiv_id_for`),
    so the extract must not be offered the author's LaTeX either."""
    from pdfdrill import ocr_router as R
    from pdfdrill.sidecar import Sidecar
    pdf = tmp_path / "1805.01788-p0003.pdf"
    pdf.write_bytes(b"%PDF-1.7 not-a-real-pdf\n%%EOF\n")
    assert R.arxiv_source_for(pdf, Sidecar(pdf)) is False


def test_a_real_eprint_name_still_gets_the_source_lane(tmp_path):
    """The regression guard. Breaking this retires the free source lane."""
    from pdfdrill import ocr_router as R
    from pdfdrill.sidecar import Sidecar
    pdf = tmp_path / "1805.01788.pdf"
    pdf.write_bytes(b"%PDF-1.7 not-a-real-pdf\n%%EOF\n")
    assert R.arxiv_source_for(pdf, Sidecar(pdf)) is True


def test_a_recorded_id_still_wins_over_the_filename(tmp_path):
    """`source_arxiv_id` is the STRONG evidence (a resolved URL, or a stamp
    `cmd_provenance` read off the page) and the filename is the fallback.
    Making the fallback strict may not touch the recorded fact."""
    from pdfdrill.commands import _arxiv_id_for
    from pdfdrill.sidecar import Sidecar
    pdf = tmp_path / "scholar-download.pdf"
    pdf.write_bytes(b"%PDF-1.7 not-a-real-pdf\n%%EOF\n")
    sc = Sidecar(pdf)
    sc.set_evidence("source_arxiv_id", "1805.01788")
    sc.save()
    assert _arxiv_id_for(pdf, Sidecar(pdf)) == "1805.01788"
