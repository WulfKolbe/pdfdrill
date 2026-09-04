"""616A — \\( … \\) inside a listing body, and the guard that stops one row.

MathPix emits listings with [mathescape=true] and then writes the inline
maths as \\(…\\), which listings' mathescape does not read — it reads $.
Measured over 1,369 documents: 464 rows carry an lstlisting and 407 of them
(88%) contain \\(, so this is the common case.
"""
from pdfdrill.report_tex import listing_cell


def test_a_body_with_no_maths_is_plain_monospace():
    out = listing_cell("for each edge do")
    assert out.startswith("{\\ttfamily\\tiny ")
    assert "$" not in out


def test_a_paren_span_is_set_as_maths():
    out = listing_cell(r"for \(e\) do")
    assert "$e$" in out, out
    assert "\\textbackslash{}(" not in out, "the delimiter must not survive as text"


def test_several_spans_and_the_text_between_them_survive():
    out = listing_cell(r"\(a\) then \(b\) end")
    assert "$a$" in out and "$b$" in out
    assert "then" in out and "end" in out


def test_a_body_containing_a_dollar_is_left_entirely_alone():
    """The guard. In listings with mathescape the $ IS the delimiter, so a
    body carrying one is already escaping and substituting around it would
    leave the escape unbalanced. Exactly one row corpus-wide is in this
    state — the Geothermal handbook's DIA_0021, `Cp(Brine\\$,T=...)`."""
    body = r"q = Cp(Brine\$,T=x) and \(y\)"
    out = listing_cell(body)
    assert out.count("$") == out.count("\\$"), "no bare $ may be introduced"
    assert "$y$" not in out, "the guard must suppress the substitution"


def test_maths_renderable_refuses_falls_back_to_the_delimiter_as_text():
    """`renderable` refuses what xelatex would choke on structurally — a bare
    `&` at brace depth 0 ends a cell. An undefined macro is NOT refused: it
    passes through and the compile fixpoint demotes the row if it errors,
    which is the same risk every maths cell already carries."""
    out = listing_cell(r"x \(a & b\) y")
    assert "$" not in out, out
    assert "textbackslash{}(" in out, "the refused span stays as text"


def test_the_limit_is_applied_before_anything_else():
    out = listing_cell("a" * 5000)
    assert len(out) < 2000


def test_an_empty_body_is_an_empty_cell():
    assert listing_cell("") == ""
    assert listing_cell(None) == ""
