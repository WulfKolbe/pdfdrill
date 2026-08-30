"""369 — the DaTikZ report says what it measures, and keeps saying it.

282 established the pattern: a caveat that a reader needs in order to read the
number correctly belongs ON THE PAGE, and a test holds it there. This report is
the case that most needs one — it looks exactly like every other report in the
project, six columns with the same header and legend, but it is not comparing a
reading against a page. Both image columns are renders of the same code.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))


def _caveat():
    from datikz_report369 import CAVEAT
    return CAVEAT


def test_the_caveat_stays_on_the_page():
    """Without it a reader takes our font substitutions for OCR defects."""
    c = _caveat()
    assert "RENDERS OF THE" in c and "SAME CODE" in c
    assert "never a transcription" in c
    assert "FLOOR" in c
    assert "not a reading" in c


def test_the_caveat_explains_the_empty_confidence_column():
    """252 — absent and zero must read differently, and the page must say
    which this is, or an empty square reads as a measurement of zero."""
    c = _caveat()
    assert "no confidence value" in c
    assert "252" in c
    assert "dash" in c


def test_the_caveat_says_page_is_not_a_page():
    """A column headed Page that holds something else is worse than no column."""
    c = _caveat()
    assert "not a page" in c
    assert "shard" in c


def test_the_two_image_columns_are_equal_width():
    """340 — a width difference between the columns being compared puts a
    scale difference into the residual, which is the number this report
    exists to produce."""
    from datikz_report369 import widths
    w = widths(404)
    assert len(w) == 6
    assert w[4] == w[5], "Rendered and Scan image must be equal: %s" % (w,)


def test_confidence_is_absent_not_invented():
    """The dataset carries no confidence. conf_cell must render a dash."""
    from pdfdrill import report_tex as rt
    assert rt.conf_cell("") == "---"
    assert rt.conf_cell(None) == "---"
    assert rt.conf_cell(0.0) != "---", "zero IS a reading and must not look absent"


def test_the_caveat_records_the_split_and_the_contamination():
    """374 — a reader cannot tell a training row from a held-out one by
    looking at the figure, and neither release page states the overlap."""
    c = _caveat()
    assert "V4 \\emph{train}" in c or "train" in c
    assert "92" in c and "442" in c and "350" in c
    assert "BY PICTURE" in c
    assert "not by document" in c
    assert "Neither release page states this" in c


def test_the_generated_column_is_marked_as_generated():
    """375 — the summary column must never read as measured. The caveat says
    so and every cell carries a coloured tag, because a reader scanning one
    row cannot be assumed to have read a header note."""
    c = _caveat()
    assert "GENERATED" in c
    assert "not measured" in c
    assert "reading aid" in c
    assert "reachable through the link" in c


def test_the_figure_identifier_pattern_does_not_touch_the_eq_one():
    r"""386 — DTZ rows carry neither half of inkconvert's EQ contract: the
    identifier is DTZ00000, not <bib>_EQ0001, and the Page cell holds
    "shard 00 / row 0" rather than a bare number. A second pattern was added
    for them.

    The risk in adding it is not that it fails — it is that it fires on a
    document the EQ pattern already handles and silently RE-PAIRS the eleven
    published reports, whose alignment out/237 verified 64 of 64 at offset
    zero. So the fallback is all-or-nothing: it runs only when the EQ pattern
    matched NOTHING at all.
    """
    from pdfdrill import inkconvert as ic
    eq = (r"\ident{doc\allowbreak{}_EQ0001} & 12 & x & y \\ \hline" "\n"
          r"\ident{doc\allowbreak{}_EQ0002} & 13 & x & y \\ \hline")
    assert ic.identifiers(eq) == ["doc_EQ0001", "doc_EQ0002"]

    fig = (r"\ident{DTZ00000}\newline{\tiny f} & {\tiny shard 00} & --- \\" "\n"
           r"\ident{DTZ00001}\newline{\tiny f} & {\tiny shard 01} & --- \\")
    assert ic.identifiers(fig) == ["DTZ00000", "DTZ00001"]

    # A document holding BOTH must be read by the EQ pattern alone: one
    # matching EQ row is enough to keep the figure pattern out entirely.
    both = eq + "\n" + fig
    assert ic.identifiers(both) == ["doc_EQ0001", "doc_EQ0002"]


def test_the_report_states_it_has_no_residual_until_it_has_one():
    """386 — the report is built twice and the first build has no ink.

    An absent measurement must not be dressed as a measured one, so the form
    preamble, the bullets and the residual legend switch together on the
    presence of report.ink.json. This asserts the no-ink build still carries
    the legend that says so, which is what 252 requires of an absent reading.
    """
    from pdfdrill import report_tex as rt
    no_ink = rt.table_open("Rows", (20, 22, 13, 91, 106, 106), False, True)
    assert "no residual" in no_ink.lower()
    assert "\\inkbullet" not in no_ink
