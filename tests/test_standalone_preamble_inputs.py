"""
826 — a package is not always loaded by \\usepackage.

`standalone_preamble` scanned for `\\usepackage{...}` and lifted the author's
macro definitions. XY-pic is loaded the plain-TeX way and matched neither:

    \\input xy
    \\xyoption{all} \\xyoption{poly} \\xyoption{knot}

arXiv 1102.1889 ("Ologs: a categorical framework for knowledge representation")
is 83 display equations of which 64 are `\\xymatrix`, and its preamble defines
`\\sq` in terms of `\\xymatrix`. The macro came across; the package that gives it
meaning did not. Each diagram then failed twice — `\\xymatrix` undefined, and
its `&` read as a misplaced alignment tab outside any alignment — for 1,029
errors in one evidence report, 503 of them that single `&` message.

Measured on the one equation, same compiler: 7 errors without the load, 0 with.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill.latex_source import standalone_preamble          # noqa: E402


def test_a_brace_less_input_is_carried_over():
    out = standalone_preamble("\\usepackage{amsmath}\n\\input xy\n")
    assert "\\input xy" in out


def test_the_options_travel_with_the_package():
    """`\\xyoption{all}` is meaningless before `\\input xy` and required after
    it, so lifting one without the other helps nothing."""
    out = standalone_preamble(
        "\\input xy\n\\xyoption{all} \\xyoption{poly}\n")
    assert "\\input xy" in out
    assert out.count("xyoption") == 2
    assert out.index("input xy") < out.index("xyoption")


def test_the_package_is_loaded_before_a_macro_that_needs_it():
    """The defect was not only the missing load: the preamble kept
    `\\renewcommand{\\sq}[4]{\\xymatrix{...}}`, which is illegal until xy is in."""
    out = standalone_preamble(
        "\\input xy\n\\newcommand{\\sq}[4]{\\xymatrix{#1\\ar[r]&#2}}\n")
    assert out.index("input xy") < out.index("\\sq")


def test_an_input_naming_a_FILE_is_refused():
    """`\\input mymacros.tex` names a file beside the source, which is not on
    the path when a cropped diagram compiles elsewhere. Lifting it turns a
    missing package into a missing file — the error moves, it does not go."""
    out = standalone_preamble(
        "\\input mymacros.tex\n\\input ../shared/defs\n\\input sub/thing\n")
    assert "mymacros" not in out
    assert "shared" not in out
    assert "sub/thing" not in out


def test_a_commented_out_input_is_not_lifted():
    out = standalone_preamble("% \\input xy\n\\usepackage{amsmath}\n")
    assert "\\input xy" not in out


def test_a_preamble_with_no_input_is_unchanged_in_that_respect():
    out = standalone_preamble("\\usepackage{amsmath}\n\\usepackage{amssymb}\n")
    assert "\\input" not in out
    assert "amsmath" in out and "amssymb" in out
