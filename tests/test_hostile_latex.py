"""348 — the hostile document, and the baseline it pins.

A fixture that RECORDS WHAT DOES NOT WORK. Every coverage number in this
project has been measured against ~/pdfdrill-library, and a corpus can only
report the constructs it happens to contain: `\\NewDocumentCommand` and `\\let`
are not rare LaTeX, they are simply absent from the documents that were
measured, so collection has looked complete for months while missing two of
six forms.

The assertions below are the CURRENT results, measured, not the desired ones.
Three will change when 350 and 351 land, and each says so. A test that asserts
a gap is the only thing that stops the gap being closed by accident and
reopened by the next corpus.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import latex_source as ls                    # noqa: E402

FIX = pathlib.Path(__file__).resolve().parent / "fixtures" / "hostile_latex"
MAIN = FIX / "main.tex"

#: the six macro forms the fixture defines, one per form
MACROS = ("newcmdMacro", "defMacro", "opMacro", "styleMacro",
          "xparseMacro", "letMacro")
#: which of them collection finds TODAY
HANDLED = {"newcmdMacro", "defMacro", "opMacro", "styleMacro"}
MISSED = {"xparseMacro", "letMacro"}


def _split():
    t = MAIN.read_text(encoding="utf-8")
    pre, body = t.split("\\begin{document}", 1)
    return pre, body


def test_the_fixture_defines_all_six_forms():
    """If a later edit drops a form, the baseline below stops meaning anything."""
    pre, _ = _split()
    assert "\\newcommand{\\newcmdMacro}" in pre
    assert "\\def\\defMacro" in pre
    assert "\\DeclareMathOperator{\\opMacro}" in pre
    assert "\\NewDocumentCommand{\\xparseMacro}" in pre
    assert "\\let\\letMacro" in pre
    assert (FIX / "authorstyle.sty").is_file()
    assert "\\newcommand{\\styleMacro}" in (FIX / "authorstyle.sty").read_text()


def test_collect_macros_baseline_is_four_of_six():
    """MEASURED, 2026-08-30. Raise this to 6 in 351, not before."""
    got = ls.collect_macros(_split()[0], str(FIX))
    found = {m for m in MACROS if m in got}
    assert found == HANDLED, "handled set changed: %s" % sorted(found)
    assert {m for m in MACROS if m not in got} == MISSED
    assert len(found) == 4


def test_a_local_style_file_is_read_but_a_system_package_is_not():
    """The author's own .sty is resolved beside the document; amsmath is not
    on disk here and is skipped rather than failing."""
    got = ls.collect_macros(_split()[0], str(FIX))
    assert "styleMacro" in got
    assert "qed" not in got and "text" not in got


def test_xparse_and_let_macros_pass_through_verbatim():
    """The consequence of the gap, which is worse than a missing key: the call
    survives into the output looking like valid LaTeX no reader will question,
    and nothing reports that a macro went unexpanded."""
    pre, body = _split()
    macros = ls.collect_macros(pre, str(FIX))
    line = next(l for l in body.splitlines() if "xparseMacro" in l)
    out = ls.expand_macros(line, macros)
    assert "\\xparseMacro" in out and "\\letMacro" in out
    assert "\\newcmdMacro" not in out, "the handled form must still expand"


def test_extract_graphics_now_finds_all_three():
    """Was 1 of 3 when this fixture landed (348): _GRAPHIC_ENVS drives a
    \\begin/\\end scan, so the inline forms were never looked for. 352 added
    both, and the count is 3 of 3."""
    _, body = _split()
    got = ls.extract_graphics(body)
    assert len(got) == 3
    assert [g["env"] for g in got].count("tikzpicture") == 1
    assert [g["env"] for g in got].count("tikz") == 2
    assert any("baseline" in g["code"] for g in got), "inline braced form"
    assert any("(0,1)" in g["code"] for g in got), "inline semicolon form"


def test_inline_tikz_takes_the_optional_argument_and_matches_braces():
    """LATW's TikzScanner uses /\\tikz\\s*{([^}]+)}/ — no optional argument,
    and `[^}]+` stops at the first `}`. Both limits are ported OUT."""
    got = ls.extract_graphics(r"\tikz[baseline,scale=2]{\node {a}; \draw (0,0);}")
    assert len(got) == 1
    assert got[0]["code"].endswith("}")
    assert "\\draw (0,0);" in got[0]["code"], "truncated at the inner brace"


def test_a_commented_out_inline_tikz_is_not_a_picture():
    """This fixture's own explanatory comments name both spellings, and were
    detected as two pictures before comments were skipped."""
    got = ls.extract_graphics("% \\tikz{\\draw (0,0);}\n\\tikz{\\draw (1,1);}\n")
    assert len(got) == 1
    assert "(1,1)" in got[0]["code"]


def test_inline_tikz_inside_a_tikzpicture_is_not_a_second_diagram():
    """Otherwise the same ink is reported twice."""
    got = ls.extract_graphics(
        "\\begin{tikzpicture}\n\\tikz \\draw (0,0);\n\\end{tikzpicture}")
    assert len(got) == 1 and got[0]["env"] == "tikzpicture"


def test_tikzset_and_tikzcd_are_not_inline_tikz():
    """`\\tikz` must not match the prefix of a longer control sequence."""
    got = ls.extract_graphics("\\tikzset{every node/.style={draw}}")
    assert not any(g["env"] == "tikz" for g in got)


def test_an_inputed_tikzpicture_is_invisible_until_inputs_are_expanded():
    """Not a defect in extract_graphics -- a constraint on its caller. Stated
    here because 332 lost 17 compiles to exactly this, an extractor reading the
    root file alone."""
    _, body = _split()
    assert not any("(1,1)" in g["code"] for g in ls.extract_graphics(body))
    whole = ls.expand_inputs(str(MAIN), str(FIX))
    after = ls.extract_graphics(whole.split("\\begin{document}", 1)[1])
    assert any("(1,1)" in g["code"] for g in after)
    # 2 tikzpicture (one of them \input'ed) + the 2 inline forms 352 added
    assert len(after) == 4
    assert [g["env"] for g in after].count("tikzpicture") == 2


def test_a_custom_environment_is_neither_macro_nor_graphic():
    """\\newenvironment{authorbox} defines something the document uses and
    neither collector claims. Recorded so the number 4 is not read as
    'everything the preamble declares'."""
    pre, body = _split()
    assert "\\newenvironment{authorbox}" in pre
    assert "authorbox" not in ls.collect_macros(pre, str(FIX))
    assert not any("authorbox" in g["code"] for g in ls.extract_graphics(body))
