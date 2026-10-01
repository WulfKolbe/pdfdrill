r"""
842 — a `.pdf` is not a PDF just because of its extension.

A failed download keeps the name it was saved under. Every tool downstream then
reports the CONSEQUENCE instead of the cause: `pdfinfo` says "Couldn't open
file", the abstract search says "no abstract block detected", and the document
is filed as a paper that merely happens to have no abstract. That is how 18
HTML error pages came to sit in the library as `sigma26-74 … sigma26-91`,
indistinguishable in the sidecar from a scanned book — and they were one
command away from being sent to MathPix, which would have paid to OCR a
"404 - PAGE NOT FOUND" page.

So the header is checked where every command resolves its input, before any
probe runs, and the message names what the file ACTUALLY is: "not a PDF" sends
a reader looking for a parser bug, "an HTML page (410 Gone)" sends them to
re-download.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.pdf_reading import pdf_header_problem, NotAPDF   # noqa: E402


def test_a_real_pdf_passes(tmp_path):
    f = tmp_path / "ok.pdf"
    f.write_bytes(b"%PDF-1.7\n...\n%%EOF\n")
    assert pdf_header_problem(f) is None


def test_junk_before_the_header_is_tolerated(tmp_path):
    """poppler reads it, so we must not reject it. One real book in this
    library begins `\\n\\n%PDF-1.4` and opens perfectly — rejecting it would
    delete a 9.5 MB document over two bytes."""
    f = tmp_path / "ok.pdf"
    f.write_bytes(b"\n\n%PDF-1.4\r%\xe2\xe3\xcf\xd3\n")
    assert pdf_header_problem(f) is None


def test_an_html_error_page_is_named_as_one(tmp_path):
    f = tmp_path / "x.pdf"
    f.write_bytes(b"<!DOCTYPE html>\n<html><head><title>404 - PAGE NOT FOUND"
                  b"</title></head><body>gone</body></html>" + b" " * 2000)
    why = pdf_header_problem(f)
    assert why and "HTML page" in why
    assert "404 - PAGE NOT FOUND" in why, why


def test_a_tiny_failure_quotes_what_it_actually_says(tmp_path):
    """The 9-byte case: the file IS the error message."""
    f = tmp_path / "x.pdf"
    f.write_bytes(b"not found")
    why = pdf_header_problem(f)
    assert why and "9 bytes" in why and "not found" in why


def test_an_empty_stub_points_at_its_half_finished_download(tmp_path):
    """0 bytes beside a `.pdf.part` is an interrupted download, and saying so
    is the difference between 're-download' and 'this book has no text'."""
    (tmp_path / "book.pdf").write_bytes(b"")
    (tmp_path / "book.AbCd1234.pdf.part").write_bytes(b"%PDF-1.6" + b"x" * 100)
    why = pdf_header_problem(tmp_path / "book.pdf")
    assert why and "EMPTY" in why and "interrupted download" in why
    assert "book.AbCd1234.pdf.part" in why


def test_a_missing_file_does_not_raise(tmp_path):
    why = pdf_header_problem(tmp_path / "nope.pdf")
    assert why and "cannot be read" in why


def test_the_resolver_refuses_before_any_probe(tmp_path, monkeypatch):
    """The whole point: it fails at resolution, so nothing downstream ever
    reports a consequence. `_probe_on_acquire` is where every command's input
    funnels through."""
    from pdfdrill import cli
    f = tmp_path / "x.pdf"
    f.write_bytes(b"<html><head><title>410 Gone</title></head></html>" + b" " * 200)

    def _boom(*a, **kw):                                       # pragma: no cover
        raise AssertionError("a probe ran on a file that is not a PDF")

    monkeypatch.setattr(cli, "_probe_on_acquire",
                        cli._probe_on_acquire)                 # keep the real one
    import pdfdrill.probes as probes
    monkeypatch.setattr(probes, "ensure", _boom)
    try:
        cli._probe_on_acquire(f)
    except NotAPDF as e:
        assert "410 Gone" in str(e)
    else:                                                      # pragma: no cover
        raise AssertionError("expected NotAPDF")


def test_a_non_pdf_input_is_left_alone(tmp_path):
    """`markdown`/`latexbook` resolve .md and .tex through the same place and
    are not PDFs by design."""
    from pdfdrill import cli
    f = tmp_path / "notes.md"
    f.write_text("# hello", encoding="utf-8")
    assert cli._probe_on_acquire(f) == f
