r"""A label or citation name is not prose, so the prose escaper leaves it alone.

T-0156, the owner's third and fifth requirements. `escape_prose_specials`
escapes `_` wherever it stands, and 822 gives the measured reason: prose holds
CODE IDENTIFIERS (`read_inc`, `all_less_than`) and a bare `_` there is
"Missing $ inserted" whatever we do. But a reference or citation standing in
prose had its ARGUMENT escaped with it, and an escaped name is a different
name:

    \label{main_algo}      emitted unescaped, from the object's own prop
    \cref{main\_algo}      escaped, because it stood in prose

MEASURED on arxiv.2402.03975: 89 distinct citation keys against 89
`\bibitem`s.

    23 keys carried an escaped underscore   ->  0 of them matched a bibitem
                                            -> 23 of them match once unescaped
    66 keys carried none                    -> 65 of them matched

So the escaping was the only systematic citation failure on that document, and
it broke 26% of its bibliography. Plus two references, `\cref{main\_algo}` and
`\cref{conditioned\_discount}`.

THE EXPOSURE IS WIDER THAN THE EIGHT: across 2,731 library source documents,
95,184 of 723,939 reference and label arguments (13%) hold an underscore in
the name, in 1,250 documents (46%), and 7% of citation keys do. Only 25
arguments bit at the time because so few references survived into prose at all
(33 of 590) — which is why this was fixed BEFORE class F promotes 115 more.

Same family as the citation placed inside a maths span: a prose rule reaching
into a command's argument.
"""
import pytest

from docops.projectors.latex_pipeline import escape_prose_specials


@pytest.mark.parametrize("cmd", [
    "label", "ref", "eqref", "autoref", "cref", "Cref", "labelcref",
    "pageref", "vref", "nameref", "cite", "citep", "citet", "citeauthor",
    "citeyear", "nocite", "bibitem",
])
def test_the_name_survives_for_every_command_that_takes_one(cmd):
    out = escape_prose_specials("see \\%s{main_algo} there" % cmd)
    assert "\\%s{main_algo}" % cmd in out, out
    assert "main\\_algo" not in out


def test_the_citation_keys_that_broke_a_bibliography():
    for key in ("generic_uniqueness", "shapley_stochastic",
                "conditioned_discount", "main_algo"):
        out = escape_prose_specials(r"as \cite{%s} shows" % key)
        assert key in out and "\\_" not in out, out


def test_a_code_identifier_in_prose_is_still_escaped():
    # 822's reason for escaping `_` at all, and it must not be lost
    out = escape_prose_specials("the function read_inc returns")
    assert "read\\_inc" in out, out


def test_prose_around_a_name_is_still_escaped():
    out = escape_prose_specials(r"R&D on \cite{foo_bar} cost 50% of x_y")
    assert r"\cite{foo_bar}" in out
    assert "R\\&D" in out
    assert "50\\%" in out
    assert "x\\_y" in out


def test_an_optional_argument_does_not_break_the_name():
    out = escape_prose_specials(r"see \cite[p.~5]{foo_bar}")
    assert r"\cite[p.~5]{foo_bar}" in out, out


def test_several_names_on_one_line():
    out = escape_prose_specials(
        r"\cref{a_b} then \cite{c_d} and finally \label{e_f}")
    for name in ("a_b", "c_d", "e_f"):
        assert "{%s}" % name in out, (name, out)
    assert "\\_" not in out


def test_a_name_beside_a_maths_span():
    out = escape_prose_specials(r"\cref{a_b} gives $x_y$ for all i_j")
    assert r"\cref{a_b}" in out
    assert "$x_y$" in out          # maths is left alone, as before
    assert "i\\_j" in out          # prose is not


def test_a_command_that_merely_looks_like_one_is_not_protected():
    # `\references` is not `\ref`: a prefix match would protect anything
    out = escape_prose_specials(r"\references{a_b}")
    assert "a\\_b" in out, out


def test_a_brace_inside_a_name_argument_is_not_matched():
    # `_NAME_ARG` takes `[^{}]*` so a nested group cannot swallow the document
    out = escape_prose_specials(r"\cite{a_b} and {a_group} after")
    assert r"\cite{a_b}" in out
    assert "a\\_group" in out, out


def test_the_string_escape_still_applies_outside_a_name():
    out = escape_prose_specials(r"a \n sequence beside \cite{x_y}")
    assert r"\textbackslash{}n" in out
    assert r"\cite{x_y}" in out


def test_text_with_no_name_is_unchanged_in_behaviour():
    assert escape_prose_specials("plain x_y and 50%") == \
        "plain x\\_y and 50\\%"
