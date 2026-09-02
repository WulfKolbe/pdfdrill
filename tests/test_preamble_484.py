"""484 — the package gaps, closed once, and the two that cannot be packages."""
import re, subprocess, sys, tempfile, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest
from pdfdrill import report_tex as rt


def _preamble(extra=""):
    return (rt.PREAMBLE.replace("%(geom)s", "a3paper,landscape")
            .replace("%(bbdigits)s", rt.MATHBB_DIGITS) + extra)


def _compile(body, extra=""):
    W = pathlib.Path(tempfile.mkdtemp())
    (W / "t.tex").write_text(
        _preamble(extra) + "\\begin{document}\n" + body + "\n\\end{document}\n",
        encoding="utf-8")
    r = subprocess.run(["xelatex", "-interaction=nonstopmode", "t.tex"],
                       cwd=W, capture_output=True, text=True, timeout=300)
    log = (W / "t.log").read_text(errors="replace") if (W / "t.log").is_file() else ""
    return r.returncode, [l for l in log.splitlines() if l.startswith("! ")]


def test_the_four_packages_are_declared():
    for pkg in ("bm", "mathtools", "extarrows", "cancel"):
        assert re.search(r"\\usepackage\{%s\}" % pkg, rt.PREAMBLE), pkg


def test_stix2_is_NOT_declared():
    """It defines \\overparen and \\oiint and it cannot be loaded: amssymb +
    bbm + mathrsfs + stmaryrd already spend TeX's 16 math families, and
    adding it fails with 'Too many symbol fonts declared'."""
    assert "stix2" not in rt.PREAMBLE


def test_the_two_that_cannot_be_packages_are_providecommands():
    for cmd in ("Perp", "overparen", "oiint"):
        assert re.search(r"\\providecommand\{\\%s\}" % cmd, rt.PREAMBLE), cmd



def test_adding_stix2_really_does_exhaust_the_symbol_fonts():
    """The claim in the comment, checked rather than asserted."""
    rc, errs = _compile("$x$", extra="\\usepackage{stix2}\n")
    assert rc != 0
    assert any("symbol font" in e or "Too many" in e for e in errs), errs[:3]



def test_every_newly_covered_command_compiles():
    body = (r"$\bm{x}\coloneqq\overparen{D}\Perp\xlongequal{f}\oiint_S"
            r"\cancel{y}\mathbb{1}\mathscr{L}\llbracket z\rrbracket"
            r"\mathfrak{g}\longdiv{7}$")
    rc, errs = _compile(body)
    assert rc == 0 and not errs, errs[:3]



def test_what_was_already_there_still_compiles():
    """The control half: 600 corpus rows that rendered before rendered after,
    and this is the shape of that check in one row."""
    rc, errs = _compile(r"$\frac{1}{2}\sum_{i=1}^{n}\alpha_i\mathbb{R}"
                        r"\int_0^\infty e^{-x^2}\,dx$")
    assert rc == 0 and not errs, errs[:3]
