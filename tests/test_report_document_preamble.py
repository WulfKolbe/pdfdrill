r"""
836 — the document's own preamble travels with its evidence report, and a
value that cannot be set in a longtable cell is compiled as its own document.

The report compiled every document with one shared preamble. arXiv 1102.1889
is 83 display equations of which 64 are `\xymatrix`, and its evidence report
came out with 1,029 errors for want of the `\input xy` its own preamble
carries. Injecting that preamble is half the fix and, alone, it is WORSE:
with xy actually loaded the diagrams stop being undefined and start EXECUTING
inside a longtable cell, where xy seizes the alignment machinery, the first
such row ends the table ("\begin{longtable} on input line 272 ended by
\end{aligned}"), and every row after it is lost — 0 pages, down from 12.

Measured on arXiv 1102.1889, evidence-equation:

    shared preamble only          12 pages   1,029 errors
    + document preamble            0 pages     112 errors   <- worse
    + xy rows compiled separately  25 pages       0 errors
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import report_tex as rt                          # noqa: E402


def test_every_injected_package_is_guarded():
    r"""An unguarded `\usepackage` for a .sty this machine lacks aborts the
    compile and produces NO pdf — worse than the rows it would have rendered."""
    out = rt.document_preamble({"latex_preamble": {"standalone": "\n".join([
        r"\documentclass{article}",
        r"\usepackage{xypic}",
        r"\usepackage[all]{xy}",
        r"\input xy",
    ])}})
    assert r"\input xy" in out
    for m in re.finditer(r"\\usepackage", out):
        head = out[:m.start()].rsplit("\n", 1)[-1]
        assert head.startswith(r"\IfFileExists{"), out


def test_the_page_layout_packages_are_never_injected():
    """The report owns its own geometry, fonts and hyperref; a document's
    `\\usepackage[margin=1in]{geometry}` would re-lay-out the report itself."""
    out = rt.document_preamble({"latex_preamble": {"standalone": "\n".join([
        r"\usepackage[margin=1in]{geometry}",
        r"\usepackage{hyperref}",
        r"\usepackage{xypic}",
    ])}})
    assert "geometry" not in out and "hyperref" not in out
    assert "xypic" in out


def test_no_preamble_injects_nothing():
    assert rt.document_preamble({}) == ""
    assert rt.document_preamble({"latex_preamble": {"standalone": "  "}}) == ""


def test_xy_is_refused_a_cell():
    r"""`display_safe` answers "is this legal display maths". `\xymatrix` is
    legal maths and still illegal HERE, because it takes over the alignment
    machinery of the longtable around it."""
    assert rt.needs_own_document(r"\xymatrix@=40pt{A \ar[r] & B}")
    assert rt.needs_own_document(r"\xygraph{a}")
    assert not rt.needs_own_document(r"\frac{a}{b} = \sum_{i} x_i")
    assert not rt.needs_own_document("")
    assert not rt.needs_own_document(None)


def test_a_word_containing_xy_is_not_an_xy_diagram():
    """The gate is a control sequence, not a substring: `\\xyzzy` and a
    variable named `xy` are ordinary maths."""
    assert not rt.needs_own_document(r"\xyzzy{a}")
    assert not rt.needs_own_document(r"xy + z")


def test_a_failed_separate_compile_refuses_the_row_rather_than_the_report():
    """THE RULE THE 0-PAGE REPORT BOUGHT. 50 of 64 xy rows compiled standalone
    and 14 did not; letting those 14 fall through to the cell cost every row
    after the first of them. One unrenderable row must cost one row."""
    from pdfdrill.reports import tex as T

    class _R:
        latex = r"\xymatrix{A \ar[r] & B}"
        identifier = "x"
        trailing_punct = ""
        listing = ""

    calls = []

    def _fails(*a, **kw):
        calls.append(kw)
        return ""                       # the separate compile did not produce

    old, rt.standalone_math = rt.standalone_math, _fails
    try:
        cell = T._rendered(_R(), (0, 0, 0, 0, 100, 0), ".", "author preamble")
    finally:
        rt.standalone_math = old
    assert cell == r"\emph{(not rendered)}", cell
    assert calls and calls[0]["author_preamble"] == "author preamble", (
        "the author's preamble must reach the separate compile — it is what "
        "carries the `\\input xy` the diagram needs")
