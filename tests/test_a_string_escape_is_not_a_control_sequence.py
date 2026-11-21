r"""`\n` in a page's prose is two characters the page drew, not a command.

T-0156, the escape class, found by naming the tokens behind a total rather
than the total. 2507.21892v1's 43 errors were ALL "Undefined control
sequence", and all 43 were one token:

    \n x34,  \nTo x4,  \nThe x3,  \nFrom x2

It is not an author macro and not a package. That paper is about model
reasoning and its figures print verbatim transcripts, so the PAGE ITSELF shows

    <think>\nTo answer the question, I need to identify the director …

The reading carries the backslash faithfully; the projector emitted it
unescaped, and LaTeX read `\nTo` as a control sequence. `\n` has no meaning in
LaTeX at all, so a `\n` in prose can only be the two characters drawn.

MEASURED over the eight T-0156 e-prints: 86 occurrences match, every one of
them in 2507.21892v1, none in the other seven. The commands those eight files
really use that begin with `n` are `\nabla`, `\ne`, `\neg`, `\neq`,
`\newtheorem`, `\nobreak`, `\node`, `\not`, `\notin`, `\npar` and `\nu` --
all lowercase after the `n`, so the negative lookahead leaves every one of
them alone, including the two `\nabla` in this very document.

WHAT THIS IS NOT, and the tests below hold the line. It is not a general
backslash escape. Prose here carries the model's own inline LaTeX, which is
why `{ } $ \` are exempt from `escape_prose_specials` and why 24.5% of table
cells hold `\(…\)`; escaping every backslash would turn every `\cite{…}` into
literal text. It also leaves an UNDEFINED AUTHOR MACRO alone on purpose --
the answer to `\gameval` is to emit the author's preamble that defines it
(class B), and escaping it here would hide the error that class B's gate
measures instead of fixing it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

P = pytest.importorskip("docops.projectors.latex_pipeline")

BS = "\\textbackslash{}"


@pytest.mark.parametrize("text,want", [
    (r"a \n b", "a " + BS + "n b"),
    (r"<think>\nTo answer", "<think>" + BS + "nTo answer"),
    (r"\n</answer>", BS + "n</answer>"),
    (r"x\nThe y", "x" + BS + "nThe y"),
    (r"\nFrom the knowledge", BS + "nFrom the knowledge"),
])
def test_a_string_escape_becomes_the_characters_the_page_drew(text, want):
    assert P.escape_prose_specials(text) == want


#: Every command beginning with `n` that the eight T-0156 e-prints actually
#: use, taken from their projections rather than from memory.
N_COMMANDS = ["nabla", "ne", "neg", "neq", "newtheorem", "nobreak", "node",
              "not", "notin", "npar", "nu",
              # and the kernel ones a projection is most likely to emit
              "newline", "newpage", "noindent", "nonumber", "null"]


@pytest.mark.parametrize("cmd", N_COMMANDS)
def test_a_real_command_starting_with_n_is_untouched(cmd):
    r"""The negative lookahead IS the rule: a LaTeX command beginning with `n`
    always continues in lowercase."""
    text = "before \\%s after" % cmd
    assert P.escape_prose_specials(text) == text


@pytest.mark.parametrize("text", [
    r"see \cite{foo}",
    r"and \(a_1\) inline",
    r"\emph{stressed} and \textbf{bold}",
    r"\begin{tabular}{l}",
    r"\ref{sec:one} and \label{sec:one}",
])
def test_the_models_own_inline_latex_still_passes_through(text):
    r"""The exempt set stays exempt. A general backslash escape would make
    every one of these literal text, which is why this rule is one token."""
    assert P.escape_prose_specials(text) == text


@pytest.mark.parametrize("text", [r"a \t{oo} b", r"a \r{a} b"])
def test_the_other_c_escapes_are_left_alone_because_they_are_accents(text):
    r"""`\t{oo}` is the tie accent and `\r{a}` the ring. The argument that
    makes `\n` unambiguous does not reach them, and guessing would cost a
    character the author wrote."""
    assert P.escape_prose_specials(text) == text


def test_a_maths_span_is_not_touched():
    """`escape_prose_specials` splits on maths spans and only escapes the text
    between them; that is what keeps subscripts and alignment alive."""
    assert P.escape_prose_specials(r"text $a \n b$ text") == r"text $a \n b$ text"


def test_escaping_twice_does_not_double_it():
    r"""Not idempotent by lookbehind here but by construction: after the
    first pass there is no `\n` left to match, because the `n` of
    `\textbackslash{}n` is preceded by `}`, not by a backslash."""
    once = P.escape_prose_specials(r"<think>\nTo")
    assert P.escape_prose_specials(once) == once


def test_the_glyph_reader_escapes_every_backslash_already():
    r"""The board's own `.glyphs.tex` comes from `pdfreader.project_mmd`, a
    different module with a different contract: it emits a GLYPH at a time, so
    it escapes the whole special set including the backslash. This rule must
    not be read as a second escaper for that path -- checked here so the two
    cannot be confused.
    """
    mmd = pytest.importorskip("pdfreader.project_mmd")
    assert mmd._TEX_SPECIAL["\\"] == BS
    for ch in ("{", "}", "$", "&", "#", "_", "%"):
        assert ch in mmd._TEX_SPECIAL
