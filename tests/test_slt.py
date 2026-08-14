"""LaTeX -> Symbol Layout Tree, and the .lg round trip (T4 deliverables 1-2).

An SLT (Zanibbi, Blostein & Cordy, TPAMI 2002) is the tree a recogniser must
recover: symbols as nodes, spatial relations as edges. `A_{i,j}^{h,l}` in the
author's source STATES that tree, which is why the arXiv LaTeX is ground truth
for structure and not merely for text.

`.lg` is the label-graph format LgEval scores, and CROHME / InftyMCCDB-2
distribute. Node lines are `N, id, label, weight`; edge lines are
`E, parent, child, relation, weight`.

Rule 5 governs the unknown case: an unsupported construct is never given a
plausible relation. It raises, or is emitted as an explicit unresolved node —
never a sentinel string, because two unidentified things must not compare equal.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from mathgold.slt import (RIGHT, SUP, SUB, ABOVE, BELOW, INSIDE,
                          Unresolved, lg_to_slt, parse_latex_slt, slt_to_lg)


def rels(slt):
    """(parent_label, child_label, relation) for every edge — order-independent."""
    lab = {n.id: n.label for n in slt.nodes}
    return sorted((lab[e.parent], lab[e.child], e.relation) for e in slt.edges)


def labels(slt):
    return sorted(n.label for n in slt.nodes)


# --------------------------------------------------------------------------
# the relations an SLT is made of
# --------------------------------------------------------------------------

def test_adjacent_symbols_are_horizontal():
    slt = parse_latex_slt("a b")
    assert labels(slt) == ["a", "b"]
    assert rels(slt) == [("a", "b", RIGHT)]


def test_superscript_and_subscript():
    assert rels(parse_latex_slt("x^2")) == [("x", "2", SUP)]
    assert rels(parse_latex_slt("x_i")) == [("x", "i", SUB)]


def test_both_scripts_attach_to_the_same_base():
    """`A_{i}^{h}` is one base with two relations, not a chain."""
    assert rels(parse_latex_slt("A_{i}^{h}")) == [("A", "h", SUP), ("A", "i", SUB)]


def test_a_multi_symbol_script_keeps_its_internal_structure():
    """The handover's example: `A_{i,j}^{h,l}` states a tree, and the commas
    are symbols in it."""
    slt = parse_latex_slt("A_{i,j}^{h,l}")
    assert rels(slt) == sorted([("A", "h", SUP), ("h", ",", RIGHT), (",", "l", RIGHT),
                                ("A", "i", SUB), ("i", ",", RIGHT), (",", "j", RIGHT)])


def test_a_fraction_relates_numerator_above_and_denominator_below():
    slt = parse_latex_slt(r"\frac{a}{b}")
    assert rels(slt) == sorted([(r"\frac", "a", ABOVE), (r"\frac", "b", BELOW)])


def test_a_radical_encloses_its_argument():
    assert rels(parse_latex_slt(r"\sqrt{x}")) == [(r"\sqrt", "x", INSIDE)]


def test_a_control_sequence_is_one_symbol():
    slt = parse_latex_slt(r"\alpha + \beta")
    assert labels(slt) == ["+", r"\alpha", r"\beta"]


def test_braces_group_without_becoming_symbols():
    """`{ab}c` is three symbols; the braces are syntax, not ink."""
    assert labels(parse_latex_slt("{ab}c")) == ["a", "b", "c"]


def test_whitespace_and_spacing_commands_are_not_symbols():
    for src in (r"a \, b", r"a \quad b", "a  b", r"a\!b"):
        assert labels(parse_latex_slt(src)) == ["a", "b"], src


# --------------------------------------------------------------------------
# rule 5 — never a plausible default
# --------------------------------------------------------------------------

def test_an_unsupported_construct_becomes_an_explicit_unresolved_node():
    slt = parse_latex_slt(r"\begin{matrix} a \end{matrix}")
    unres = [n for n in slt.nodes if isinstance(n.label, Unresolved)]
    assert unres, "an unhandled environment was silently given a plausible label"


def test_two_unresolved_things_are_not_equal():
    """A sentinel string would make every unidentified symbol the same symbol."""
    a, b = Unresolved("matrix"), Unresolved("matrix")
    assert a != b
    assert a == a


def test_an_unbalanced_expression_raises_rather_than_guessing():
    for bad in (r"\frac{a}", "x^", "{a"):
        with pytest.raises(ValueError):
            parse_latex_slt(bad)


# --------------------------------------------------------------------------
# the .lg round trip
# --------------------------------------------------------------------------

def test_lg_has_one_node_line_per_symbol_and_one_edge_line_per_relation():
    lg = slt_to_lg(parse_latex_slt("x^2"))
    body = [l for l in lg.splitlines() if l and not l.startswith("#")]
    assert sum(1 for l in body if l.startswith("N,")) == 2
    assert sum(1 for l in body if l.startswith("E,")) == 1
    assert any(l.startswith("E,") and l.rstrip().endswith("1.0") for l in body)


def test_the_round_trip_preserves_labels_and_relations():
    for src in ("a b", "x^2", "A_{i,j}^{h,l}", r"\frac{a}{b}", r"\sqrt{x+1}",
                r"\alpha^{2} + \beta_{k}"):
        slt = parse_latex_slt(src)
        back = lg_to_slt(slt_to_lg(slt))
        assert labels(back) == labels(slt), src
        assert rels(back) == rels(slt), src


def test_a_label_containing_a_comma_survives_the_round_trip():
    """`,` is both a symbol and the .lg field separator."""
    slt = parse_latex_slt("a,b")
    back = lg_to_slt(slt_to_lg(slt))
    assert labels(back) == ["*", "a", "b"] or labels(back) == [",", "a", "b"]
    assert rels(back) == rels(slt)


def test_lg_ignores_comments_and_blank_lines():
    lg = "# CROHME header\n\nN, n0, x, 1.0\n\n# mid-file\nN, n1, 2, 1.0\nE, n0, n1, Sup, 1.0\n"
    slt = lg_to_slt(lg)
    assert labels(slt) == ["2", "x"]
    assert rels(slt) == [("x", "2", SUP)]


def test_an_empty_expression_is_an_empty_graph_not_an_error():
    slt = parse_latex_slt("")
    assert slt.nodes == [] and slt.edges == []
    assert lg_to_slt(slt_to_lg(slt)).nodes == []


def test_a_transparent_modifier_does_not_separate_a_base_from_its_scripts():
    """`\\sum\\limits_{i}` is a base with a subscript. Treating `\\limits` as a
    term left the `_` with no base — 18 of 3000 real gold equations raised on
    exactly this."""
    slt = parse_latex_slt(r"\sum\limits_{i}^{n}")
    assert rels(slt) == sorted([(r"\sum", "i", SUB), (r"\sum", "n", SUP)])
    assert labels(slt) == [r"\sum", "i", "n"]   # `\` sorts before letters


def test_spacing_does_not_separate_a_base_from_its_scripts():
    r"""`c\;\!\!^\dagger` is a creation operator with the dagger tucked in.

    Same defect as `\limits`, same class of cause: spacing carries no ink, so
    treating it as a TERM ended the base's run and left the `^` with nothing to
    attach to. Four of the 59 scorable gold equations raised on exactly this —
    every one of them this construct.
    """
    slt = parse_latex_slt(r"c\;\!\!^\dagger_{i}")
    assert labels(slt) == [r"\dagger", "c", "i"]
    assert rels(slt) == sorted([("c", r"\dagger", SUP), ("c", "i", SUB)])


def test_a_font_wrapper_is_transparent_and_can_carry_a_script_argument():
    r"""`\dfrac{\mathrm{i}}{\hbar}` — `\mathrm` selects a typeface and puts no
    ink of its own on the page.

    Treated as a TERM it returned nothing, so `x^\mathrm{i}` raised "script
    argument is empty": 55 of 21,334 corpus equations, the largest remaining
    failure class after the spacing fix, and the same defect a third time — a
    no-ink command standing where a symbol was required.
    """
    assert labels(parse_latex_slt(r"x^\mathrm{i}")) == ["i", "x"]
    assert rels(parse_latex_slt(r"x^\mathrm{i}")) == [("x", "i", SUP)]
    assert labels(parse_latex_slt(r"\mathrm{ab}")) == ["a", "b"]


def test_an_unbraced_script_argument_is_one_atom_and_takes_no_script_of_its_own():
    r"""`x^a_b` is x with BOTH scripts — not x sup (a sub b).

    An unbraced script argument is a single atom in LaTeX; parsing it as a full
    term let it swallow the following `_`, silently rebuilding the tree one
    level too deep. Braces still mean what they say: `x^{a_b}` really is nested.
    """
    assert rels(parse_latex_slt("x^a_b")) == sorted([("x", "a", SUP), ("x", "b", SUB)])
    assert rels(parse_latex_slt("x^{a_b}")) == sorted([("x", "a", SUP), ("a", "b", SUB)])


def test_delimiter_sizing_is_transparent_but_the_delimiter_is_ink():
    slt = parse_latex_slt(r"\left( a \right)")
    assert labels(slt) == ["(", ")", "a"]


def test_a_script_on_a_GROUP_attaches_to_its_rightmost_symbol():
    """`{ab}^c` puts c after b, so the Sup edge starts at b. Every earlier test
    used a single-symbol base, where head and tail coincide — so the choice was
    unexercised and a mutation swapping them survived."""
    assert rels(parse_latex_slt("{ab}^c")) == sorted([("a", "b", RIGHT), ("b", "c", SUP)])


def test_a_script_on_a_fraction_attaches_to_the_fraction():
    """The fraction node IS both head and tail, so this pins the single-symbol
    case alongside the group case."""
    assert rels(parse_latex_slt(r"\frac{a}{b}^{2}")) == sorted(
        [(r"\frac", "a", ABOVE), (r"\frac", "b", BELOW), (r"\frac", "2", SUP)])
