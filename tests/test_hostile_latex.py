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


def test_extract_graphics_baseline_is_one_of_three():
    """MEASURED, 2026-08-30. _GRAPHIC_ENVS is a \\begin/\\end list, so the two
    INLINE forms are not failing to parse -- they are never looked for, and
    nothing reports a missing diagram. Raise this to 3 in 350."""
    _, body = _split()
    got = ls.extract_graphics(body)
    assert len(got) == 1
    assert got[0]["env"] == "tikzpicture"
    assert "circle (1)" in got[0]["code"]
    assert not any("baseline" in g["code"] for g in got), "inline braced form"
    assert not any("(0,1)" in g["code"] for g in got), "inline semicolon form"


def test_an_inputed_tikzpicture_is_invisible_until_inputs_are_expanded():
    """Not a defect in extract_graphics -- a constraint on its caller. Stated
    here because 332 lost 17 compiles to exactly this, an extractor reading the
    root file alone."""
    _, body = _split()
    assert not any("(1,1)" in g["code"] for g in ls.extract_graphics(body))
    whole = ls.expand_inputs(str(MAIN), str(FIX))
    after = ls.extract_graphics(whole.split("\\begin{document}", 1)[1])
    assert any("(1,1)" in g["code"] for g in after)
    assert len(after) == 2


def test_a_custom_environment_is_neither_macro_nor_graphic():
    """\\newenvironment{authorbox} defines something the document uses and
    neither collector claims. Recorded so the number 4 is not read as
    'everything the preamble declares'."""
    pre, body = _split()
    assert "\\newenvironment{authorbox}" in pre
    assert "authorbox" not in ls.collect_macros(pre, str(FIX))
    assert not any("authorbox" in g["code"] for g in ls.extract_graphics(body))
