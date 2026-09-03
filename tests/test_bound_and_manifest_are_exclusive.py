"""593 — a build that writes report.tables.json cannot take a page bound.

588 measured it on johnston: `pagesel` discards pages at SHIPOUT, so the
document is typeset in full and the manifest is written from the complete row
list while the PDF ships only what fits. At --pages 10 the manifest named 52
identifiers and the PDF shipped 24 — exactly the 24 in "run holds 24 data
rows, the manifest expects 68". Unbounded, both were 52.

Truncating the manifest to the shipped rows would make them agree and would be
wrong: a measurement of ten pages reported as a measurement of the document.
So the bound is refused. breport keeps --pages because B writes no manifest.
"""
import inspect
import pathlib

from pdfdrill import commands as C
from pdfdrill import report_tex as rt


def test_reporttex_refuses_a_bound(tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    out = C.cmd_reporttex(pdf, pages=10)
    assert "refuses --pages 10" in out
    assert rt.TABLES_MANIFEST in out
    assert "breport" in out, "the refusal must name the surface that can be bounded"


def test_inkreport_refuses_a_bound_rather_than_dropping_it(tmp_path):
    """578's defect was a flag accepted and silently ignored."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    out = C.cmd_inkreport(pdf, pages=10)
    assert "refuses --pages 10" in out and "breport" in out


def test_a_zero_or_absent_bound_is_not_refused(tmp_path):
    """0/None mean 'every page'. Only a positive bound is a bound."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    for v in (None, 0, -1):
        try:
            out = C.cmd_reporttex(pdf, pages=v)
        except Exception as exc:          # the stub PDF cannot rasterise, and
            out = str(exc)                # that is not what this test is about
        assert "refuses --pages" not in out


def test_the_build_is_never_silently_bounded():
    """`pages=None` used to become PAGES_DEFAULT (10) at the build_report
    call, so every reporttex build was bounded whether or not anyone asked —
    including the measure build 585 believed it had made unbounded."""
    src = inspect.getsource(C.cmd_reporttex)
    assert "rt.PAGES_DEFAULT if pages is None" not in src
    assert "pages=0," in src, "build_report must be called unbounded"


def test_the_measure_bound_is_zero_not_none():
    """None meant PAGES_DEFAULT. 0 means every page (pagesel_line)."""
    assert C.MEASURE_PAGES_BOUND == 0
    assert rt.pagesel_line(C.MEASURE_PAGES_BOUND) == "", "0 must select all pages"


def test_no_manifest_writing_build_inside_inkreport_takes_a_bound():
    import re
    src = inspect.getsource(C.cmd_inkreport)
    for call in re.findall(r"cmd_reporttex\((?:[^()]|\([^()]*\))*\)", src, re.S):
        assert "pages=pages" not in call, "a bounded manifest build: %s" % call


def test_breport_keeps_its_bound():
    """B writes no manifest, so it can be bounded — it is a reading surface."""
    assert "pages" in inspect.signature(C.cmd_breport).parameters
    src = pathlib.Path(rt.__file__).read_text(encoding="utf-8")
    import ast
    tree = ast.parse(src)
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name in ("b_tex", "b_rows"):
            body = ast.get_source_segment(src, n) or ""
            assert "TABLES_MANIFEST" not in body, \
                "%s writes a manifest — it can no longer take a bound" % n.name
