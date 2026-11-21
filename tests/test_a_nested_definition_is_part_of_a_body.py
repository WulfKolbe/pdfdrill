r"""A `\newcommand` inside another definition's body is not a definition.

T-0156, found while measuring class B and bigger than it.
`latex_source._collect_macro_defs` lifts the author's macro definitions out of
a preamble. Its `\def` loop has refused a nested one since 288, by brace depth
and by span membership; its `\newcommand` loop had NEITHER guard, and the two
shapes are the same shape.

Measured on arxiv.2402.03975, whose preamble builds commands by name:

    \newcommand\@newmathsfone[1]{
      \expandafter\newcommand\csname #1\endcsname{\mathsf{#1}}
    }

The inner `\newcommand\csname` was collected as a definition of its own and
emitted as

    \providecommand{\csname}{}\renewcommand\csname

— TeX's OWN `\csname` primitive, redefined to nothing. Everything after it
fails: "Missing control sequence inserted", "Extra \endcsname", "Missing
\begin{document}", and no PDF at all. The errors name neither the macro nor
the line that caused it.

IT WAS ALREADY REACHING `standalone_preamble`, which is where this collector's
output has always gone, so every figure crop of a document whose preamble uses
`\expandafter\newcommand\csname …\endcsname` was compiling against a destroyed
`\csname`. That is the defect; class B only walked into it.

The two guards, in the order 288 gives them:

  * BRACE DEPTH FIRST. A definition inside a `\pgfextra{}` inside a
    `\tikzset{}` is not covered by the span test at all, because those blocks
    are collected separately — 2602.23211's `\hgnodea`.
  * THEN SPAN MEMBERSHIP, for a definition nested directly in another's body.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

LS = pytest.importorskip("pdfdrill.latex_source")

BUILDER = "\n".join([
    r"\newcommand\@newmathsfone[1]{",
    r"  \expandafter\newcommand\csname #1\endcsname{\mathsf{#1}}",
    r"}",
])


def _names(preamble):
    return [LS._def_name(d) for d in LS._collect_macro_defs(preamble)]


def test_the_csname_primitive_is_not_collected_as_a_macro():
    """The exact shape, and the one that cost a 69-page PDF."""
    assert _names(BUILDER) == ["@newmathsfone"]


def test_the_outer_definition_is_still_collected_whole():
    r"""Refusing the inner one must not lose the outer one: its body is what
    builds the commands, `\expandafter` and all."""
    got = LS._collect_macro_defs(BUILDER)
    assert len(got) == 1
    assert "\\expandafter" in got[0]
    assert "\\endcsname" in got[0]


def test_a_top_level_definition_beside_it_is_kept():
    """The guards must be narrow: a definition of its own, at depth 0, outside
    every captured span, is exactly what this function is for."""
    assert _names(BUILDER + "\n" + r"\newcommand{\plain}{ok}") \
        == ["@newmathsfone", "plain"]


def test_the_brace_depth_test_is_deliberately_not_used_here():
    r"""THE `\def` LOOP'S OTHER GUARD WAS TRIED ON THIS LOOP AND LOSES, and
    the number is here so it is not tried again.

    `_depth_at` counts braces linearly from position 0, so ONE body it cannot
    balance by that count — a `\def` whose body holds an unmatched `{`, a
    `\verb`, a listings block — puts every later definition at depth > 0.
    Measured over 2,725 library source preambles, comment-stripped as both
    callers strip them: with the depth test 230 documents lose a collected
    definition, without it 91. Among the 139 it cost was

        \newcommand{\R}{{\rm I\!R}}

    standing in a plain run of top-level definitions — a definition this
    function exists to collect. So a `\newcommand` inside a delaying group is
    collected here, and that is a choice with a measurement behind it.
    """
    assert _names(r"\AtBeginDocument{\newcommand{\late}{x}}") == ["late"]
    plain = "\n".join([r"\def\unbalanced{ {\color{red} \textbf{?}}",
                      r"\newcommand{\R}{{\rm I\!R}}"])
    assert "R" in _names(plain)


def test_the_def_loop_keeps_the_guards_it_already_had():
    r"""288's cases, so a change to one loop cannot quietly drop the other's
    protection: a `\def` inside a body, and a `\def` inside a group."""
    nested = "\n".join([
        r"\def\outer#1\@nil@{\def\inner{#1}}",
        r"\tikzset{a/.code={\def\ingroup{x}}}",
        r"\def\toplevel{t}",
    ])
    assert _names(nested) == ["outer", "toplevel"]


def test_the_standalone_preamble_no_longer_destroys_csname():
    r"""The consequence, at the function that has always consumed this: a
    figure-crop preamble must not redefine a TeX primitive to nothing."""
    sa = LS.standalone_preamble(BUILDER)
    assert "providecommand{\\csname}" not in sa
    assert "renewcommand\\csname" not in sa
    assert "@newmathsfone" in sa


def test_a_primitive_is_never_collected_whatever_nested_it():
    r"""THE NAME TEST, which is complete where the structural one is partial.

    Span membership catches a nested `\newcommand` inside another
    `\newcommand`. It does NOT catch one inside a `\newenvironment` body or a
    `\tikzset{}`, because those are not `\newcommand` spans — measured, that
    is 5 of the 13 library documents whose preamble produces a `\csname`
    "definition". A name test reaches all 13, and costs nothing: no author
    defines `\csname`.
    """
    inside_env = (r"\newenvironment{ex}{\expandafter\newcommand"
                  r"\csname z\endcsname{q}}{}")
    assert "csname" not in _names(inside_env)
    assert "csname" not in _names(BUILDER)
    for name in ("csname", "endcsname", "expandafter", "relax", "begin", "end"):
        assert name in LS._NEVER_A_MACRO


def test_a_package_name_is_not_on_that_list():
    r"""The list is TeX's own and the kernel's, not anything a package
    defines: an author may legitimately `\renewcommand` a package's command,
    and `_robustify_macro_defs` already makes that safe."""
    for name in ("qedsymbol", "theenumi", "labelenumi", "arraystretch",
                 "interval", "xspace"):
        assert name not in LS._NEVER_A_MACRO


def test_a_refused_definition_still_shields_what_is_nested_in_it():
    r"""The span is recorded even when the definition itself is refused, so a
    definition nested inside a refused one is still seen as nested rather than
    becoming a top-level definition by accident."""
    nested_in_refused = (r"\newcommand\csname{\newcommand{\inner}{x}}")
    assert _names(nested_in_refused) == []
