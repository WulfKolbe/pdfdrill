r"""An equation carries the number the page prints.

T-0156, the owner's fourth requirement. THE NUMBER WAS ALREADY IN THE MODEL:
`docmodel/modules/equation.py` holds `number_bands`, `absorbed_equation_number`
and `normalize_equation_number`, and an Equation's props carry `refnum`. 78 of
the 82 reading-built equations across the audit's eight e-prints have one, and
0 of the 172 source-built ones, where LaTeX generates the number itself. So
nothing here pairs anything: the pairing exists and this emits it.

WHAT `\tag` PRINTS, verified by compiling rather than read off the manual:

    \begin{equation} a=b \end{equation}   ->  (1)    LaTeX's own counter
    c=d\tag{7}                            ->  (7)    amsmath parenthesises it
    e=f\tag{3.2}                          ->  (3.2)
    g=h\tag*{9}                           ->  9      no parentheses

so the value goes in bare and `\tag{N}` reproduces the page's `(N)`.

THE VALUE IS ESCAPED, because a printed number is not always a number.
Measured over 8,854 equation refnums in the library: 53% plain digits, 19%
`n.m`, 10% `A.1`, and 19% something else — `4a`, `3.8b`, `3.18/16`, `*`. One
holding `_`, `%` or `&` would end the compile.

AND A BODY THAT ALREADY CARRIES A TAG IS LEFT ALONE: the author's own
`\tag*{(\ref{th:shapley})}` survives into the projection, and a second tag in
one display is "Multiple \tag" — an error where there was none.
"""
import re

import pytest

from docmodel import DocObject, Document
from docops.base import OperatorConfig
from docops.projectors.latex import LaTeXProjector


def _project(*propsets):
    doc = Document()
    for i, props in enumerate(propsets):
        p = dict(props)
        p["flow_index"] = i
        doc.add(DocObject(type="Equation", props=p))
    return LaTeXProjector(OperatorConfig(
        op="projector", classname="LaTeXProjector")).project(doc)


def _tags(tex):
    return re.findall(r"\\tag\*?\{([^}]*)\}", tex)


def test_the_printed_number_becomes_a_tag():
    assert _tags(_project({"latex": "a = b", "refnum": "7"})) == ["7"]


def test_an_equation_without_a_number_gets_no_tag():
    assert _tags(_project({"latex": "a = b"})) == []
    assert _tags(_project({"latex": "a = b", "refnum": ""})) == []
    assert _tags(_project({"latex": "a = b", "refnum": "   "})) == []


@pytest.mark.parametrize("refnum", ["7", "3.2", "4a", "3.8b", "A.1",
                                    "3.18/16", "12"])
def test_every_measured_refnum_shape_reaches_the_tag(refnum):
    """The shapes the library census found AND that are numbers.

    `*` is in that census too and is deliberately absent here: it is a value
    `refnum` holds, not a number a page prints, and the shape guard refuses
    it. A census tells you what the data contains, not what the data means.
    """
    assert _tags(_project({"latex": "a = b", "refnum": refnum})) == [refnum]


@pytest.mark.parametrize("refnum", ["2_3", "5%", "x&y", "a#b"])
def test_a_special_in_the_number_is_refused_not_escaped(refnum):
    r"""`_`, `%`, `&` and `#` would end the compile unescaped — and a printed
    equation number contains none of them, so the shape guard REFUSES the
    value rather than escaping it. The escape stays as a second layer for
    whatever passes the guard (see `test_the_escape_remains_as_a_second_
    layer`), but nothing that reaches it needs escaping today.

    An earlier version of this test asserted the escaped form was emitted.
    The guard is stricter and it is the right answer: a refnum holding `%` is
    not a number we should print beside an equation.
    """
    assert _tags(_project({"latex": "a = b", "refnum": refnum})) == []


def test_the_escape_remains_as_a_second_layer():
    """Defence in depth: everything the guard admits is already safe, so the
    escaper is a no-op on it — which is the property worth pinning, because
    it is what makes widening the guard safe later."""
    from docops.projectors.latex_pipeline import (escape_prose_specials,
                                                  looks_like_a_printed_number)
    for v in ["7", "3.2", "4a", "A.1", "3.18/16", "3.9 /7", "3.26-27 /24-25"]:
        assert looks_like_a_printed_number(v)
        assert escape_prose_specials(v) == v, v


def test_a_body_that_already_has_a_tag_gets_no_second_one():
    tex = _project({"latex": r"a = b\tag*{(mine)}", "refnum": "9"})
    assert _tags(tex) == ["(mine)"], _tags(tex)
    assert tex.count("\\tag") == 1


def test_the_tag_is_inside_the_equation_environment():
    """amsmath refuses `\\tag` outside a numbered display — the author's four
    misplaced ones on arxiv.2402.03975 are exactly that error."""
    tex = _project({"latex": "a = b", "refnum": "7"})
    m = re.search(r"\\begin\{equation\}(.*?)\\end\{equation\}", tex, re.S)
    assert m, tex
    assert "\\tag{7}" in m.group(1)


def test_the_backslash_spelling_mathpix_sometimes_yields_is_stripped():
    # `common.equation_label`'s own comment: refnums arrive like `\1.1\`
    assert _tags(_project({"latex": "a = b", "refnum": "\\1.1\\"})) == ["1.1"]


def test_several_equations_each_keep_their_own_number():
    tex = _project({"latex": "a = b", "refnum": "1"},
                   {"latex": "c = d", "refnum": "2"},
                   {"latex": "e = f"},
                   {"latex": "g = h", "refnum": "4"})
    assert _tags(tex) == ["1", "2", "4"]


def test_a_tag_and_a_label_say_different_things():
    r"""The number is the TAG; the name is the LABEL.

    This test was written in the previous step to RECORD the state that step
    would leave behind — the refnum emitted as `\label{7}`, a number used as
    an identifier — and it failed the moment that changed, which is what it
    was for. The label is now `eq:7`
    (`test_an_equation_has_a_name_not_a_number` holds the scheme).
    """
    tex = _project({"latex": "a = b", "refnum": "7"})
    assert "\\tag{7}" in tex
    assert "\\label{eq:7}" in tex
    assert "\\label{7}" not in tex


def test_the_tag_survives_a_transcluded_body():
    """The body may be `\\EqExpr{i}` from the readarray array rather than the
    latex itself; the tag goes beside it either way."""
    tex = _project({"latex": "a = b", "refnum": "7"})
    m = re.search(r"\\begin\{equation\}(.*?)\\end\{equation\}", tex, re.S)
    body = m.group(1)
    assert ("\\EqExpr{" in body) or ("a = b" in body)
    assert "\\tag{7}" in body


# ------------------------------------------ a printed number, or nothing

r"""`refnum` DOES NOT ALWAYS HOLD A NUMBER.

Over 8,854 equation refnums in the library, 54 carry a LaTeX special or a
backslash, and the values show what they really are — a whole mis-parsed
expression written into a number field:

    left7^{*}right
    psi=left[begin{array}{c}nu  e  u^{r} … end{array}right]
    mathrm{A}-mathrm{C}
    3 cdot 4        by Eq. 13        *        {

As `\tag{…}` each prints a mis-parsed expression in the equation's margin:
output that compiles, renders, and is visibly wrong — and `equation_label`
strips the backslashes, so it reads as text rather than as broken LaTeX. The
eight audit e-prints cannot show this; all 78 of their refnums are digits.
"""

from docops.projectors.latex_pipeline import looks_like_a_printed_number


@pytest.mark.parametrize("value", [
    "7", "12", "3.2", "4a", "3.8b", "A.1", "B.2.3", "3.18/16",
    "3.9 /7",            # a compound printed number, with a space
    "3.26-27 /24-25",    # and another — the first rule I wrote threw these away
    "(12)",
])
def test_a_printed_number_is_kept(value):
    assert looks_like_a_printed_number(value), value


@pytest.mark.parametrize("value", [
    "*", "{", "a", "", "   ",
    "by Eq. 13",                    # a sentence, not a number
    "3 cdot 4",                     # a product, mis-parsed
    "left7^{*}right",
    "mathrm{A}-mathrm{C}",
    "psi=left[begin{array}{c}nu  e  u^{r}end{array}right]",
])
def test_mathematics_in_the_number_field_is_refused(value):
    assert not looks_like_a_printed_number(value), value


def test_a_token_without_a_digit_is_not_part_of_a_number():
    """The property that does the work: `cdot` and `by` carry no digit."""
    assert not looks_like_a_printed_number("3 cdot 4")
    assert not looks_like_a_printed_number("by Eq. 13")
    assert looks_like_a_printed_number("3 4")       # two numbers, both digits


def test_a_long_value_is_refused_whatever_it_contains():
    assert not looks_like_a_printed_number("1." * 11)


def test_the_guard_reaches_the_projection():
    """An equation whose refnum is mathematics gets NO tag."""
    tex = _project({"latex": "a = b", "refnum": "left7^{*}right"})
    assert _tags(tex) == [], _tags(tex)
    tex = _project({"latex": "a = b", "refnum": "3 cdot 4"})
    assert _tags(tex) == []


def test_the_guard_does_not_touch_a_real_number():
    assert _tags(_project({"latex": "a = b", "refnum": "3.8b"})) == ["3.8b"]
