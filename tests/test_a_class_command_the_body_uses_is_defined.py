r"""`\dvtx` is imsart's spaced colon, and we keep our own class.

T-0156. arxiv.0912.2444 writes `$H_i\dvtx [q^-]\rightarrow\mathbb{R}$` in its
body maths. `\dvtx` is defined in the author's CLASS — arximspdf.cls:1110 —
not in the author's preamble, so neither class B (the author's packages) nor
variant C (the author's macro definitions) could reach it: both read the
preamble. It arrived undefined.

THE DEFINITION IS THE CLASS'S OWN, copied including the `\mathchoice`, which
is what gives the script sizes a wider gap than the text ones:

    \def\dvtx{%
      \mathchoice{\nobreak\,\colon\relax}%
                 {\nobreak\,\colon\relax}%
                 {\nobreak\,\colon\;\relax}%
                 {\nobreak\,\colon\;\relax}}

MEASURED, the audit's two commands on fresh copies, both halves clean:

    arxiv.0912.2444   95 -> 83      the other seven unchanged
    total            278 -> 266     eight PDFs, nothing rises

16 `\dvtx` errors went and 4 were exposed behind them (the non-`\dvtx` count
rose 79 -> 83), so the net is -12 and not the -16 the token census predicted.
The 13 `\dvtx` in the projected .tex now typeset instead of erroring.

AND IT IS NOT A GENERAL RULE, which was measured before it was written. Taking
the bundled class's definition for every command the body uses and the
preamble does not define reaches, on this same document:

    \begin   129   \def\begin#1{\@ifundefined{pseudo@#1}{\org@begin{#1}}…}
    \end     129
    \section   9   plus \author, \address, \thankstext

A class REDEFINES the kernel, and `\def\begin` there depends on `\org@begin`
which the class sets up elsewhere. Lifting that wholesale would put fragments
of someone else's class where LaTeX's own commands belong — the same family as
the A and B refutations. So this is a named entry with a cited line, and it
grows one measured entry at a time.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

L = pytest.importorskip("docops.projectors.latex")


def _dvtx_line():
    for line in L._DEFAULT_PREAMBLE.splitlines():
        if "dvtx" in line:
            return line
    return ""


def test_the_preamble_defines_it():
    assert "\\dvtx" in L._DEFAULT_PREAMBLE


def test_it_is_providecommand_so_the_real_class_still_wins():
    r"""`\providecommand` is a no-op where the author's class is loaded, so
    this cannot override an author who has the real one. A `\newcommand`
    would error "already defined" there, and a `\renewcommand` would error
    where it is absent."""
    line = _dvtx_line()
    assert line.lstrip().startswith("\\providecommand{\\dvtx}")
    assert "\\newcommand{\\dvtx}" not in L._DEFAULT_PREAMBLE
    assert "\\renewcommand{\\dvtx}" not in L._DEFAULT_PREAMBLE


def test_the_body_is_the_class_s_own_mathchoice():
    r"""Copied from arximspdf.cls:1110, not flattened to a bare `\colon`: the
    four branches are display, text, script and scriptscript, and the last two
    carry the extra `\;`."""
    line = _dvtx_line()
    assert "\\mathchoice" in line
    assert line.count("\\colon") == 4
    assert line.count(r"\;") == 2
    assert line.count("\\nobreak\\,") == 4


def test_it_is_unconditional_like_the_other_symbol_entries():
    r"""The reason this preamble gives for `stmaryrd`, `extarrows` and
    `listings`: "a symbol the projection can write and the preamble cannot
    resolve is not a rendering problem, it is a compile failure". The entry
    sits in the one preamble string, not behind a flag."""
    assert "dvtx" in L._DEFAULT_PREAMBLE
    assert L._DEFAULT_PREAMBLE.count("\\providecommand{\\dvtx}") == 1


def test_the_preamble_still_has_one_documentclass_and_no_inputenc():
    """A guard on the whole string, since this edit is inside it: xelatex is
    the engine, and `_DEFAULT_PREAMBLE`'s own comment says inputenc "actively
    CLASHES" with it."""
    assert L._DEFAULT_PREAMBLE.count("\\documentclass") == 1
    assert "inputenc" not in L._DEFAULT_PREAMBLE
    assert "fontenc" not in L._DEFAULT_PREAMBLE


def test_every_brace_in_the_preamble_balances():
    r"""The entry is a nested `\mathchoice` of four groups written as a Python
    string concatenation across three source lines, which is exactly where a
    brace goes missing."""
    depth = 0
    for i, ch in enumerate(L._DEFAULT_PREAMBLE):
        if ch in "{}" and (i == 0 or L._DEFAULT_PREAMBLE[i - 1] != "\\"):
            depth += 1 if ch == "{" else -1
        assert depth >= 0, "a closing brace with nothing open"
    assert depth == 0, "unbalanced preamble"


def test_it_compiles():
    r"""The only test here that can catch a wrong `\mathchoice` arity: xelatex
    on the preamble plus one use of `\dvtx` in maths."""
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("xelatex"):
        pytest.skip("NOT RUN: xelatex is not on PATH")
    body = (L._DEFAULT_PREAMBLE + "\\begin{document}\n"
            "$H_i\\dvtx [q^-]\\rightarrow\\mathbb{R}$\n"
            "\\end{document}\n")
    with tempfile.TemporaryDirectory(
            dir=str(Path(__file__).resolve().parent.parent
                    / "work" / "run-files")) as d:
        tex = Path(d) / "dvtx.tex"
        tex.write_text(body, encoding="utf-8")
        subprocess.run(["xelatex", "-interaction=nonstopmode", tex.name],
                       cwd=d, capture_output=True, timeout=300)
        log = (Path(d) / "dvtx.log")
        assert (Path(d) / "dvtx.pdf").exists(), "no PDF"
        text = log.read_text(encoding="utf-8", errors="replace")
        errs = [ln for ln in text.splitlines() if ln.startswith("!")]
        assert not errs, errs[:3]
