r"""The preamble loads the packages the emitted body's own commands need.

T-0156, requirement 1 (an error-free xelatex compile).

CENSUS of the eight e-prints: 146 xelatex errors, and EVERY class of them is
produced by the projector, not by the model or the reader. 74 were
`Undefined control sequence`, and 33 of those were commands this projector
emits that its FIXED preamble did not provide:

    \rowcolor   19     comes from `colortbl`
    \unitfrac   12     comes from `units`
    \unit        2

`xcolor` WAS loaded. `\rowcolor` arrives with `\usepackage[table]{xcolor}`,
so the package was right and the OPTION was missing.

A LONGER FIXED LIST WAS THE OBVIOUS FIX AND IS NOT THIS ONE. The table maps
a command to the package that defines it and is read against the .tex JUST
WRITTEN, so a command first emitted next month brings its package with it
instead of waiting for someone to notice an error and lengthen a list. A
command with no entry still reaches xelatex as an error: this resolves what
it knows and hides nothing.

IN PLACE, NOT APPENDED — and this cost a measurement. The head of a .tex is
not a package block: it carries the author's `\definecolor`, `\newcommand`
and theorem declarations too. Appending `\usepackage[table]{xcolor}` at the
end of the head put it BELOW the eight `\definecolor` calls in
2507.21892v1's preamble and took that document from 19 errors to 133. The
replacement now goes where the original `\usepackage` sat.

AND IT REPLACES RATHER THAN JOINS. Loading one package twice with different
options is an "Option clash", which is fatal — a worse error than the one
being removed.

MEASURED on the eight, before and after, with the content row:

    1503.00301         0 ->   0
    1703.08160         4 ->   4
    1909.00741        13 ->  13
    arxiv.0912.2444   36 ->  36
    arxiv.2402.03975  43 ->  43
    2102.08145        30 ->  16
    2602.11699v3       1 ->   1
    2507.21892v1      19 ->   0
                     146 -> 113

and every content column — graphics, tikz, tabular, equation, figure — is
identical on all eight.
"""
from docops.projectors.latex import _packages_the_body_needs as fix

HEAD = "\\documentclass{article}\n\\usepackage{graphicx,xcolor,url}\n"
DOC = "\\begin{document}\n%s\n\\end{document}\n"


def test_a_rowcolor_brings_colortbl_through_the_table_option():
    out = fix(HEAD + DOC % "\\rowcolor{gray}")
    assert "\\usepackage[table]{xcolor}" in out


def test_xcolor_is_replaced_not_loaded_twice():
    """Two loads with different options is an Option clash, which is fatal."""
    out = fix(HEAD + DOC % "\\rowcolor{gray}")
    head = out[:out.index("\\begin{document}")]
    assert head.count("xcolor") == 1


def test_the_package_goes_where_the_original_was():
    """2507.21892v1: appended, it landed below the author's \\definecolor
    calls and took the document from 19 errors to 133."""
    head = HEAD + "\\definecolor{x}{HTML}{112233}\n"
    out = fix(head + DOC % "\\rowcolor{x}")
    h = out[:out.index("\\begin{document}")]
    assert h.index("xcolor") < h.index("definecolor")


def test_unitfrac_brings_units():
    out = fix(HEAD + DOC % "\\unitfrac{1}{2}")
    assert "\\usepackage{units}" in out


def test_nothing_is_added_when_nothing_needs_it():
    t = HEAD + DOC % "plain prose only"
    assert fix(t) == t


def test_it_is_idempotent():
    t = "\\documentclass{article}\n\\usepackage[table]{xcolor}\n" + DOC % "\\rowcolor{g}"
    assert fix(t) == t


def test_a_longer_command_does_not_match():
    """`\\rowcolormodel` is not `\\rowcolor`."""
    t = "\\documentclass{article}\n" + DOC % "\\rowcolormodel"
    assert "usepackage" not in fix(t)


def test_a_command_with_no_entry_is_left_as_an_error():
    """This resolves what it knows; it does not hide an unknown command."""
    t = "\\documentclass{article}\n" + DOC % "\\someunknownmacro"
    assert fix(t) == t
