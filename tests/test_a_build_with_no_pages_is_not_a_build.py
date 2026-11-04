"""A compile that produced no pages must say why, and must not be measured.

Measured on nopi, 2026-11-04, for 17 documents holding 4,106 rows. The
document's own report compiled to a 95,879-byte file with no trailer, and what
the fleet saw was:

    STOPPED at step 3 (measure): RegionInkRefused: ghostscript wrote no raster
    for page 1 of report.pdf at 300 dpi: Catalog dictionary not located in
    file, unable to proceed

A ghostscript message about a PDF. The cause was four layers up and one line
long -- `xdvipdfmx:fatal: Cannot proceed without .vf or "physical" font`,
because `bbm10.tfm` was installed and the Metafont source `bbm10.mf` was not.
Two things hid it:

1. `compile_fixpoint` runs xelatex with `capture_output=True` and DISCARDS the
   stderr that carries that line. xelatex pipes to xdvipdfmx, so xelatex
   itself dies of SIGPIPE with nothing to say; the one process that knows is
   the one whose output is thrown away.
2. inkreport step 2 verifies the build STAMP says `phase=measure` and never
   looks at its page count, so a stamp reading `phase=measure, None pages`
   passes and a truncated PDF goes to the rasterizer.

So: keep the stderr when a build produced no pages, and refuse such a build
where it is stamped rather than four layers later. The log must be read BEFORE
the refusal, because `_bail` restores the reading build and overwrites
report.log -- which is why the failing log was never there to read.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pdfdrill import report_tex as rt                            # noqa: E402
from pdfdrill import commands as cmds                            # noqa: E402

FATAL = 'xdvipdfmx:fatal: Cannot proceed without .vf or "physical" font for PDF output...'


def _fake_run(stderr_text, log_text):
    """Stand in for `subprocess.run`, writing the log xelatex would write."""
    def run(cmd, **kw):
        out = None
        for i, a in enumerate(cmd):
            if a == "-output-directory":
                out = Path(cmd[i + 1])
        src = Path(cmd[-1])
        if out is not None and log_text is not None:
            (out / (src.stem + ".log")).write_text(log_text, encoding="utf-8")
        return subprocess.CompletedProcess(cmd, 0, b"", stderr_text.encode())
    return run


@pytest.fixture
def tex(tmp_path):
    p = tmp_path / "report.tex"
    p.write_text("\\documentclass{article}\\begin{document}x\\end{document}\n",
                 encoding="utf-8")
    return p


def test_a_compile_that_produced_no_pages_keeps_the_stderr_that_says_why(
        tex, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/xelatex")
    monkeypatch.setattr(subprocess, "run",
                        _fake_run(FATAL + "\n\nNo output PDF file written.\n",
                                  "! Font bbm10 not loadable\n"))
    pages, nerr, demoted = rt.compile_fixpoint(tex)
    assert pages == 0
    err = tex.with_name("report.compile.err")
    assert err.is_file(), "no report.compile.err beside a 0-page build"
    body = err.read_text(encoding="utf-8")
    assert "Cannot proceed without" in body
    assert 'physical' in body


def test_a_compile_that_produced_pages_leaves_no_stale_error_file(
        tex, monkeypatch):
    stale = tex.with_name("report.compile.err")
    stale.write_text("from an older failure\n", encoding="utf-8")
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/xelatex")
    monkeypatch.setattr(subprocess, "run",
                        _fake_run("", "Output written on report.pdf (7 pages, "
                                      "123 bytes).\n"))
    pages, _, _ = rt.compile_fixpoint(tex)
    assert pages == 7
    assert not stale.exists(), ("a build that produced pages left the previous "
                               "build's error file, which reads as this one's")


def test_an_empty_stderr_writes_no_error_file(tex, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/xelatex")
    monkeypatch.setattr(subprocess, "run", _fake_run("", None))
    pages, _, _ = rt.compile_fixpoint(tex)
    assert pages == 0
    assert not tex.with_name("report.compile.err").exists()


# ---------------------------------------------------------------- step 2

def _doc(tmp_path, pages, log=None, compile_err=None):
    d = tmp_path / "doc"
    d.mkdir(exist_ok=True)
    (d / "report.build.json").write_text(
        json.dumps({"phase": "measure", "pages": pages,
                    "sha256": "a" * 64}), encoding="utf-8")
    if log is not None:
        (d / "report.log").write_text(log, encoding="utf-8")
    if compile_err is not None:
        (d / "report.compile.err").write_text(compile_err, encoding="utf-8")
    return d


def test_a_build_with_pages_is_not_refused(tmp_path):
    d = _doc(tmp_path, 13)
    assert cmds.no_pages_refusal(d, {"phase": "measure", "pages": 13}) is None


@pytest.mark.parametrize("pages", [None, 0, "0"])
def test_a_build_with_no_pages_is_refused(tmp_path, pages):
    d = _doc(tmp_path, pages, log="! File ended while scanning use of "
                                  "\\@newl@bel.\n! a later one\n")
    lines = cmds.no_pages_refusal(d, {"phase": "measure", "pages": pages})
    assert lines, "a build stamped %r pages was accepted" % (pages,)
    joined = "\n".join(lines)
    assert "step 2" in joined
    assert "\\@newl@bel" in joined, "the refusal does not quote the LaTeX error"
    assert "a later one" not in joined, "quote the FIRST error, not every one"


def test_the_refusal_quotes_the_line_that_names_the_cause(tmp_path):
    d = _doc(tmp_path, None, log="! something\n", compile_err=FATAL + "\n")
    joined = "\n".join(cmds.no_pages_refusal(
        d, {"phase": "measure", "pages": None}))
    assert "Cannot proceed without" in joined
    assert "report.compile.err" in joined


def test_a_refusal_without_a_log_still_says_what_happened(tmp_path):
    d = _doc(tmp_path, 0)
    joined = "\n".join(cmds.no_pages_refusal(
        d, {"phase": "measure", "pages": 0}))
    assert "0 pages" in joined or "no pages" in joined


def test_step_2_of_inkreport_calls_the_guard(tmp_path):
    """The call site, not only the helper -- rule 46's lesson in miniature.

    A helper nothing calls is the exact shape this branch keeps finding: the
    thing that verifies not verifying the thing that runs.
    """
    src = (ROOT / "src" / "pdfdrill" / "commands.py").read_text(
        encoding="utf-8")
    i = src.index('"2 build/measure  phase=%s, %s pages, sha %s"')
    before = src[max(0, i - 2500):i]
    assert "no_pages_refusal(" in before, (
        "step 2 prints the build line without having asked whether the build "
        "produced any pages")
