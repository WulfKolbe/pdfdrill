r"""137 — macro definitions apply in SOURCE ORDER, last one wins, as TeX does.

Each form used to be collected in its own pass, and \def used setdefault (FIRST
wins), so precedence was decided by which regex ran rather than by the document.

build_source_model INLINES \input before parsing, so every included file lands
in one string. preprints202505.0818.v1 defines \bS twice — \begin{slide} in
_definitions.tex, then \mathbb{S} in jin_thesis_macros.tex — and TeX takes the
second. We took the first and expanded 168 uses into a slide fragment.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.latex_source import extract_macros


def test_two_defs_last_wins():
    m = extract_macros("\\def\\bS{\\begin{slide}}\n\\def\\bS{\\mathbb{S}}")
    assert m["bS"]["body"] == "\\mathbb{S}"


def test_two_defs_the_other_way_round():
    """Symmetry: the fix must follow the ORDER, not prefer a particular body."""
    m = extract_macros("\\def\\bS{\\mathbb{S}}\n\\def\\bS{\\begin{slide}}")
    assert m["bS"]["body"] == "\\begin{slide}"


def test_def_then_newcommand():
    m = extract_macros("\\def\\x{FIRST}\n\\newcommand{\\x}{SECOND}")
    assert m["x"]["body"] == "SECOND"


def test_newcommand_then_def():
    """The case a plain setdefault->assignment change would have broken in the
    other direction: a \\def must not beat a \\newcommand that came AFTER it."""
    m = extract_macros("\\newcommand{\\y}{FIRST}\n\\def\\y{SECOND}")
    assert m["y"]["body"] == "SECOND"


def test_newcommand_then_renewcommand():
    m = extract_macros("\\newcommand{\\z}{FIRST}\n\\renewcommand{\\z}{SECOND}")
    assert m["z"]["body"] == "SECOND"


def test_declaremathoperator_participates_in_the_order():
    m = extract_macros("\\def\\op{FIRST}\n\\DeclareMathOperator{\\op}{tr}")
    assert m["op"]["body"] == "\\operatorname{tr}"
    m2 = extract_macros("\\DeclareMathOperator{\\op}{tr}\n\\def\\op{LAST}")
    assert m2["op"]["body"] == "LAST"


def test_arguments_survive_the_reordering():
    m = extract_macros("\\def\\ad#1#2{({\\rm ad}\\,#1)^{#2}}")
    assert m["ad"]["nargs"] == 2 and "\\rm ad" in m["ad"]["body"]


def test_optional_default_survives():
    m = extract_macros("\\newcommand{\\q}[2][D]{#1#2}")
    assert m["q"]["nargs"] == 2 and m["q"]["default"] == "D"


def test_unrelated_macros_are_all_kept():
    m = extract_macros("\\def\\a{A}\n\\def\\b{B}\n\\newcommand{\\c}{C}")
    assert {m["a"]["body"], m["b"]["body"], m["c"]["body"]} == {"A", "B", "C"}


def test_alphabet_declaration_still_recorded_with_no_body():
    m = extract_macros("\\newmathalphabet*\\got{euf}{m}{n}")
    assert m["got"]["body"] is None and m["got"]["alphabet"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
