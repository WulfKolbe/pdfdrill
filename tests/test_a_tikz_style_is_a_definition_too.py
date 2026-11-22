r"""A tikz style is a definition too, and it must bring its own package.

T-0156, requirement 1, fourth step.

`document_addon_preamble` carries the author's macro definitions. Its
collector matches the `\newcommand` family and `\DeclareMathOperator`; a
picture's styles are defined by `\tikzstyle` and `\tikzset`, which it did
not match. So carried tikz content referred to styles that no longer
existed: "Package pgfkeys Error: I do not know the key '/tikz/process'",
11 of the eight e-prints' errors, all on 2102.08145.

IT RECURS, which is why it is built at all. Over 150 source-built library
documents, 11 define tikz styles in their preamble and 8 of those also draw
a `tikzpicture` — against 1 in 121 for the macro-generator shape, which was
refused for being one paper's idiom.

TWO SYNTAXES, and only one is brace-balanced:

    \tikzstyle{process} = [rectangle, minimum width=2.5cm, …]
    \tikzset{arrow/.style={thick,->}}

NOT ROBUSTIFIED. `_robustify_macro_defs` wraps a macro as
`\providecommand{\name}{}\renewcommand…`, right for a control sequence and
wrong for a style: a style is a key in pgf's table, and the wrapper would
define a macro named after it instead.

AND THE STYLES CARRY `\usepackage{tikz}` THEMSELVES. The addon is placed
BEFORE the preamble's own tikz load, so emitted bare they land above the
package that defines `\tikzstyle` and every one is an "Undefined control
sequence" — measured, 2102.08145 went 16 errors to 1583.

THAT IS THE SAME ORDERING MISTAKE AS `\usepackage[table]{xcolor}` BELOW THE
AUTHOR'S `\definecolor`, two commits earlier in this task, where 19 errors
became 133. Writing the lesson in a commit message did not prevent the
repeat; carrying the package WITH the thing that needs it does, because
then there is no order to get wrong.

MEASURED: 2102.08145 16 -> 5, the total 84 -> 73, every content column
identical.
"""
from pdfdrill.latex_source import _collect_tikz_styles, document_addon_preamble

PRE = r"""
\documentclass{article}
\tikzstyle{process} = [rectangle, minimum width=2.5cm, draw=black]
\tikzstyle{arrow} = [thick,->,>=stealth]
\tikzset{n/.style={thick}}
\newcommand{\x}{y}
"""


def test_a_tikzstyle_is_carried_with_its_bracket_body():
    """The body is in BRACKETS after `=`, which a brace walk cannot see."""
    got = _collect_tikz_styles(PRE)
    assert r"\tikzstyle{process} = [rectangle, minimum width=2.5cm, draw=black]" in got


def test_a_tikzset_is_carried_with_its_brace_body():
    assert r"\tikzset{n/.style={thick}}" in _collect_tikz_styles(PRE)


def test_every_style_is_carried_in_source_order():
    r"""An author who redefines a style keeps the later one, as intended."""
    got = _collect_tikz_styles(PRE)
    assert len(got) == 3
    assert got[0].startswith(r"\tikzstyle{process}")
    assert got[1].startswith(r"\tikzstyle{arrow}")


def test_the_styles_bring_their_own_package():
    """Placed bare, they land above the preamble's own tikz load: 16 -> 1583."""
    addon = document_addon_preamble(PRE)
    assert r"\usepackage{tikz}" in addon
    assert addon.index(r"\usepackage{tikz}") < addon.index(r"\tikzstyle{process}")


def test_the_macros_are_still_carried_beside_them():
    addon = document_addon_preamble(PRE)
    assert "\\x" in addon


def test_a_preamble_with_no_styles_gains_no_tikz():
    """The package comes only with a style that needs it."""
    addon = document_addon_preamble("\\documentclass{article}\n\\newcommand{\\a}{b}\n")
    assert r"\usepackage{tikz}" not in addon


def test_a_style_is_not_robustified():
    r"""A style is a pgf key, not a control sequence: `\providecommand`
    around it would define a macro named after the style instead."""
    addon = document_addon_preamble(PRE)
    assert r"\providecommand{\tikzstyle}" not in addon
    assert r"\tikzstyle{process} = [" in addon
