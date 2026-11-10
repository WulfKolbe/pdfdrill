r"""Defect 221, narrowed: a dropped glyph costs its own rows, never the document.

THE OWNER'S DECISION, 2026-11-03, verbatim: "my anser s clear, never reject a
whole document but indicate the errors found and go on."

What 221 did until now: `residuals --measure` checked the previous build's log,
and if xelatex had discarded ANY character it renamed the whole measurement to
`report.ink.json.REFUSED`. The reasoning was sound as far as it went -- the
residual compares RENDERED ink against SCANNED ink, and a glyph the engine
threw away is missing from the render and present in the scan, which reads as
an extraction defect when the defect is a missing font. But the price was the
whole document: measured over the T-0116 tranches, 12 refused documents
withheld 1,651 sound rows, 6 of them for exactly ONE dropped character, and
`1306.1660` and `1306.1660v1` -- two library folders holding one document --
were refused twice for the same glyph. A re-run repeated the refusal at full
cost, so the rows could never come back.

ATTRIBUTION, and why it is not simply "the code point". The log names the
character and the font:

    Missing character: There is no ১ (U+09E7) in font DejaVu Serif/OT:...
    Missing character: There is no g ("67) in font rsfs10!

The first is a Unicode coverage gap: only a row CONTAINING U+09E7 can have
dropped it. The second is the measured real case (0707.4470) and inverts the
rule -- `g` is ASCII, and every row with a lowercase g contains it. What is
missing there is not a code point but a LETTER OF A TeX MATH ALPHABET: rsfs10
(`\mathscr`) has no lowercase at all. So a row is only implicated when it both
contains the character AND selects that alphabet.

Where neither rule reaches a row, nothing is quarantined and the loss is still
REPORTED -- "indicate the errors found" is half the instruction and the half
that is easy to lose. A row that disappears quietly is the failure family this
group hit three times in one day: a flag accepted and ignored, a reader
silently dropping a tier, and a page count of zero believed.
"""
import pytest

from pdfdrill import report_tex as rt

#: A Unicode coverage gap: the character is not in the font at all.
BENGALI_ONE = ("Missing character: There is no ১ (U+09E7) in font "
               "DejaVu Serif/OT:script=latn;\n")
#: A TeX math ALPHABET gap: ASCII `g`, absent from \mathscr's alphabet.
RSFS_G = 'Missing character: There is no g ("67) in font rsfs10!\n'


def test_the_log_is_parsed_into_losses_not_just_counted():
    """`glyphs_dropped` returns (count, first message). Narrowing needs every
    loss, each with the font, because the font decides which rule applies."""
    losses = rt.glyph_losses(BENGALI_ONE + RSFS_G)
    assert len(losses) == 2
    assert losses[0]["code_point"] == 0x09E7
    assert losses[0]["char"] == "১"
    assert "DejaVu" in losses[0]["font"]
    assert losses[1]["code_point"] == 0x67
    assert losses[1]["font"].startswith("rsfs")
    assert losses[1]["alphabet"] is True      # a TeX math alphabet, not coverage
    assert losses[0]["alphabet"] is False


def test_a_coverage_gap_quarantines_only_the_rows_holding_that_character():
    rows = {"D_EQ0001": r"x = \text{১} + 1",
            "D_EQ0002": r"y = 2",
            "D_EQ0003": "z = ১"}
    q = rt.quarantine_rows(BENGALI_ONE, rows)
    assert set(q) == {"D_EQ0001", "D_EQ0003"}
    assert "U+09E7" in q["D_EQ0003"]
    assert "D_EQ0002" not in q


def test_an_alphabet_gap_does_not_quarantine_every_row_with_that_letter():
    r"""The whole point of splitting on the font. `g` is ASCII: without the
    alphabet test this quarantines both rows, which is the old whole-document
    refusal wearing a different hat."""
    rows = {"D_EQ0001": r"\mathscr{g}(x)",       # selects rsfs10 AND has a g
            "D_EQ0002": r"g = mc^2",             # has a g, no \mathscr
            "D_EQ0003": r"\mathscr{A}"}          # \mathscr, no g
    q = rt.quarantine_rows(RSFS_G, rows)
    assert set(q) == {"D_EQ0001"}
    assert "rsfs10" in q["D_EQ0001"]
    assert "mathscr" in q["D_EQ0001"]


def test_a_loss_no_row_explains_quarantines_nothing_and_is_still_reported():
    """A character dropped from a running header or a caption belongs to no
    measured row. Quarantining a row for it would charge a row for a fault it
    does not carry; quarantining the document is what the owner forbade; saying
    nothing is the third mistake."""
    rows = {"D_EQ0001": r"y = 2"}
    q = rt.quarantine_rows(BENGALI_ONE, rows)
    assert q == {}
    note = rt.glyph_loss_summary(BENGALI_ONE, rows)
    assert note["dropped"] == 1
    assert note["quarantined"] == 0
    assert note["unattributed"] == 1
    assert "U+09E7" in note["note"]


def test_the_summary_separates_no_verdict_from_verdict_zero():
    """The DB reader's question. The count must travel with the document, or a
    quarantined row is indistinguishable from a row that measured zero."""
    rows = {"D_EQ0001": "z = ১", "D_EQ0002": "y = 2"}
    note = rt.glyph_loss_summary(BENGALI_ONE, rows)
    assert note["dropped"] == 1
    assert note["quarantined"] == 1
    assert note["rows"] == {"D_EQ0001": note["rows"]["D_EQ0001"]}
    assert "U+09E7" in note["rows"]["D_EQ0001"]


def test_a_clean_log_quarantines_nothing():
    rows = {"D_EQ0001": r"y = 2"}
    assert rt.quarantine_rows("Output written on report.pdf (2 pages)\n", rows) == {}
    assert rt.glyph_loss_summary("", rows)["dropped"] == 0


def test_the_whole_document_refusal_is_no_longer_how_221_is_handled():
    """`ink_measurable` stays -- other callers report the fact -- but it must no
    longer be the only answer available: the narrowing needs a row-level one."""
    assert hasattr(rt, "quarantine_rows")
    assert hasattr(rt, "glyph_loss_summary")
    assert hasattr(rt, "glyph_losses")


# --- the adoption step, which is where the document used to be refused ------

import json


def _ink(tmp_path, rows):
    p = tmp_path / "report.ink.json"
    p.write_text(json.dumps({"rows": rows, "source": "report.compare.tsv"}),
                 encoding="utf-8")
    return p


def test_the_measurement_is_adopted_and_the_faulty_rows_are_marked(tmp_path):
    log = tmp_path / "report.log"
    log.write_text("Output written on report.pdf (2 pages)\n" + BENGALI_ONE,
                   encoding="utf-8")
    ink = _ink(tmp_path, [{"id": "D_EQ0001", "distance": 99},
                          {"id": "D_EQ0002", "distance": 3}])
    kept, note = rt.narrow_glyph_refusal(
        ink, log, {"D_EQ0001": "z = ১", "D_EQ0002": "y = 2"})
    assert kept == ink, "the measurement must still be adopted, not refused"
    assert not (tmp_path / "report.ink.json.REFUSED").exists()
    data = json.loads(ink.read_text(encoding="utf-8"))
    assert data["quarantine"]["dropped"] == 1
    assert data["quarantine"]["quarantined"] == 1
    by_id = {r["id"]: r for r in data["rows"]}
    assert by_id["D_EQ0001"]["quarantined"] is True
    assert "U+09E7" in by_id["D_EQ0001"]["quarantine_reason"]
    assert "quarantined" not in by_id["D_EQ0002"]
    assert by_id["D_EQ0002"]["distance"] == 3, "a sound row keeps its verdict"
    assert "1 row" in note


def test_a_refusal_already_on_disk_comes_back_without_a_rebuild(tmp_path):
    """The 12 documents refused before the narrowing hold 1,651 rows, and 350
    of them are in the current cascade. Re-measuring them costs a full report
    build each -- two of the twelve are 300 MB+ books. The quarantined file IS
    the measurement; it only ever needed annotating."""
    log = tmp_path / "report.log"
    log.write_text(BENGALI_ONE, encoding="utf-8")
    dead = tmp_path / "report.ink.json.REFUSED"
    dead.write_text(json.dumps({"rows": [{"id": "D_EQ0001", "distance": 99},
                                         {"id": "D_EQ0002", "distance": 3}]}),
                    encoding="utf-8")
    kept, note = rt.narrow_glyph_refusal(
        None, log, {"D_EQ0001": "z = ১", "D_EQ0002": "y = 2"},
        blob_dir=tmp_path)
    assert kept is not None and kept.name == "report.ink.json"
    assert not dead.exists(), "the refusal is lifted, not left beside the revival"
    data = json.loads(kept.read_text(encoding="utf-8"))
    assert data["quarantine"]["quarantined"] == 1
    assert {r["id"] for r in data["rows"]} == {"D_EQ0001", "D_EQ0002"}
    assert "revived" in note


def test_a_clean_log_changes_nothing(tmp_path):
    log = tmp_path / "report.log"
    log.write_text("Output written on report.pdf (2 pages)\n", encoding="utf-8")
    ink = _ink(tmp_path, [{"id": "D_EQ0001", "distance": 3}])
    before = ink.read_text(encoding="utf-8")
    kept, note = rt.narrow_glyph_refusal(ink, log, {"D_EQ0001": "y = 2"})
    assert kept == ink and note == ""
    assert ink.read_text(encoding="utf-8") == before


# --- which text was typeset, which is the text the quarantine must test -----

def test_the_text_tested_is_the_text_that_was_typeset(tmp_path):
    r"""A row substituted from a provenance was typeset from
    `latex_<prov>`, not from the model's `latex`. Testing the wrong one
    quarantines the wrong rows: here the dropped ১ is in the MODEL's
    text for EQ0001 and in the READING's text for EQ0002, and a measure build
    rendering `pdf2mmd2` typeset the reading."""
    tid = tmp_path / "d.tiddlers.json"
    tid.write_text(json.dumps([
        {"title": "d_EQ0001", "latex": "a = ১", "latex_pdf2mmd2": "a = 1"},
        {"title": "d_EQ0002", "latex": "b = 2", "latex_pdf2mmd2": "b = ১"},
        {"title": "d_EQ0003", "latex": "c = 3"},
    ]), encoding="utf-8")
    plain = rt.typeset_rows(tid, None)
    assert plain["d_EQ0001"] == "a = ১"
    assert plain["d_EQ0002"] == "b = 2"
    withprov = rt.typeset_rows(tid, "pdf2mmd2")
    assert withprov["d_EQ0001"] == "a = 1"
    assert withprov["d_EQ0002"] == "b = ১"
    assert withprov["d_EQ0003"] == "c = 3", "no candidate — the model's latex stands"
    # and the consequence for the quarantine
    assert set(rt.quarantine_rows(BENGALI_ONE, plain)) == {"d_EQ0001"}
    assert set(rt.quarantine_rows(BENGALI_ONE, withprov)) == {"d_EQ0002"}


# --- the row-level taint (coordinator's review, 2026-11-03) -----------------

def test_an_unattributed_loss_marks_every_row_of_the_document(tmp_path):
    """A document note is not enough, because rows are what gets consumed.

    The cascade pools PER-ROW verdicts and the confirmed set is filtered on
    `distance == 0`. An unattributed loss INFLATES a distance, so an affected
    row is LESS likely to reach 0 — it drops out of the confirmed set silently
    and the drop looks like a reader failure instead of a font gap. A false
    negative in the costume of a measurement.

    This is NOT a quarantine: which rows carry the fault is genuinely unknown,
    and charging a row for a fault it may not carry is the thing the narrowing
    exists to stop. It is a statement that the row's distance is not KNOWN to
    be clean, so a row-level consumer can segregate it without re-reading the
    document.
    """
    log = tmp_path / "report.log"
    log.write_text(BENGALI_ONE, encoding="utf-8")        # in no row below
    ink = _ink(tmp_path, [{"id": "D_EQ0001", "distance": 0},
                          {"id": "D_EQ0002", "distance": 7}])
    kept, note = rt.narrow_glyph_refusal(ink, log, {"D_EQ0001": "a = 1",
                                                    "D_EQ0002": "b = 2"})
    data = json.loads(kept.read_text(encoding="utf-8"))
    assert data["quarantine"]["unattributed"] == 1
    for row in data["rows"]:
        assert row["glyph_loss_unattributed"] is True
        assert "U+09E7" in row["glyph_loss_taint"]
        assert "quarantined" not in row, "a taint is not a quarantine"
    assert data["rows"][0]["distance"] == 0, "the verdict itself is untouched"


def test_a_fully_attributed_loss_taints_no_row(tmp_path):
    """Where every loss is charged to a row, the rest of the document is clean
    and must not be marked — otherwise the taint means nothing."""
    log = tmp_path / "report.log"
    log.write_text(BENGALI_ONE, encoding="utf-8")
    ink = _ink(tmp_path, [{"id": "D_EQ0001", "distance": 99},
                          {"id": "D_EQ0002", "distance": 7}])
    kept, _ = rt.narrow_glyph_refusal(ink, log, {"D_EQ0001": "a = ১",
                                                 "D_EQ0002": "b = 2"})
    data = json.loads(kept.read_text(encoding="utf-8"))
    assert data["quarantine"]["unattributed"] == 0
    by_id = {r["id"]: r for r in data["rows"]}
    assert by_id["D_EQ0001"]["quarantined"] is True
    assert "glyph_loss_unattributed" not in by_id["D_EQ0002"]
    assert "glyph_loss_unattributed" not in by_id["D_EQ0001"]
