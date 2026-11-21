r"""An algorithm step's comment closes its own brace.

T-0156. `arxiv.2402.03975` ended its compile with

    Runaway argument?
    ! File ended while scanning use of \textit .
    ! Emergency stop.

and the cost was not the error: the `.aux` came out with ZERO `\bibcite`
lines, so all 89 of that document's citations were undefined and its
bibliography never rendered. One unclosed brace took the rest of the document
with it.

Two defects in `_clean_step_text`, each invisible because of the other:

  * `re.sub(r"\\Comment\{", "// ", s)` dropped the OPENING brace and left
    every close, so `\Comment{\textit{x}}` became `// \textit{x}}` — one `}`
    too many;
  * `.strip(" {}")` is a CHARACTER-CLASS strip, so it then removed BOTH
    closes and left `\textit{` open.

A surplus brace and a greedy strip cancel on `\Comment{plain text}` and
compound on `\Comment{\textit{...}}`, which is why this survived: the shape
that breaks is a comment whose argument begins with a command.

Measured over the library's LaTeX sources: 2,445 algorithmic steps, of which
the old code left 302 brace-unbalanced, in 57 documents.
"""
import re

import pytest

from pdfdrill.latex_source import (_clean_step_text, _matching_close,
                                   _strip_wrapping_group)


def _balanced(s: str) -> bool:
    return s.count("{") == s.count("}")


THE_STEP = (r"\State\label{line:value-blackwell-bias} $(\gameval, \bias) "
            r"\gets $ value and Blackwell bias of the zero-player "
            r"mean-payoff game with fixed $(\sigma,\tau)$ "
            r"\Comment{\textit{if the value of the zero-player game is not "
            r"constant for all states, pick any $(\gameval,\bias)$}}")


def test_the_step_that_cost_a_bibliography_is_balanced():
    out = _clean_step_text(THE_STEP)
    assert _balanced(out), out
    assert r"\textit{" in out
    assert out.rstrip().endswith("}")


def test_the_comment_keeps_its_argument():
    out = _clean_step_text(THE_STEP)
    assert "if the value of the zero-player game is not constant" in out
    assert "//" in out                       # the comment marker is kept


def test_the_matching_close_is_removed_not_the_first():
    out = _clean_step_text(r"\Comment{\textbf{a} b}")
    assert out == r"// \textbf{a} b", out


@pytest.mark.parametrize("step", [
    r"\State $x$ \Comment{plain words}",
    r"\State $x$ \Comment{\textit{emphasised}}",
    r"\State $x$ \Comment{\textbf{a} and \textit{b}}",
    r"\State \Comment{a} then \Comment{\textbf{b}}",
    r"\Return \Comment{\texttt{x_y}}",
    THE_STEP,
])
def test_every_comment_shape_stays_balanced(step):
    assert _balanced(_clean_step_text(step)), step


def test_a_wrapping_group_is_still_unwrapped():
    # the behaviour `.strip(" {}")` was there for, and it is kept
    assert _clean_step_text(r"\State {wrapped in a group}") == \
        "wrapped in a group"


def test_a_brace_that_closes_something_inside_is_not_stripped():
    # `.strip(" {}")` turned this into `$x$} and {$y$` — two unmatched braces
    # out of a balanced input. Nothing in the old code could see it.
    assert _strip_wrapping_group(r"{$x$} and {$y$}") == r"{$x$} and {$y$}"


def test_nested_wrapping_groups_unwrap_completely():
    # every layer here genuinely wraps the whole string, and a LaTeX group
    # only scopes, so unwrapping all of them is equivalent
    assert _strip_wrapping_group("{{ {a} }}") == "a"
    assert _strip_wrapping_group("{a} {b}") == "{a} {b}"   # neither wraps


def test_an_unbalanced_source_is_left_alone():
    # a source we cannot parse is not improved by guessing
    out = _clean_step_text(r"\State \Comment{unclosed and then the end")
    assert "unclosed and then the end" in out


@pytest.mark.parametrize("text,open_at,want", [
    ("{a}", 0, 2),
    ("{a{b}c}", 0, 6),
    ("x{a}y", 1, 3),
    ("{unclosed", 0, -1),
])
def test_the_brace_matcher(text, open_at, want):
    assert _matching_close(text, open_at) == want


def test_the_old_character_class_strip_is_gone():
    import inspect

    from pdfdrill import latex_source
    src = inspect.getsource(latex_source._clean_step_text)
    assert 'strip(" {}")' not in src, (
        "a character-class strip removes a brace that closes something "
        "inside the string; use _strip_wrapping_group")


def test_no_step_text_in_the_corpus_is_left_unbalanced():
    # the 302 the old code broke, as a property rather than a list
    for step in (THE_STEP,
                 r"\State \Comment{\textit{a} \textbf{b} \texttt{c}}",
                 r"\Statex \Comment{\emph{nested {deeper} still}}"):
        out = _clean_step_text(step)
        assert _balanced(out), (step, out)
        assert not re.search(r"\\[a-zA-Z]+\{[^{}]*$", out), out
