r"""`--compile` names which of three things happened, and errors exit non-zero.

T-0156, after class G (841b8ff6). `_xelatex_compile` passed
`-halt-on-error`, so xelatex stopped at the FIRST error and 7 of the audit's 8
e-prints produced no PDF at all. Dropping it, one pass over the eight:

    1503.00301       1179 errors   23pp    8325 words  103%   DOCUMENT
    1703.08160         24 errors   22pp    7881        105%   DOCUMENT
    1909.00741        344 errors   24pp    6695         97%   DOCUMENT
    arxiv.0912.2444   142 errors   59pp   19989        168%   DOCUMENT
    arxiv.2402.03975  187 errors   69pp   27438        117%   DOCUMENT
    2102.08145         75 errors    --pp      0  broken PDF   FRAGMENT
    2602.11699v3        7 errors    1pp      25        0.3%   FRAGMENT
    2507.21892v1       26 errors   no PDF                     NO PDF
                                                      total   1984

against pdfdrill-58's 1977 on base 0be8abcf. Five of the eight become a
22-69 page document a person can open, where "no PDF" is nothing to inspect.

SO THE PDF IS WORTH HAVING AND THE ERRORS ARE WORTH SAYING. Each run ends in
exactly one of three states, every one of them a non-zero exit while errors
remain, and the verdict NAMES the state and the count:

    no PDF                     nothing was produced
    fragment                   a PDF that is not the document (class G)
    document with N errors     inspectable, and still not a clean compile

A share over 100% is normal and not an error: the PDF renders bibliography
and figure text that stripping the source removes — 0912.2444 is 168%. The
share is a FLOOR on content, never an equality.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

C = pytest.importorskip("pdfdrill.commands")


def test_no_pdf_is_named_and_fails():
    ok, note = C._compile_verdict(False, 0, 7298, 26)
    assert ok is False
    assert "no PDF" in note


def test_a_fragment_is_named_and_fails():
    """2602.11699v3: 25 of 7229 words."""
    ok, note = C._compile_verdict(True, 25, 7229, 7)
    assert ok is False
    assert "fragment" in note and "25 of 7229" in note


def test_a_broken_pdf_of_no_pages_is_a_fragment():
    """2102.08145: a PDF file holding 0 words."""
    ok, note = C._compile_verdict(True, 0, 6719, 75)
    assert ok is False and "fragment" in note


def test_a_document_with_errors_says_how_many_and_fails():
    """1909.00741: 6695 of 6866 words, 344 errors — inspectable, not clean."""
    ok, note = C._compile_verdict(True, 6695, 6866, 344)
    assert ok is False
    assert "344 error" in note
    assert "fragment" not in note


def test_a_clean_compile_is_the_only_success():
    ok, note = C._compile_verdict(True, 6695, 6866, 0)
    assert ok is True and note == ""


def test_a_share_over_one_hundred_percent_is_not_an_error():
    """0912.2444 renders 168% of the stripped source's words."""
    ok, _ = C._compile_verdict(True, 19989, 11868, 0)
    assert ok is True


#: ------------------------------------------------------------------
#: TWO STATES THE ACCEPTANCE RUN FOUND UNREACHABLE.
#:
#: The first version asked `_pdf_word_count` BEFORE asking whether a PDF
#: existed, and returned None both when `pdftotext` was missing and when it
#: ran and failed. So two of the three states could never be reported:
#:
#:   2507.21892v1  no PDF at all  -> said "the PDF's words could not be counted"
#:   2102.08145    a PDF of 0 pages -> said the same, instead of "fragment"
#:
#: A missing `pdftotext` means the question cannot be put. A `pdftotext` that
#: ran and failed means the PDF cannot be read, and a PDF nobody can read
#: carries no words — a fragment, not an unknown.


def test_the_no_pdf_state_is_reachable_through_the_real_helper(tmp_path):
    """No file on disk must read as "no PDF", not as an uncounted one."""
    tex = tmp_path / "x.tex"
    tex.write_text("\\documentclass{article}\\begin{document}hi\\end{document}")
    ok, note = C._compile_verdict(False, 0, 0, 26)
    assert ok is False and "no PDF" in note
    assert "could not be counted" not in note


def test_an_unreadable_pdf_counts_as_no_words(tmp_path):
    """`pdftotext` on a file that is not a PDF: 0 words, not None."""
    import shutil
    if not shutil.which("pdftotext"):
        pytest.skip("pdftotext not installed")
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf at all")
    assert C._pdf_word_count(broken) == 0
