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


def _tsv(tmp_path, pages):
    """A compare TSV: pages is {page: [(L, R), ...]} with the footer LAST."""
    head = ("report_page\tline\tdis\tA_eq_B\tL_comp\tL_holes\tL_stk\tL_cen\t"
            "L_off\tR_comp\tR_holes\tR_stk\tR_cen\tR_off\tB_stable")
    out = [head]
    for pg, rows in sorted(pages.items()):
        for i, (L, R) in enumerate(rows):
            out.append("\t".join(str(x) for x in
                                 [pg, i * 2 + 1, 0, "yes"] + L + R + ["yes"]))
    p = tmp_path / "report.compare.tsv"
    p.write_text("\n".join(out) + "\n")
    return p


def test_an_all_zero_data_row_is_not_a_footer(tmp_path, monkeypatch):
    """386 — the footer rule was value-based and should be structural.

    read_tsv calls any all-zero five-tuple pair a footer, on the measured
    coincidence that across the eleven this was exactly the last row of every
    page (1232/1232). DTZ page 25 broke the coincidence: a real data row whose
    Rendered and Scan cells are both empty. Eaten as a footer, it costs a row
    and shifts the tail onto the wrong figures.

    Here the footer is the LAST row of the page. The empty data row survives
    and is classed `absent` — not `clean`, which is what flag_of's first
    branch would have given a distance of zero.
    """
    from pdfdrill import inkconvert as ic
    Z = [0, 0, 0, 0, 0]
    tsv = _tsv(tmp_path, {1: [([5, 2, 1, 1, 0], [5, 2, 1, 1, 0]),
                              (Z, Z),                    # a real EMPTY row
                              ([4, 1, 0, 0, 0], [4, 1, 0, 0, 0]),
                              (Z, Z)]})                  # the footer
    monkeypatch.setattr(ic, "page_identifiers",
                        lambda pdf: {1: ["DTZ00000", "DTZ00001", "DTZ00002"]})
    pay = ic.convert_by_page(tsv, tmp_path / "report.pdf")
    assert [r["id"] for r in pay["rows"]] == ["DTZ00000", "DTZ00001",
                                              "DTZ00002"]
    assert pay["rows"][1]["flag"] == "absent"
    assert pay["footers_dropped"] == 1


def test_a_page_that_lost_a_row_is_dropped_whole_not_truncated(tmp_path,
                                                               monkeypatch):
    """386 — containment. DTZ page 22's lattice lost a row, and whole-document
    zip refuses all 100 rows over 3. Pairing per page keeps the other 33 pages
    and drops the bad one WHOLE: taking the first N would be exactly the
    silent truncation this converter exists to refuse.
    """
    from pdfdrill import inkconvert as ic
    Z = [0, 0, 0, 0, 0]
    tsv = _tsv(tmp_path, {
        1: [([5, 2, 1, 1, 0], [5, 2, 1, 1, 0]), (Z, Z)],       # 1 row, ok
        2: [([9, 3, 2, 1, 1], [9, 3, 2, 1, 1]), (Z, Z)],       # 1 row, 2 ids
    })
    monkeypatch.setattr(ic, "page_identifiers",
                        lambda pdf: {1: ["DTZ00000"],
                                     2: ["DTZ00001", "DTZ00002"]})
    pay = ic.convert_by_page(tsv, tmp_path / "report.pdf")
    assert [r["id"] for r in pay["rows"]] == ["DTZ00000"]
    assert pay["pages_dropped"] == [{"page": 2, "rows": 1, "identifiers": 2,
                                     "ids": ["DTZ00001", "DTZ00002"]}]


def test_the_tables_cell_does_not_cross_reference_a_rare_artefact():
    r"""426 — the empty-LaTeX cell said "see tables.html".

    10,928 rows across 680 documents said it, and tables.html exists in 17 of
    those 680: 97.5% of the pointers dangle. Where it does exist it is
    pdfplumber's keyless extraction of the page, not that row's table
    rendered, so even the 2.5% pointed somewhere other than a reader would
    expect.

    report.pdf is the universal artefact (1,331 documents) and tables.html is
    a rare one (31). A cross-reference in that direction has to dangle.
    """
    import inspect
    from pdfdrill import report_tex as rt
    src = inspect.getsource(rt.build_tex if hasattr(rt, "build_tex") else rt)
    body = src if isinstance(src, str) else ""
    # the CELL must not name it; the comment explaining why may.
    cell_lines = [l for l in body.splitlines()
                  if "no LaTeX source" in l]
    assert cell_lines, "the empty-LaTeX cell text moved; this test needs its anchor"
    for l in cell_lines:
        assert "tables.html" not in l, l.strip()
