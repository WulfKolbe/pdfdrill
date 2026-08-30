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
    # 3 tikzpicture: the plain one, the margin note's (355), the one wrapping
    # an inclusion (357); plus the 2 inline forms this test is named for
    assert len(got) == 5
    assert [g["env"] for g in got].count("tikzpicture") == 3
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
    assert len(after) == 6   # +1 again: the \\input'ed tikzpicture
    assert [g["env"] for g in after].count("tikzpicture") == 4


def test_a_custom_environment_is_neither_macro_nor_graphic():
    """\\newenvironment{authorbox} defines something the document uses and
    neither collector claims. Recorded so the number 4 is not read as
    'everything the preamble declares'."""
    pre, body = _split()
    assert "\\newenvironment{authorbox}" in pre
    assert "authorbox" not in ls.collect_macros(pre, str(FIX))
    assert not any("authorbox" in g["code"] for g in ls.extract_graphics(body))


# --- 355: margin material -------------------------------------------------

def test_margin_note_is_brace_matched_and_keeps_its_offset():
    r"""\marginnote[-6cm]{... \begin{tikzpicture}...\end{tikzpicture} ...} is
    the thesis construct. A regex stopping at the first `}` ends the note
    inside the picture and takes the rest of the document as body text."""
    _, body = _split()
    notes = ls.extract_margin_notes(body)
    assert len(notes) == 1
    n = notes[0]
    assert n["cmd"] == "marginnote"
    assert n["offset"] == "-6cm", "the offset says WHERE in the margin"
    assert "tikzpicture" in n["content"]
    assert n["content"].rstrip().endswith("inside."), "truncated at an inner brace"


def test_a_graphic_in_the_margin_is_marked_and_one_in_the_body_is_not():
    """The gap 353 measured: 29 of the thesis's 140 graphics sit inside a
    \marginnote and every one read as a body figure."""
    _, body = _split()
    got = ls.extract_graphics(body)
    spans = ls.margin_spans(body)
    marked = [g for g in got if ls.in_margin(spans, g["pos"])]
    assert len(marked) == 1
    assert "(2,2)" in marked[0]["code"]
    assert len(got) - len(marked) == 4, "the others must stay unmarked"


def test_a_commented_margin_note_is_not_one():
    assert ls.extract_margin_notes("% \\marginnote{x}\n") == []


def test_an_unbalanced_margin_note_is_refused_not_guessed():
    """Better no object than one holding the rest of the file."""
    assert ls.extract_margin_notes("\\marginnote{unclosed") == []


# --- 357: orphan inclusions become Picture objects -------------------------

def test_an_orphan_inclusion_is_found_and_a_covered_one_is_not():
    r"""`extract_graphics` returns BLOCKS, so an \includegraphics standing on
    its own produced nothing at all — no object, no SVG, no report row."""
    _, body = _split()
    orph = ls.orphan_graphics(body)
    files = [o["file"] for o in orph]
    assert "figs/plain" in files, "the bare inclusion is an orphan"
    assert "figs/inner" not in files, "the one inside a tikzpicture is covered"


def test_orphan_positions_are_raw_body_offsets():
    r"""`texgraphics.calls` reports positions in COMMENT-STRIPPED text and
    `extract_graphics` in the raw body. Comparing them directly misclassified
    any inclusion preceded by a comment and would have placed every Picture at
    the wrong point in the flow — 4,610 orphans where the true count is
    4,529."""
    body = ("%" + " a comment long enough to shift every later offset\n"
            + "\\begin{tikzpicture}\\node{\\includegraphics{a}};\\end{tikzpicture}\n"
            + "\\includegraphics{b}\n")
    orph = ls.orphan_graphics(body)
    assert [o["file"] for o in orph] == ["b"]
    pos = orph[0]["pos"]
    assert body[pos:pos + len("\\includegraphics{b}")] == "\\includegraphics{b}"


def test_a_commented_inclusion_is_not_an_orphan():
    assert ls.orphan_graphics("% \\includegraphics{ghost}\n") == []
