"""822 — the LaTeX a reader compiles by hand. Four defects found by doing that
on arXiv 2605.23109: 215 xelatex errors, now 0.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from docops.projectors.latex import _cell_tex                     # noqa: E402
from docops.projectors.latex_pipeline import (                    # noqa: E402
    escape_prose_specials, sanitize_math)


# ── 1. prose escapes text-mode specials, math is left alone ─────────────────

def test_a_code_identifier_in_prose_is_escaped():
    r"""`_` was on the exempt list ("carries the model's inline LaTeX"), but a
    subscript outside math is already an error. What prose actually holds is
    code identifiers, and 2605.23109 had 46 `Missing $ inserted` from them."""
    assert escape_prose_specials("the read_inc theorem") == r"the read\_inc theorem"


def test_math_is_not_escaped():
    m = r"\(\mathbb{I}_{R Y W}^{*}\)"
    assert escape_prose_specials(m) == m


@pytest.mark.parametrize("raw,want", [
    ("100% done", r"100\% done"),
    ("R&D", r"R\&D"),
    ("C#", r"C\#"),
])
def test_the_previously_handled_specials_still_are(raw, want):
    assert escape_prose_specials(raw) == want


def test_caret_and_tilde_get_their_TEXT_commands():
    r"""`\^` is the circumflex ACCENT and wants an argument, so `x\^2` sets a
    circumflex over the 2 or fails."""
    assert escape_prose_specials("x^2") == r"x\textasciicircum{}2"
    assert escape_prose_specials("a~b") == r"a\textasciitilde{}b"


def test_it_is_idempotent():
    once = escape_prose_specials("read_inc and 50%")
    assert escape_prose_specials(once) == once


def test_a_cell_uses_the_same_rule_not_a_second_one():
    r"""819 escaped cells with `_escape_text`, which escapes `_` wherever it
    stands — and 24.5% of corpus cells hold mathematics, so
    `\(\mathbb{I}_{R Y W}^{*}\)` came out with `\_`: a literal underscore where
    a subscript belonged, wrong silently rather than broken loudly."""
    got = _cell_tex(r"\(\mathbb{I}_{R Y W}^{*}\) and user_arg")
    assert r"\(\mathbb{I}_{R Y W}^{*}\)" in got
    assert r"user\_arg" in got


# ── 2. a formula must not escape its own closing delimiter ──────────────────

def test_a_dangling_backslash_is_dropped():
    r"""A Formula body of `52-\` is wrapped `${body}$` and comes out `$52-\$`:
    the closing `$` is escaped, the span never closes, and the damage surfaces
    hundreds of lines later."""
    assert not sanitize_math("52-\\").endswith("\\")


def test_a_real_line_break_is_kept():
    r"""`\\` is a line break and legal; only an ODD number of trailing
    backslashes is a truncation."""
    assert sanitize_math(r"a \\").rstrip().endswith("\\\\")


def test_wrapping_a_sanitised_body_keeps_the_dollars_balanced():
    body = sanitize_math("52-\\")
    wrapped = f"${body}$"
    assert len(re.findall(r"(?<!\\)\$", wrapped)) % 2 == 0


# ── 3. a cell may not emit an environment it cannot close ───────────────────

def test_an_unterminated_environment_in_a_cell_is_dropped():
    r"""Inside a tabular an unterminated `\begin{lstlisting}` swallows every
    following `&` and `\\`, so the table stops being a table: measured on
    2605.23109, one such cell produced 51 `Missing }` and 49 `Missing \cr`."""
    got = _cell_tex(r"\begin{lstlisting}[mathescape=true] Put-req-payload")
    assert "lstlisting" not in got
    assert "Put-req-payload" in got


def test_a_balanced_environment_still_unwraps_to_its_words():
    assert _cell_tex(r"\begin{lstlisting}code\end{lstlisting}") == "code"


def test_the_option_and_column_spec_go_with_the_wrapper():
    r"""Matching only `\begin{env}` left them behind: a cell holding
    `\begin{tabular}[t]{l}…\end{tabular}` unwrapped to `[t]{l} …`."""
    got = _cell_tex(r"\begin{tabular}[t]{l}inner\end{tabular}")
    assert got == "inner"


# ── 4. the crop path resolves from either directory ─────────────────────────

def test_the_preamble_sets_graphicspath():
    """The .tex is written to `<doc>/latex/` and names `report-crops/…`, which
    is relative to `<doc>/`. pdfdrill's own compile works only because it sets
    cwd there; a reader opening the file in its own folder gets a missing
    graphic."""
    src = (Path(__file__).resolve().parents[1]
           / "src" / "docops" / "projectors" / "latex.py").read_text()
    assert r"\\graphicspath{{./}{../}}" in src or \
           r"\graphicspath{{./}{../}}" in src


# ── the real documents: zero errors, not "a PDF exists" ─────────────────────

_LIB = Path.home() / "pdfdrill-library"


import shutil
import subprocess
import tempfile

_PAPERS = ["arxiv.2609.12039", "arxiv.2607.22944",
           "arxiv.2607.16387", "arxiv.2605.23109"]


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="no xelatex")
@pytest.mark.parametrize("doc", _PAPERS)
def test_the_projected_latex_compiles_with_ZERO_errors(doc):
    r"""The invariant, and the only honest one.

    A grep for unescaped specials is a proxy, and every proxy I wrote today was
    wrong in the same way: a `&` inside a tabular is legitimate, a `_` inside
    `\Expr{…}` is mathematics, and TeX reports a runaway wherever it finally
    collides with something rather than where it began. The compiler is the
    authority.

    "A PDF was produced" is not the property either: `nonstopmode` produced one
    for 2605.23109 while recovering from 215 errors, and pdfdrill reported that
    as `compiled: ✓`.
    """
    tex = _LIB / doc / "latex" / f"{doc}.tex"
    if not tex.is_file():
        pytest.skip(f"{doc} not projected")
    with tempfile.TemporaryDirectory() as out:
        subprocess.run(
            # cwd is the DOC folder, which is what `\graphicspath{{./}{../}}`
            # makes work either way — so the file is `latex/<name>`, not
            # `<name>`. Passing the bare name found nothing and the test
            # silently skipped instead of running.
            ["xelatex", "-interaction=nonstopmode", "-output-directory", out,
             f"latex/{tex.name}"],
            cwd=str(tex.parent.parent), capture_output=True, timeout=900)
        log = Path(out) / f"{doc}.log"
        if not log.is_file():
            pytest.skip("xelatex produced no log")
        errs = re.findall(r"^! .*$", log.read_text(encoding="utf-8",
                                                   errors="replace"), re.M)
    assert not errs, f"{len(errs)} xelatex error(s):\n" + "\n".join(errs[:8])
