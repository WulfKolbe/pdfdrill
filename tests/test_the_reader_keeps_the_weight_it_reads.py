r"""The reader keeps the weight it already reads.

T-0156, under the owner's rule of 2026-11-22: "think always of possible
improvements at lower levels that might solve problems now covered by some
heuristic. We have now control over all levels of the code even the lowest
level." (PROTOCOL "Fix at the lowest level".)

THREE THINGS WERE THROWN AWAY on the route that reads a PDF's own text layer,
and three heuristics were built on top of the hole:

  * `is_bold`. `_classify_font_family` returns `(base, is_math, is_bold,
    is_italic)`; `chars_to_lines.font_flags` unpacked the third into `_bd` and
    dropped it, per character.
  * THE TEX SPELLING OF BOLD. The classifier tested `"bold" in low or "-bd" in
    low or "medi" in low` — and TeX writes `CMBX10` (Computer Modern Bold
    Extended), `ptmb`, `phvb`. Measured over 40 library documents: 79 bold font
    names use a TeX spelling against 62 that say "Bold", so the test missed
    56% of the bold in a corpus that is mostly LaTeX.
  * THE LINE'S FONT RUNS. `ocr_lines.lines_json_from_words` rebuilt each line
    dict from scratch with five keys — id, type, text, text_display, region —
    so anything the chars route computed stopped there.

What that cost, each measured before this existed: a description-list rule
that could not tell a bold label from a heading and failed at precision 0.50;
`refnum` holding mathematics, guarded at two DISPLAY sites instead of typed at
the source. (The "paragraphs merged 2.6 into one" that first motivated a
block id was a MISCOUNT, retracted: `ParagraphProcessor` honours a DOUBLE
newline in `text_display`, and counted against that marker the model splits
finer than the reading, 1,589 paragraphs to 1,136 markers. The single `\n`
I counted is MathPix's BLOCK marker, which is not a paragraph break -- 8 of
20 sampled were list items, footnotes, a bibliography entry, a title.)

RUNS, NOT ONE FONT PER LINE. A description label is a bold run at the START of
a body line, so the line's dominant font is the body's and a per-line field
would drop exactly the label it is wanted for.
"""
import pytest

from pdfdrill.chars_to_lines import _runs_of, font_run_key
from pdfdrill.font_image_layers import _classify_font_family
from pdfdrill.ocr_lines import _merge_runs


@pytest.mark.parametrize("name", ["CMBX10", "VPYVZL+CMBX10", "CMBX9", "CMBX12",
                                  "CMB10", "ptmb8r", "phvb8t", "pcrb8a",
                                  "Helvetica-Bold", "DejaVuSerif-Bold"])
def test_bold_is_recognised_however_it_is_spelled(name):
    assert _classify_font_family(name)[2] is True, name


@pytest.mark.parametrize("name", ["CMR10", "PPOMIM+CMR10", "CMTI10", "CMCSC10",
                                  "CMTT10", "Times-Roman", "DejaVuSerif",
                                  "Bexley-Regular"])
def test_what_is_not_bold_stays_not_bold(name):
    assert _classify_font_family(name)[2] is False, name


def test_the_run_key_carries_family_size_weight_and_slant():
    assert font_run_key("VPYVZL+CMBX10", 10.0) == ("CMBX10", 10.0, True, False)
    assert font_run_key("CMTI10", 9.0) == ("CMTI10", 9.0, False, True)


def test_consecutive_glyphs_in_one_font_are_one_run():
    chars = [{"t": c, "fr": font_run_key("CMBX10", 10.0)} for c in "declares"]
    runs = _runs_of(chars)
    assert len(runs) == 1
    assert runs[0] == {"start": 0, "family": "CMBX10", "size": 10.0,
                       "bold": True, "italic": False}


def test_a_bold_label_then_body_text_is_two_runs():
    chars = ([{"t": c, "fr": font_run_key("CMBX10", 10.0)} for c in "declares"]
             + [{"t": c, "fr": font_run_key("CMR10", 10.0)} for c in " XML"])
    runs = _runs_of(chars)
    assert [r["start"] for r in runs] == [0, 8]
    assert [r["bold"] for r in runs] == [True, False]


def test_a_run_spanning_two_words_is_merged_once():
    """`declares XML` in one bold face is ONE run of the joined line, not two
    — which is what makes a multi-word label a single label."""
    bold = [{"start": 0, "family": "CMBX10", "size": 10.0,
             "bold": True, "italic": False}]
    body = [{"start": 0, "family": "CMR10", "size": 10.0,
             "bold": False, "italic": False}]
    ws = [{"text": "declares", "runs": bold},
          {"text": "XML", "runs": bold},
          {"text": "entities", "runs": body}]
    runs = _merge_runs(ws)
    assert [r["start"] for r in runs] == [0, 13]
    assert [r["bold"] for r in runs] == [True, False]


def test_offsets_are_into_the_joined_line():
    ws = [{"text": "ab", "runs": [{"start": 0, "family": "F", "size": 10.0,
                                   "bold": False, "italic": False}]},
          {"text": "cd", "runs": [{"start": 0, "family": "G", "size": 10.0,
                                   "bold": False, "italic": False}]}]
    runs = _merge_runs(ws)
    assert [r["start"] for r in runs] == [0, 3]      # "ab cd"


def test_a_word_without_runs_contributes_none():
    assert _merge_runs([{"text": "plain"}]) == []


def test_the_page_that_closed_the_description_list():
    r"""lib:d68e0271bd4d p24, read through the reader rather than from
    outside it: every line carries runs, and the lines that OPEN with a bold
    run are the three description labels plus the `Listing1.2.` caption.

    This is the signal the list rule needed and did not have; it was in the
    font classifier all along, one underscore from being kept.
    """
    import os

    import pytest as _pytest
    book = "work/run-files/T-0156-list/book.pdf"
    if not os.path.exists(book):
        _pytest.skip("the measured book is a work copy, not in the repo")
    pdfplumber = _pytest.importorskip("pdfplumber")
    from pdfdrill.chars_to_lines import lines_json_streaming

    def pages():
        with pdfplumber.open(book) as pdf:
            pg = pdf.pages[23]
            yield {"page_number": 24, "width": pg.width, "height": pg.height,
                   "chars": [{"x0": c["x0"], "y0": c["y0"], "x1": c["x1"],
                              "y1": c["y1"], "text": c["text"],
                              "fontname": c["fontname"], "size": c["size"],
                              "upright": c.get("upright", True)}
                             for c in pg.chars]}

    lines = lines_json_streaming(pages(), source="pdfminer-chars")["pages"][0]["lines"]
    assert lines and all(l.get("runs") for l in lines)
    # `block` IS NOT EMITTED, and this assertion is the corrected one.
    # 23a5effa carried a `block` into every line from the grouping key while
    # `_emit_words` still wrote a hardcoded 0 -- so the field arrived the
    # same on all 45 lines of lib:d68e0271bd4d p24, and this test pinned
    # that constant as though it were evidence. A field with one value is
    # evidence of nothing; it comes back when a reader measures a layout
    # block. See `tests/test_a_number_is_emitted_once.py` for the same
    # disease found at the serialiser.
    assert not any("block" in l for l in lines)
    opens_bold = [l for l in lines if (l.get("runs") or [{}])[0].get("bold")]
    assert len(opens_bold) == 4, [l["text"][:30] for l in opens_bold]
