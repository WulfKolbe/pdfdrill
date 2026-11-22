r"""One born-digital reader, and the poorer one is its fallback.

T-0156, under the owner's rule of 2026-11-22 — fix at the lowest level.

pdfdrill had TWO born-digital writers. `chars_to_lines` emits two line types,
`text` and `math`; the glyph reader in `src/pdfreader/` emits typed lines
(`section_header`, `list_item`, `figure_label`, `column`, `footnote`,
`page_info`, `code`, `equation`…). The twenty modules in `docmodel/modules/`
that build `Table`, `Diagram`, `CodeListing`, `Section` from typed lines had
nothing to work with, and the keyless lane topped out at paragraphs.

THE POORER WRITER WAS NEVER CHOSEN. It was REACHED. Both write the same path
(`_lines_json_path`), and `model` already prefers an existing lines.json --
`if not (lines_path.exists() or _write_born_digital_lines(pdf))`. So the
richer reading was a command nothing ran first: `glyphlines` has
`requires: None`, and so does `model`.

Measured, same document, same pipeline, from the PDF alone:

    arxiv.0912.2444     2 types -> 8     errors 36 -> 36    content row identical
    arxiv.2402.03975    2 types -> 10    errors 43 -> 43    content row identical

AND THE EXTRA TEXT IS LATEX, NOT DUPLICATION -- checked because a +39% text
count is exactly the shape of a record written twice:

    pdftotext 65,939  |  chars route 65,920 (1.00)  |  glyph 64,306 (0.98)
    pdftotext 127,707 |  chars route 127,233 (1.00) |  glyph 124,665 (0.98)

with control words and delimiters stripped. The raw +39%/+31% was markup:
30,596 and 49,428 LaTeX characters against 75 and 211 for the chars route.
"""
import json

import pytest

from pdfdrill import commands as C


def test_the_glyph_reader_is_tried_before_the_chars_route(monkeypatch, tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    order = []

    def glyph(p):
        order.append("glyph")
        return True

    def declined(p):
        order.append("chars")
        return True                                  # would decline the lane

    monkeypatch.setattr(C, "_write_glyph_lines", glyph)
    monkeypatch.setattr(C, "_pdfminer_declined", declined)
    assert C._write_born_digital_lines(pdf) is True
    assert order == ["glyph"], "the chars route must not run once the glyph reader wrote"


def test_the_chars_route_still_runs_when_the_glyph_reader_declines(monkeypatch, tmp_path):
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    seen = []
    monkeypatch.setattr(C, "_write_glyph_lines", lambda p: (seen.append("glyph"), False)[1])
    monkeypatch.setattr(C, "_pdfminer_declined", lambda p: (seen.append("chars"), True)[1])
    C._write_born_digital_lines(pdf)
    assert seen == ["glyph", "chars"], "a declining glyph reader must fall through"


def test_the_glyph_writer_never_displaces_a_reading(tmp_path):
    """It is reached only when no lines.json exists; it also checks itself."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    C._lines_json_path(pdf).write_text(json.dumps({"pages": []}), encoding="utf-8")
    assert C._write_glyph_lines(pdf) is False


def test_a_failing_reader_declines_rather_than_raising(monkeypatch, tmp_path):
    """A reader that raises must not take the command down -- the caller has
    two more lanes."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    assert C._write_glyph_lines(pdf) is False         # not a real PDF


def test_glyphlines_keeps_a_chars_reading_it_displaces():
    """Condition from the coordinator, 2026-11-22: the owner's library holds
    chars-route readings and nothing else records what they said.

    The MathPix clause above it has kept `.mathpix.bak.json` since cmd_ocr;
    a displaced chars reading had no such keeping.
    """
    import inspect
    src = inspect.getsource(C.cmd_glyphlines)
    assert '".chars.bak.json"' in src or ".chars.bak.json" in src
    at = src.find("chars_backup")
    assert at > 0, "the rollback must be in cmd_glyphlines itself"
    assert "not _is_mathpix_lines" in src[max(0, at - 400):at + 400], (
        "only OUR OWN earlier reading is kept under the chars name; a MathPix "
        "reading keeps its own")


def test_both_writers_write_the_same_path():
    """The fact that made the switch nearly free -- and that made the poorer
    writer reachable in the first place."""
    import inspect
    assert "_lines_json_path" in inspect.getsource(C._write_glyph_lines)
    assert "_lines_json_path" in inspect.getsource(C._write_born_digital_lines)
