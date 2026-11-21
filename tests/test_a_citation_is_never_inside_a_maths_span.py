r"""A citation is prose. It is never placed inside a maths span.

T-0156, found while measuring class B rather than while looking for it.
`apply_subs` places a citation group by LITERAL search for its source
substring, and a bracket-inclusive numeric source is the string `[4]` -- which
also occurs inside the mathematics, meaning something else entirely.
1503.00301's paragraph reads

    \(\varepsilon>4 / \sqrt[4]{|\boldsymbol{A}|+|\boldsymbol{B}|}\)

and the projection came out

    \(\varepsilon>4 / \sqrt\cite{atre2010matrix}{|\boldsymbol{A}|+…}\)

The `[4]` that matched is `\sqrt`'s OPTIONAL ARGUMENT, the degree of a fourth
root. Replacing it leaves `\sqrt` taking `\cite` as its argument and
`{|A|+|B|}` stray -- which is where that document's two baseline errors come
from: `Missing { inserted` and `Missing } inserted` are one event, and both
were in the gate's 383 all along.

HOW IT WAS FOUND, because the route matters. The class B experiment made the
document WORSE, 2 errors to 8, and the six new ones were `You can't use
\spacefactor in math mode`. Reading the trace rather than the total named
`\cite@adjust`, which is `cite.sty` -- a package the author's style chain
loads, whose `\cite` touches `\spacefactor`, illegal in math mode. So a failed
gate on someone else's preamble was a defect of ours that the default
preamble's kernel `\cite` merely tolerated.

`_numeric_source_in_context` already guards the BARE-digit case ("1" inside
"Stein1970"), and it never ran here: `[4]` is not a bare digit but the
bracket-inclusive form, which that test accepts anywhere on purpose. The
missing rule is not about digits — it is that the maths is not prose.

Two occurrences across the eight T-0156 e-prints, both on this document, and
ZERO on the glyphlines/board side: 192 board `ours.lines.json` readings and
every board `.glyphs.tex` hold none, because that path emits glyphs and does
no citation substitution at all.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

C = pytest.importorskip("docops.projectors.citations")


def _sub(source, replacement):
    return C.Sub(anchor=None, offset=0, length=len(source), source=source,
                 replacement=replacement, keys=())


def test_the_degree_of_a_root_is_not_a_citation():
    """The 1503.00301 shape, end to end: the bracket inside the maths is
    passed over and the one in the prose after the formula is taken."""
    text = (r"any \(\varepsilon>4 / \sqrt[4]{|A|+|B|}\). "
            r"See also [4] for the bound.")
    out = C.apply_subs(text, [_sub("[4]", r"\cite{atre2010matrix}")])
    assert r"\sqrt[4]{|A|+|B|}" in out          # the maths is untouched
    assert r"See also \cite{atre2010matrix} for" in out
    assert r"\sqrt\cite" not in out


def test_the_citation_lands_after_the_formula_as_on_the_page():
    """The page reads "ε > 4/√(|A|+|B|) [4]" -- formula, then citation. The
    substitution must not reorder them."""
    text = r"\(\varepsilon>4 / \sqrt[4]{|A|+|B|}\) [4]."
    out = C.apply_subs(text, [_sub("[4]", r"\cite{atre2010matrix}")])
    assert out.index(r"\sqrt[4]") < out.index(r"\cite{atre2010matrix}")
    assert out.endswith(r"\cite{atre2010matrix}.")


def test_a_source_only_inside_the_maths_is_refused_and_reported():
    """An honest refusal, not a wrong edit. `apply_subs` already reports a
    source it cannot find; a source it can only find inside the maths is the
    same case."""
    missed = []
    text = r"only \(\sqrt[4]{x}\) here"
    out = C.apply_subs(text, [_sub("[4]", r"\cite{z}")],
                       on_missing=lambda s: missed.append(s.source))
    assert out == text
    assert missed == ["[4]"]


@pytest.mark.parametrize("opener,closer", [
    ("\\(", "\\)"), ("$", "$"), ("\\[", "\\]"), ("$$", "$$"),
])
def test_every_span_form_this_projector_writes_counts(opener, closer):
    r"""`$…$`, `$$…$$`, `\(…\)` and `\[…\]` are the four forms the projector
    emits; all four are maths, so all four are off limits."""
    text = "%s a^[2] %s and then [2] again" % (opener, closer)
    out = C.apply_subs(text, [_sub("[2]", r"\cite{q}")])
    assert "a^[2]" in out
    assert r"then \cite{q} again" in out


def test_ordinary_prose_brackets_are_still_substituted():
    """The rule must not cost a citation that was never in any maths."""
    out = C.apply_subs(r"normal [14] and Boolean [19] algebras",
                       [_sub("[14]", r"\cite{a}"), _sub("[19]", r"\cite{b}")])
    assert out == r"normal \cite{a} and Boolean \cite{b} algebras"


def test_a_bare_digit_is_still_judged_by_its_context():
    """The older guard is untouched: a bare digit needs a citation opener
    before it, so the `1` inside a word is not a citation. Both refusals now
    run in one loop, and this is the half that was already there."""
    out = C.apply_subs("Stein1970 said [1] later",
                       [_sub("1", r"\cite{Stein1970}")])
    assert "Stein1970" in out
    assert r"[\cite{Stein1970}]" in out


def test_a_source_straddling_a_span_boundary_is_not_inside_it():
    r"""Containment, not overlap. A source that begins in the maths and ends
    outside it is a text that has MOVED, which `apply_subs` reports rather
    than edits -- the same judgement it already makes for a source it cannot
    find at all."""
    assert C._inside_math([(0, 10)], 2, 8) is True
    assert C._inside_math([(0, 10)], 8, 14) is False
    assert C._inside_math([], 0, 3) is False


def test_the_span_ranges_are_computed_once_per_text():
    """`_math_ranges` is the whole state the rule needs, so it is a plain
    function of the text and the test can state what it returns."""
    text = r"a \(x\) b $y$ c"
    assert C._math_ranges(text) == [(2, 7), (10, 13)]
