"""596 — attribution is per identifier, never per run.

inkdrill established three things that ordinal selection cannot honour: a run
can hold several tables (two adjacent 5-column tables are one run), a table
can span runs of different column counts (one 212-row table crosses a 6- and
a 5-column run), and 608 of 717 documents share a column count between two
tables. 594 measured the consequence: 2501.06662's 18-page full listing
segments into nine runs, the Display-equations rows sit in ordinals 1, 5 and
7, and the search found 3 rows where the manifest named 60.
"""
import re

from pdfdrill import inkmeasure as im


def test_flat_removes_the_wrap():
    """A long bibkey pushes the identifier past the column and pdftotext
    returns it split; plain and -layout both then match nothing."""
    assert im._flat("Introduction_to_Linear\nand_Matrix_EQ0001") == \
        "Introduction_to_Linearand_Matrix_EQ0001"
    assert im._flat("a \t b\n\nc") == "abc"


def test_key_matches_flat_on_a_suffixed_identifier():
    """`X (was)` is one identifier with a space in it; both sides lose it."""
    assert im._key("DOC_EQ0001 (was)") == im._flat("DOC_EQ0001 (was)")
    assert im._key("DOC_EQ0001 (was)") == "DOC_EQ0001(was)"


def test_the_permissive_pattern_is_wide_enough_for_every_row_kind():
    for tok in ("doc_EQ0001", "doc_FO1234", "doc_TAB005", "doc_DIA012",
                "1605.05775_EQ0007", "a-b.c_EQ0001(was)"):
        assert im._IDENT_TOKEN.search(tok), tok


def test_the_manifest_decides_not_the_pattern(monkeypatch, tmp_path):
    """The pattern only has to be wide enough to not miss one; membership in
    the manifest is what makes a token a row."""
    pages = {1: "x DOC_EQ0001 y DOC_FO9999 z", 2: "DOC_EQ0002"}

    def fake(cmd, *a, **k):
        class R: pass
        r = R()
        if cmd[0] == "pdfinfo":
            r.stdout = "Pages:           2\n"
        else:
            r.stdout = pages[int(cmd[cmd.index("-f") + 1])]
        return r
    import subprocess
    monkeypatch.setattr(subprocess, "run", fake)
    j = im.identifier_pages(tmp_path / "report.pdf", ["DOC_EQ0001", "DOC_EQ0002"])
    assert j["missing"] == []
    assert j["by_page"] == {1: ["DOC_EQ0001"], 2: ["DOC_EQ0002"]}
    assert j["pages"] == [1, 2]
    assert "DOC_FO9999" in j["leftover"], "a stray identifier must be printed"


def test_order_comes_from_the_manifest_not_the_page(monkeypatch, tmp_path):
    """Reading order returns the right SET in the wrong SEQUENCE, which
    mispairs every row while the counts look perfect."""
    import subprocess

    def fake(cmd, *a, **k):
        class R: pass
        r = R()
        r.stdout = ("Pages:           1\n" if cmd[0] == "pdfinfo"
                    else "DOC_EQ0009 DOC_EQ0002 DOC_EQ0005")
        return r
    monkeypatch.setattr(subprocess, "run", fake)
    wanted = ["DOC_EQ0002", "DOC_EQ0005", "DOC_EQ0009"]     # manifest order
    j = im.identifier_pages(tmp_path / "report.pdf", wanted)
    assert j["by_page"][1] == wanted, "page order must not win over the manifest"


def test_measure_no_longer_selects_a_table_by_ordinal_or_width():
    import inspect
    src = inspect.getsource(im.measure)
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    assert "table=1" not in code, "ordinal selection must be gone"
    assert "reportpages_json" not in code, "the run lattice must not select"
    # 613 — the TEXT-LAYER join this test was written for is itself
    # superseded. 596 located each identifier by page and still reconciled by
    # COUNTING rows on that page; 604 measured that no count correction can
    # fix a mispairing, and the rect makes the claim positional. What must
    # hold either way: no ordinal, no width, and every row carries the
    # identifier it was paired with.
    assert "rows_manifest" in code, "the rect manifest must be read"
    assert "pair_rows" in code, "the claim must be positional"
    assert 'r["identifier"] = ident' in src, "rows must carry their identifier"
