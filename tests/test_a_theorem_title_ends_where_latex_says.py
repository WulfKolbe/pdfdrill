r"""A theorem's bracket title ends at the first `]` AT BRACE DEPTH ZERO.

T-0156. The scanner was `re.match(r"\s*\[([^\]]*)\]", inner)`, which stops at
the first `]` whatever encloses it. arxiv.2402.03975 writes

    \begin{theorem}[{e.g., \cite[Section~2.2]{generic_uniqueness}}]

braced exactly as LaTeX requires, and the old scanner cut the title at the `]`
belonging to `\cite[Section~2.2]`. It stored

    title: '{e.g., \cite[Section 2.2'

and spilled `{generic_uniqueness}}]` into the statement. The projector then
appended the theorem's `\label` to that truncated head, placing it INSIDE the
broken title and between a `\cite`'s optional argument and its key:

    \begin{theorem}[{e.g., \cite[Section 2.2]
    \label{ergodic_solvability}
    {{generic\_uniqueness}}] The ergodic equation has a solution ...

So the label never executed. FIVE labels stood in the .tex and NONE of them
reached the .aux — invisible for as long as the references to them were
flattened to text, and 12 "Reference undefined" warnings the moment this task
promoted them to `\ref`. A reference that resolves is only as good as the
label it resolves to.
"""
import pytest

from pdfdrill.latex_source import _optional_arg


@pytest.mark.parametrize("text,want,end", [
    ("[plain title]rest", "plain title", 13),
    ("  [spaced]rest", "spaced", 10),
    (r"[\cite{a,b}]rest", r"\cite{a,b}", 12),
    # LaTeX's own rule: depth 0 wins, so the first `]` ends it
    ("[a]b]c", "a", 3),
])
def test_the_argument_ends_where_latex_ends_it(text, want, end):
    assert _optional_arg(text) == (want, end)


def test_a_bracket_inside_braces_does_not_end_the_argument():
    text = r"[{e.g., \cite[Section~2.2]{generic_uniqueness}}]rest"
    got, end = _optional_arg(text)
    assert got == r"{e.g., \cite[Section~2.2]{generic_uniqueness}}"
    assert text[end:] == "rest"


def test_the_theorem_title_that_lost_five_labels():
    """The whole title survives, so the label lands after a complete head."""
    got, _ = _optional_arg(r"[{e.g., \cite[Section~2.2]{generic_uniqueness}}]")
    assert "generic_uniqueness" in got
    assert got.count("{") == got.count("}")


@pytest.mark.parametrize("text", ["no bracket", "[unterminated", ""])
def test_no_argument_is_reported_as_none(text):
    assert _optional_arg(text) is None


def test_nested_brackets_several_deep():
    got, _ = _optional_arg(r"[{a \cite[x]{y} b \ref[z]{w} c}]")
    assert got == r"{a \cite[x]{y} b \ref[z]{w} c}"


def test_an_escaped_bracket_does_not_end_the_argument():
    got, _ = _optional_arg(r"[a \] b]")
    assert got == r"a \] b"


def test_the_extractor_keeps_the_whole_title():
    """End to end through the theorem extractor, not just the scanner."""
    from pdfdrill.latex_source import extract_theorems
    src = (r"\begin{theorem}[{e.g., \cite[Section~2.2]{generic_uniqueness}}]"
           "\n" r"\label{ergodic_solvability}" "\n"
           r"The ergodic equation has a solution." "\n"
           r"\end{theorem}")
    got = extract_theorems(src, ["theorem"], [])
    thms = got["theorems"] if isinstance(got, dict) else got
    assert thms, "no theorem extracted"
    t = thms[0]
    assert "generic_uniqueness" in t["bracket_title"], t["bracket_title"]
    assert t["label"] == "ergodic_solvability", t["label"]
    # and the key did not spill into the statement
    assert "generic_uniqueness" not in t["statement"], t["statement"]
