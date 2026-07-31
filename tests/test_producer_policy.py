"""
Producer-driven routing policy + the arXiv "no LaTeX source" download bug.

Two edge cases found on one document:

1. `pdfinfo` is the CHEAPEST signal and must be consulted before choosing an
   extraction lane. A PDF whose Producer is OpenOffice.org encodes its glyphs in
   a way our pdfminer lane mishandles, so that lane is DECLINED for this family;
   pdftotext / MathPix / tesseract handle it fine.

2. arXiv's e-print endpoint returns the PDF itself when a submission has NO
   LaTeX source. It was saved as `<id>.tgz` regardless — a PDF wearing a tarball
   name, which then failed to unpack.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.producer_policy import (avoid_pdfminer, producer_family,
                                      policy_note, PDFMINER_UNSAFE_PRODUCERS)


# --- 1) producer -> lane policy ---------------------------------------------

def test_openoffice_producers_decline_the_pdfminer_lane():
    for p in ("OpenOffice.org 3.2", "OpenOffice 4.1.0",
              "OpenOffice.org 2.4", "openoffice.org 3.2"):
        assert avoid_pdfminer(p), p
        assert producer_family(p) == "openoffice"


def test_unrelated_producers_keep_the_pdfminer_lane():
    for p in ("pdfTeX-1.40.25", "Acrobat Distiller 5.0.5 (Windows)",
              "GPL Ghostscript 9.05", "Microsoft® Word 2019", "Skia/PDF m120",
              "", None):
        assert not avoid_pdfminer(p), p


def test_policy_note_names_the_producer_and_the_working_lanes():
    note = policy_note("OpenOffice.org 3.2")
    assert "OpenOffice" in note
    for lane in ("pdftotext", "MathPix", "tesseract"):
        assert lane in note
    assert policy_note("pdfTeX-1.40.25") == ""


def test_the_unsafe_set_is_explicit_not_a_catch_all():
    """Guard against over-reach: the policy must not silently disable the free
    lane for every producer that merely contains 'office' or 'writer'."""
    assert PDFMINER_UNSAFE_PRODUCERS
    assert not avoid_pdfminer("LibreOffice 24.2")   # separate lineage; not declared unsafe
    assert not avoid_pdfminer("Writer")


# --- 2) arXiv e-print that is really a PDF ----------------------------------

def test_eprint_payload_sniffing():
    from pdfdrill.sources import looks_like_pdf_bytes, looks_like_source_archive
    assert looks_like_pdf_bytes(b"%PDF-1.4\n%\xe2\xe3")
    assert not looks_like_pdf_bytes(b"\x1f\x8b\x08\x00")          # gzip
    assert looks_like_source_archive(b"\x1f\x8b\x08\x00")          # .tar.gz / .gz
    assert looks_like_source_archive(b"\\documentclass{article}")  # bare .tex
    assert not looks_like_source_archive(b"%PDF-1.4")


def test_download_arxiv_source_rejects_a_pdf_payload(tmp_path, monkeypatch):
    """arXiv serves the PDF when there is no LaTeX source — that must NOT be
    saved as `<id>.tgz`; it must raise and leave no bogus tarball behind."""
    from pdfdrill import sources

    def fake_download(url, dest):
        Path(dest).write_bytes(b"%PDF-1.4\n%fake pdf, no latex source\n")
        return Path(dest)
    monkeypatch.setattr(sources, "download", fake_download)

    try:
        sources.download_arxiv_source("2101.00001", tmp_path)
    except sources.NoLatexSource as e:
        assert "no LaTeX source" in str(e).lower() or "pdf" in str(e).lower()
    else:
        raise AssertionError("expected NoLatexSource")
    assert not (tmp_path / "2101.00001.tgz").exists()   # no PDF-as-tarball left


def test_download_arxiv_source_keeps_a_real_archive(tmp_path, monkeypatch):
    from pdfdrill import sources

    def fake_download(url, dest):
        Path(dest).write_bytes(b"\x1f\x8b\x08\x00rest-of-a-real-tarball")
        return Path(dest)
    monkeypatch.setattr(sources, "download", fake_download)

    out = sources.download_arxiv_source("2101.00002", tmp_path)
    assert out.exists() and out.suffix == ".tgz"


# --- 3) the policy is actually WIRED into the lane ---------------------------

def test_born_digital_lane_refuses_a_declined_producer(tmp_path, monkeypatch):
    """`_write_born_digital_lines` must return False for a declined producer —
    BEFORE parsing anything — so the caller falls through to MathPix/tesseract."""
    from pdfdrill import commands as C
    pdf = tmp_path / "ooo.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(C, "_pdf_producer", lambda p: "OpenOffice.org 3.2")
    def _boom(p):
        raise AssertionError("must not parse a declined producer")
    monkeypatch.setattr(C, "_born_digital_char_dump", _boom)
    assert C._write_born_digital_lines(pdf) is False

    # an unrelated producer is NOT declined (the dump is reached)
    monkeypatch.setattr(C, "_pdf_producer", lambda p: "pdfTeX-1.40.25")
    reached = {"yes": False}
    def _dump(p):
        reached["yes"] = True
        return {"pages": []}                     # too few chars -> False, fine
    monkeypatch.setattr(C, "_born_digital_char_dump", _dump)
    C._write_born_digital_lines(pdf)
    assert reached["yes"], "an allowed producer must reach the extractor"
