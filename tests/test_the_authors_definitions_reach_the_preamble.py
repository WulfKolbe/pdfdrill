r"""The author's MACRO DEFINITIONS reach the document preamble. Nothing else does.

T-0156 class B. `build_from_source` stored only the `standalone` crop preamble,
and `_doc_preamble` correctly refuses that as a document preamble (it typesets
in LR mode, so `\section` errors "Not allowed in LR mode") and fell back to
`_DEFAULT_PREAMBLE` — so the author's macros were thrown away and `\gameval`,
`\disc`, `\payoff`, `\edges`, `\PLS` all arrived undefined.

TWO WIDER VERSIONS WERE MEASURED AND REFUTED FIRST, over the audit's eight
e-prints, each half compiled from a clean directory:

    A  the author's whole preamble replacing ours
       241 -> 384 over the seven that still produced a PDF; the eighth produced
       none. Three mechanisms: the tarball is not self-contained (`arximspdf`
       dies on `File 'texsort.sty' not found`); the class changes what the body
       assumed (under `acmart`, `width=\linewidth` divides by zero and 20 crops
       fail); the author's preamble lacks what our projection needs (82
       misplaced `&`, 49 `\omit`, 34 `\span`).

    B  our class plus the author's packages and macros
       1503.00301 0 PDF -> 0 PDF; arxiv.0912.2444 142 PDF -> 142 PDF;
       arxiv.2402.03975 187 PDF -> 93 and NO PDF. `amsaddr` assumes an AMS
       class, where `\email` IS a class command, and we keep `article` — so a
       package the author loads needs the class we refused.

EVERY ONE OF THOSE FOUR MECHANISMS IS A PROPERTY OF A CLASS OR A
`\usepackage`, and a `\newcommand` body has neither. So only the definitions
come across, and `_robustify_macro_defs` emits each as
`\providecommand{\name}{}` + `\renewcommand` — the same guard the `\email`
failure needed, so a macro that depended on a package we do not load still
defines rather than erroring.

AND THE AUTHOR'S MACROS ARE NORMALLY EXPANDED, NOT DEFINED — which is why
this is a safety net and not a second strategy. `expand_macros` / `expand_math`
substitute a macro's body into equations, paragraphs, theorems, proofs,
abstracts, prose and a Diagram's code (see
`test_the_authors_macros_reach_the_statement`, which closed the branches that
did not). A definition emitted here for a macro that WAS expanded defines
something nothing calls, and costs a line.

What it buys is the calls that survive unexpanded. Measured on
arxiv.2402.03975, those are `\disc` 17, `\gameval` 9, `\edges` 4, `\payoff`
4, `\PLS` 2, `\FP`, `\DetG`, `\StG`, `\pUEOPL`, `\UP` — about 41 of its
120 undefined control sequences. It is also the enabling half of the audit's
own recommendation 2 for class A, "do not expand a macro whose body uses
`\@ifstar` or other @-commands; keep the call AND the definition": keeping the
call is only safe once the definition travels with it.

WHAT THIS FILE OWNS is that nothing but definitions crosses the boundary, that
both writers of the author's preamble are read, that a model carrying neither
key is left byte-for-byte as it was, and that a preamble `injectlatex`
captured is not given the definitions twice.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

L = pytest.importorskip("docops.projectors.latex")
S = pytest.importorskip("pdfdrill.latex_source")

AUTHOR = "\n".join([
    r"\documentclass[a4paper,10pt]{article}",
    r"\usepackage[utf8]{inputenc}",
    r"\usepackage[T1]{fontenc}",
    r"\usepackage{geometry}",
    r"\usepackage{xspace}",
    r"\usepackage{interval}",
    r"\newcommand{\RDF}{\textsc{rdf}\xspace}",
])


def _preamble(meta):
    return L.LaTeXProjector._doc_preamble(
        L.LaTeXProjector.__new__(L.LaTeXProjector), meta)


# ── what the author's content is cut down to ────────────────────────────────

def test_the_authors_class_line_does_not_come_across():
    r"""The whole point: the packages and macros, never the `\documentclass`.
    `standalone_preamble` opens with the standalone class and that line is
    dropped, so nothing can set the document's class but us."""
    out = S.document_addon_preamble(AUTHOR)
    assert "\\documentclass" not in out


def test_the_authors_macro_definitions_do_come_across():
    out = S.document_addon_preamble(AUTHOR)
    assert "\\RDF" in out and "textsc{rdf}" in out


@pytest.mark.parametrize("line", [
    "\\usepackage{xspace}", "\\usepackage{interval}", "\\usepackage{geometry}",
])
def test_not_one_usepackage_crosses_the_boundary(line):
    r"""Variant B loaded them and 2402.03975 lost its PDF: `amsaddr` needs the
    AMS class we refused. A package is the author's ENVIRONMENT; only the
    definitions are the author's mathematics."""
    assert line not in S.document_addon_preamble(AUTHOR)


def test_a_definition_is_guarded_so_it_cannot_error_undefined():
    r"""`_robustify_macro_defs`: `\providecommand{\name}{}` then
    `\renewcommand`. Without it a `\renewcommand` of a name only a dropped
    package defined fails "Command \name undefined" — which is exactly how
    variant B lost a PDF."""
    out = S.document_addon_preamble(AUTHOR)
    assert "\\providecommand{\\RDF}{}" in out
    assert "\\renewcommand{\\RDF}" in out


def test_an_at_name_is_wrapped_so_the_braces_still_count():
    r"""A definition whose name contains `@` is only legal between
    `\makeatletter` and `\makeatother`; lifted out bare, `\appendix@section`
    parses as `\appendix` plus the text `@section` and LaTeX reports "Missing
    \begin{document}" a hundred lines later."""
    out = S.document_addon_preamble(
        AUTHOR + "\n\\def\\appendix@section#1{x}")
    assert out.startswith("\\makeatletter")
    assert out.rstrip().endswith("\\makeatother")


def test_no_author_preamble_is_not_an_empty_one():
    r"""`standalone_preamble` always opens with its own `\usepackage{tikz}`, so
    without an explicit guard an ABSENT preamble answered that one line and
    "the author loaded nothing" could not be told from "there was no author"."""
    assert S.document_addon_preamble("") == ""
    assert S.document_addon_preamble("   \n  ") == ""


# ── how the projector uses it ───────────────────────────────────────────────

def test_a_model_with_neither_key_is_left_exactly_as_it_was():
    """The explicit fallback. Every model built before this stores neither key,
    and its preamble must be byte-for-byte what it was — not an empty one."""
    assert _preamble({}) == L._DEFAULT_PREAMBLE
    assert _preamble({"latex_preamble": {"main": "x.tex"}}) == L._DEFAULT_PREAMBLE
    assert _preamble({"latex_preamble": {"packages_macros": ""}}) \
        == L._DEFAULT_PREAMBLE


def test_the_source_builders_key_is_read():
    """`latex_source.build_from_source` precomputes `packages_macros`."""
    got = _preamble({"latex_preamble": {
        "packages_macros": "\\providecommand{\\q}{}\\renewcommand{\\q}{Q}"}})
    assert got.startswith(L._DEFAULT_PREAMBLE.rstrip())
    assert got.rstrip().endswith("\\renewcommand{\\q}{Q}")


def test_the_inject_builders_key_is_read_too():
    r"""`cmd_injectlatex` stores the author's RAW preamble as `original`, and
    deriving the addon from it here reaches every model that already carries
    the preamble without a rebuild. Measured on the eight: only one source-built
    document improves, so a rule that read `packages_macros` alone would have
    reached a quarter of the measurement it came from."""
    got = _preamble({"latex_preamble": {
        "original": AUTHOR,
        # the real value this key holds, which `standalone_preamble` writes
        "standalone": S.standalone_preamble(AUTHOR)}})
    assert "\\renewcommand{\\RDF}" in got
    assert "\\usepackage{interval}" not in got      # the package is not ours to load
    assert got.startswith(L._DEFAULT_PREAMBLE.rstrip())


def test_the_precomputed_key_wins_over_deriving_it_again():
    """Both present: the stored one is used, so a model's own content cannot be
    silently replaced by a re-derivation at projection time."""
    got = _preamble({"latex_preamble": {"packages_macros": "\\def\\stored{S}",
                                        "original": AUTHOR}})
    assert "\\def\\stored{S}" in got
    assert "\\RDF" not in got


def test_a_standalone_preamble_is_still_refused_as_a_document_preamble():
    r"""Unchanged, and it is why class B existed: the crop preamble typesets in
    LR mode. Its packages still arrive, through the addon."""
    meta = {"latex_preamble": {
        "standalone": "\\documentclass[border=2pt]{standalone}\n"
                      "\\usepackage{tikz}",
        "packages_macros": "\\def\\kept{K}"}}
    got = _preamble(meta)
    assert "{standalone}" not in got
    assert got.startswith(L._DEFAULT_PREAMBLE.rstrip())
    assert "\\def\\kept{K}" in got


def test_a_captured_document_preamble_is_not_given_the_definitions_twice():
    r"""A preamble `injectlatex` captured as `expanded` IS a document preamble
    and carries the author's definitions itself. Appending them again would
    emit each one twice; harmless for a `\\renewcommand` and not for a
    `\\newcounter` or a `\\newsavebox`, which error on the second."""
    meta = {"latex_preamble": {
        "expanded": "\\documentclass{article}\n\\def\\dup{D}",
        "packages_macros": "\\def\\dup{D}"}}
    got = _preamble(meta)
    assert got.count("\\def\\dup{D}") == 1


def test_the_addon_goes_after_the_default_so_a_redefinition_wins():
    r"""The same reason `_DEFAULT_PREAMBLE` puts `stmaryrd` after `amssymb`:
    the later definition is the one that stands. An author who redefines a
    symbol our packages provide means his own."""
    got = _preamble({"latex_preamble": {
        "packages_macros": "\\renewcommand{\\ZZZmarker}{z}"}})
    assert got.index("amssymb") < got.index("ZZZmarker")


def test_with_addon_is_a_plain_function_of_its_two_arguments():
    """So the ordering rule can be stated without building a projector."""
    assert L._with_addon("BASE\n", "") == "BASE\n"
    assert L._with_addon("BASE\n", "X") == "BASE\nX\n"

def test_the_standalone_key_is_refused_by_its_own_class_line():
    r"""WHY it never reaches the output, pinned because the mechanism is not
    obvious. `standalone` is still a candidate in `_doc_preamble`'s `or` chain;
    what rejects it is the `\documentclass{standalone}` line that
    `standalone_preamble` always writes at its head. A stored value that had
    lost that line would be emitted as a document preamble — so the guard is
    the line, not the key's name, and this test states which.
    """
    sa = S.standalone_preamble(AUTHOR)
    assert sa.lstrip().startswith("\\documentclass")
    assert "{standalone}" in sa.splitlines()[0]
    assert _preamble({"latex_preamble": {"standalone": sa}}) \
        == L._DEFAULT_PREAMBLE

def test_the_addon_never_carries_a_redefinition_of_a_primitive():
    r"""The consequence here of the collector's own guard (see
    `test_a_nested_definition_is_part_of_a_body`): a preamble that builds
    commands by name must not send `\providecommand{\csname}{}` into the
    document, which is how the first attempt at this change cost
    arxiv.2402.03975 its 69-page PDF."""
    builder = "\n".join([
        r"\newcommand\@newmathsfone[1]{",
        r"  \expandafter\newcommand\csname #1\endcsname{\mathsf{#1}}",
        r"}",
    ])
    out = S.document_addon_preamble(builder)
    assert "providecommand{\\csname}" not in out
    assert "@newmathsfone" in out
