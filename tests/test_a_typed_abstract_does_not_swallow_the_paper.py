"""A typed `abstract` line latched the paragraph builder shut for the rest of
the document, so 699 of 704 prose lines reached no model object.

Found on the owner's YACCLAB batch (2026-10-28). Re-reading the 15 papers with
the FREE glyph reader fixed their structure — `section_header` 0 -> 1..35,
`list_item` 0 -> 12..215 — but three documents came out with a markdown file a
sixth of its former size, and the correlation over the batch is exact:

    folder              abstract lines   text lines   Paragraph   md KB
    sensors-15-23763               14          704           4       9
    2016acivs                       5          213           1       6
    2019caip_labeling              22          469           1       6
    the other twelve                0      261..996     30..126   26..91

`ParagraphProcessor` sets `in_abstract = True` on a line typed `abstract` and
only ever clears it by a REGEX on the text (`_ABSTRACT_END`). MathPix types its
abstract as plain `text`, so in the corpus this was written against the latch
was always released by the regex and the bug could not appear. The glyph reader
TYPES the abstract, so the first such line closed the builder and every later
prose line hit `if in_abstract: flush(); continue`.

Nothing reported it. `[ParagraphProcessor] {'paragraphs_created': 4}` was the
whole account of 704 lines — no skip counter, no reason, exactly the
silent-partial-success shape `_format_math_capture`'s docstring warns about.

The fix is to believe the TYPE when the reading provides it: where a reading
types its abstract, the type is the fence at both ends, and the regex ladder
stays for readings that do not.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

import pytest

from pdfdrill import commands as C


def _line(i: int, ltype: str, text: str, y: int) -> dict:
    return {"id": f"l{i}", "_i": i, "line": i, "type": ltype, "text": text,
            "text_display": text, "column": 0, "font_size": 30,
            "confidence": 1, "confidence_rate": 1, "is_printed": True,
            "is_handwritten": False, "conversion_output": True,
            "region": {"top_left_x": 100, "top_left_y": y,
                       "width": 1600, "height": 40}}


def _reading(n_abstract: int, n_text: int) -> dict:
    """One page: a typed abstract, then prose. The shape the glyph reader
    produces — `pdfminer-docmodel`, an integer (pixel) page frame."""
    lines, i, y = [], 0, 200
    lines.append(_line(i, "title", "A Paper About Labeling", y)); i += 1; y += 60
    for k in range(n_abstract):
        lines.append(_line(i, "abstract",
                           f"Abstract sentence {k} about the method.", y))
        i += 1; y += 50
    lines.append(_line(i, "section_header", "1 Introduction", y)); i += 1; y += 60
    for k in range(n_text):
        lines.append(_line(i, "text",
                           f"Body sentence {k} carrying the argument of the paper.",
                           y))
        i += 1; y += 50
    return {"source": "pdfminer-docmodel",
            "pages": [{"image_id": "doc-1", "page": 1,
                       "page_width": 2067, "page_height": 2923,
                       "lines": lines}]}


def _build(tmp_path: Path, reading: dict):
    """(object-type counts, the whole model's text) for a synthetic reading.

    The invariant is TEXT COVERAGE, not a paragraph count: consecutive prose
    lines merge into one Paragraph, so 60 body lines legitimately become two
    paragraphs. Counting them measured the merger, not the defect — the first
    version of this test failed its own control for that reason. What the
    defect destroys is the words, so the words are what gets asserted.
    """
    d = tmp_path / "doc"
    d.mkdir()
    pdf = d / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    (d / "doc.lines.json").write_text(json.dumps(reading), encoding="utf-8")
    out = C.cmd_model(pdf, force=True)
    model = d / "model.docmodel.json"
    assert model.exists(), out
    raw = model.read_text(encoding="utf-8")
    objs = (json.loads(raw).get("objects") or {})
    vals = list(objs.values() if isinstance(objs, dict) else objs)

    def _text(o):
        pr = o.get("props") or {}
        return " ".join(str(pr.get(k) or "") for k in
                        ("text", "markdown", "latex", "latex_original"))

    # ONLY the text the model's own OBJECTS carry. The first version of this
    # helper searched the whole model file, which embeds the reading's line
    # payloads — so every body sentence was "present" even when no Paragraph
    # had been built from it, and the test passed against the live defect.
    prose = " ".join(_text(o) for o in vals
                     if o.get("type") in ("Paragraph", "Abstract"))
    return collections.Counter(o.get("type") for o in vals), prose


def _body_lines_present(prose: str, n_text: int) -> int:
    return sum(1 for k in range(n_text) if ("Body sentence %d " % k) in prose)


def test_no_prose_is_lost_after_a_typed_abstract(tmp_path):
    """The defect at the size it was found: sensors-15-23763 kept 5 of 704
    prose lines. Every body line must reach the model."""
    got, prose = _build(tmp_path, _reading(n_abstract=14, n_text=120))
    assert got["Abstract"] == 14, dict(got)
    present = _body_lines_present(prose, 120)
    assert present == 120, (
        "%d of 120 body lines reached the model — the typed abstract latched "
        "the paragraph builder shut (%r)" % (present, dict(got)))
    assert got["Paragraph"] >= 1, dict(got)


def test_the_abstract_is_not_also_prose(tmp_path):
    """The converse, so the fix cannot pass by ignoring the abstract: its lines
    stay Abstract objects, and the body still arrives."""
    got, prose = _build(tmp_path, _reading(n_abstract=6, n_text=40))
    assert got["Abstract"] == 6, dict(got)
    assert _body_lines_present(prose, 40) == 40, dict(got)


def test_a_reading_with_no_typed_abstract_is_unchanged(tmp_path):
    """MathPix types its abstract as plain `text`, and the regex ladder that
    serves it stays. This is the population every earlier measurement came
    from, so it must not move."""
    got, prose = _build(tmp_path, _reading(n_abstract=0, n_text=60))
    assert got["Abstract"] == 0, dict(got)
    assert _body_lines_present(prose, 60) == 60, dict(got)
