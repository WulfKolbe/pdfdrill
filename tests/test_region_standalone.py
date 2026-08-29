r"""286 — compiling a region's LaTeX alone, with the author's preamble.

A region's LaTeX routinely depends on things a generic document does not have:
the author's macros (`\<v|`), their figure files (`figures/ch1/concept2`),
their colours and tikz styles. `latex_source.standalone_preamble()` already
extracts exactly that from a document's own preamble and `injectlatex` stores
it on the model.

But the author's preamble is not always better. Injecting it ALONE moved a
10-document sample from 66.7% to 52.2%: it rescued the documents whose regions
need it and destroyed three whose extracted preamble does not stand alone. So
the render tries the author's first and falls back to the generic one.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from pdfdrill.region_standalone import (document, needs_math_wrapper,
                                        PREAMBLE, _GUARDED_PKGS)


@pytest.mark.parametrize("latex,wrap", [
    (r"x^2 + 1", True),
    (r"\frac{a}{b}", True),
    (r"\begin{tikzpicture}\draw(0,0)--(1,1);\end{tikzpicture}", False),
    (r"\begin{tikzcd} A\arrow[r]&B \end{tikzcd}", False),
    (r"\begin{tabular}{c}a\end{tabular}", False),
    (r"\begin{lstlisting}x\end{lstlisting}", False),
])
def test_only_bare_maths_is_wrapped_in_math_mode(latex, wrap):
    """A picture wrapped in $...$ is not a picture. The inline version of this
    got it wrong the other way and set tikzcd as mathematics."""
    assert needs_math_wrapper(latex) is wrap
    doc = document(latex)
    assert (r"$\displaystyle" in doc) is wrap


def test_the_authors_preamble_replaces_the_generic_head():
    author = "\\documentclass[border=2pt,class=report]{standalone}\n" \
             "\\newcommand{\\myop}{\\mathrm{Op}}"
    doc = document(r"\myop(x)", author_preamble=author)
    assert "\\newcommand{\\myop}" in doc
    assert doc.count("\\documentclass") == 1      # not both heads


def test_the_guarded_packages_are_appended_to_the_authors_preamble():
    """A region may use tikz-cd or adjustbox whether or not the source document
    loaded them; a duplicate \\usepackage is a no-op."""
    doc = document(r"\begin{tikzcd}A\end{tikzcd}",
                   author_preamble="\\documentclass{standalone}")
    for pkg in ("tikz-cd.sty", "adjustbox.sty", "listings.sty"):
        assert pkg in doc


def test_every_package_is_guarded_by_IfFileExists():
    """221's rule: an unguarded \\usepackage for a package this machine lacks
    aborts the compile and produces NOTHING, which is worse than the row it
    would have set."""
    for line in _GUARDED_PKGS.strip().split("\n"):
        assert line.startswith("\\IfFileExists{"), line
    assert PREAMBLE.count("\\IfFileExists{") >= 4


def test_graphicspath_points_at_the_eprint():
    """`figures/ch1/concept2' not found — the file is in the e-print beside the
    model, so the standalone document has to be told where to look."""
    doc = document(r"\includegraphics{figures/ch1/concept2}",
                   graphics_dir=Path("/lib/doc/texsrc"))
    assert "\\graphicspath{{/lib/doc/texsrc/}{/lib/doc/texsrc/figures/}}" in doc


def test_no_graphics_dir_emits_no_graphicspath():
    assert "graphicspath" not in document(r"x^2")


def test_a_document_with_no_author_preamble_uses_the_generic_one():
    doc = document(r"x^2")
    assert doc.startswith("\\documentclass[border=3pt]{standalone}")
