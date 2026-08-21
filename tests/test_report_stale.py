"""A report.pdf older than its report.tex is stale, and must be said so.

064 regenerated 0902.0431's report.tex and left the pdf an hour older. Both
this session and the consumer's read the superseded pdf for half a day: it
existed, its page count was plausible, and its mtime was recent relative to
the corpus. Every check anyone ran compared it against the CLOCK. None
compared it against its own source.
"""
import os

from pdfdrill.report_tex import stale_pdf_for


def _pair(tmp_path, tex_mtime, pdf_mtime):
    tex = tmp_path / "report.tex"
    pdf = tmp_path / "report.pdf"
    tex.write_text("x")
    pdf.write_text("y")
    os.utime(tex, (tex_mtime, tex_mtime))
    os.utime(pdf, (pdf_mtime, pdf_mtime))
    return tex, pdf


def test_pdf_older_than_tex_is_stale(tmp_path):
    tex, pdf = _pair(tmp_path, 2000, 1000)
    assert stale_pdf_for(tex) == pdf


def test_pdf_newer_than_tex_is_current(tmp_path):
    tex, _ = _pair(tmp_path, 1000, 2000)
    assert stale_pdf_for(tex) is None


def test_equal_mtimes_are_not_stale(tmp_path):
    """A compile that finishes inside the same filesystem timestamp tick must
    not be reported as stale — the check would then fire on every run."""
    tex, _ = _pair(tmp_path, 1500, 1500)
    assert stale_pdf_for(tex) is None


def test_absent_pdf_is_not_stale(tmp_path):
    """Absence is not staleness. A first run has no pdf and has nothing to
    warn about; conflating the two would make the message meaningless."""
    tex = tmp_path / "report.tex"
    tex.write_text("x")
    assert stale_pdf_for(tex) is None


def test_recent_pdf_can_still_be_stale(tmp_path):
    """The whole point: freshness against the clock says nothing. Both files
    are seconds old; the pdf is still the wrong build."""
    import time
    now = time.time()
    tex, pdf = _pair(tmp_path, now, now - 2)
    assert stale_pdf_for(tex) == pdf
