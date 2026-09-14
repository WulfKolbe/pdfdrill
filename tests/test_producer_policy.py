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


def _gzipped_tar(*names: str) -> bytes:
    import io, tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for n in names:
            data = b"\\documentclass{article}\n"
            info = tarfile.TarInfo(n); info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def test_download_arxiv_source_keeps_a_real_archive(tmp_path, monkeypatch):
    """A gzipped TAR — the multi-file submission — lands as `.tgz`."""
    from pdfdrill import sources
    monkeypatch.setattr(sources, "download",
                        lambda url, dest: (Path(dest).write_bytes(
                            _gzipped_tar("main.tex", "sec1.tex")), Path(dest))[1])
    out = sources.download_arxiv_source("2101.00002", tmp_path)
    assert out.exists() and out.name == "2101.00002.tgz"


def test_download_arxiv_source_names_a_plain_gzip_gz(tmp_path, monkeypatch):
    r"""689 — a SINGLE-FILE arXiv submission is served as gzip(paper.tex), NOT
    gzip(tar(...)). It used to be written as `<id>.tgz`, which is a lie: 0902.0431
    sat on disk as `0902.0431.tgz` while `file` said `gzip compressed data, was
    "SpEcxp.tex"` and `tarfile.is_tarfile` said no. Nothing broke — every reader
    sniffs content — but the seven places that match on the EXTENSION would not
    have found the file under its true name, so the name has to be true."""
    import gzip
    from pdfdrill import sources
    payload = gzip.compress(b"\\documentclass[a4]{article}\n\\begin{document}x\\end{document}\n")
    monkeypatch.setattr(sources, "download",
                        lambda url, dest: (Path(dest).write_bytes(payload), Path(dest))[1])
    out = sources.download_arxiv_source("0902.0431", tmp_path)
    assert out.name == "0902.0431.gz", f"named {out.name}, not for what it is"
    assert not (tmp_path / "0902.0431.tgz").exists()
    assert not (tmp_path / "0902.0431.download").exists()   # no temp left behind
    # and the loader reads it, which is why the old wrong name never showed up
    from pdfdrill import latex_source
    text, _main = latex_source.read_source(str(out))
    assert "documentclass" in text


def test_download_arxiv_source_names_a_bare_tex(tmp_path, monkeypatch):
    """The third payload shape: one uncompressed `.tex`."""
    from pdfdrill import sources
    monkeypatch.setattr(sources, "download",
                        lambda url, dest: (Path(dest).write_bytes(
                            b"\\documentclass{article}\n"), Path(dest))[1])
    out = sources.download_arxiv_source("2101.00003", tmp_path)
    assert out.name == "2101.00003.tex"


def test_eprint_suffix_for_each_payload_shape(tmp_path):
    """The sniffer alone, on the three shapes plus a mislabelled cache."""
    import gzip
    from pdfdrill import sources
    tgz = tmp_path / "a"; tgz.write_bytes(_gzipped_tar("m.tex"))
    gz = tmp_path / "b"; gz.write_bytes(gzip.compress(b"\\documentclass{article}"))
    tex = tmp_path / "c"; tex.write_bytes(b"\\documentclass{article}")
    assert sources.eprint_suffix_for(tgz.read_bytes()[:4096], tgz) == ".tgz"
    assert sources.eprint_suffix_for(gz.read_bytes()[:4096], gz) == ".gz"
    assert sources.eprint_suffix_for(tex.read_bytes()[:4096], tex) == ".tex"
    # gzip with no path to test for tar-ness: `.gz` is the honest answer, and
    # every reader sniffs content anyway.
    assert sources.eprint_suffix_for(tgz.read_bytes()[:4096], None) == ".gz"


def test_download_arxiv_source_reuses_a_cache_under_any_suffix(tmp_path, monkeypatch):
    """A `.gz` already on disk is not re-downloaded — and neither is a payload
    left under the old wrong `.tgz` name by a pre-689 build. Existing files are
    never renamed behind the user's back."""
    import gzip
    from pdfdrill import sources

    def refuse(url, dest):
        raise AssertionError("must not download: a cached e-print exists")
    monkeypatch.setattr(sources, "download", refuse)

    (tmp_path / "0902.0431.gz").write_bytes(gzip.compress(b"\\documentclass{a}"))
    assert sources.download_arxiv_source("0902.0431", tmp_path).name == "0902.0431.gz"

    # the mislabelled legacy file keeps working, under its legacy name
    (tmp_path / "1111.2222.tgz").write_bytes(gzip.compress(b"\\documentclass{a}"))
    assert sources.download_arxiv_source("1111.2222", tmp_path).name == "1111.2222.tgz"


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


def test_the_extension_lookups_accept_a_plain_gz(tmp_path):
    r"""689 — the fix to `download_arxiv_source` is only half the defect. Seven
    places locate the e-print by matching its EXTENSION, and every one of them
    listed `.tgz`/`.tar.gz` only; a correctly-named `.gz` would have been
    invisible to all of them, which is how a naming bug becomes a silent
    "no author source" and a document verified against nothing.

    This test pins the one that matters most — `refine.author_eprint`, the
    identity evidence a census repair is accepted on.
    """
    import gzip
    from pdfdrill import refine
    pdf = tmp_path / "0902.0431.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    body = b"\\documentclass[a4]{article}\n\\begin{document}\n$E=mc^2$\n\\end{document}\n"
    # gzip carrying the original name, exactly as arXiv serves a single file
    import io
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", filename="SpEcxp.tex") as g:
        g.write(body)
    (tmp_path / "0902.0431.gz").write_bytes(buf.getvalue())
    text, main = refine.author_eprint(pdf)
    assert "E=mc^2" in text, "author_eprint did not find the .gz e-print"
    assert main.endswith(".tex")
