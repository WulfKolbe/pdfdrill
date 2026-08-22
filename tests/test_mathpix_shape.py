"""The MathPix output guard must verify the artifact, not just its presence."""
import json

from pdfdrill.mathpix_client import _is_mathpix_output


def _lines(tmp_path, name, line):
    p = tmp_path / name
    p.write_text(json.dumps({"pages": [{"lines": [line]}]}))
    return str(p)


def test_pdfminer_lines_json_is_not_mathpix_output(tmp_path):
    """The case this exists for: a MathPix .tex.zip and .md sitting beside a
    .lines.json a later pdfminer pass overwrote. Existence-only reported
    'already present' and skipped forever, leaving 29 documents with
    equations and no confidence through a run meant to give them some."""
    p = _lines(tmp_path, "a.lines.json",
               {"id": "1", "region": {}, "text": "x", "text_display": "x",
                "type": "math"})
    assert _is_mathpix_output(".lines.json", p) is False


def test_mathpix_lines_json_is_recognised(tmp_path):
    p = _lines(tmp_path, "b.lines.json",
               {"id": "1", "type": "math", "text": "x", "confidence": 0.9,
                "confidence_rate": 0.99, "is_printed": True})
    assert _is_mathpix_output(".lines.json", p) is True


def test_a_mathpix_line_without_confidence_still_counts(tmp_path):
    """Not every MathPix line carries confidence; other fields identify it.
    Requiring confidence would re-fetch documents that are already correct."""
    p = _lines(tmp_path, "c.lines.json",
               {"id": "1", "type": "text", "text": "x", "cnt": [[0, 0]],
                "font_size": 9})
    assert _is_mathpix_output(".lines.json", p) is True


def test_absent_file_is_not_output(tmp_path):
    assert _is_mathpix_output(".lines.json", str(tmp_path / "nope.json")) is False


def test_unreadable_file_is_treated_as_absent(tmp_path):
    p = tmp_path / "d.lines.json"
    p.write_text("{not json")
    assert _is_mathpix_output(".lines.json", str(p)) is False


def test_other_formats_are_taken_at_face_value(tmp_path):
    """Only .lines.json has a cheap discriminator. Inventing one for .tex.zip
    would re-fetch on a guess."""
    p = tmp_path / "e.tex.zip"
    p.write_bytes(b"PK\x03\x04")
    assert _is_mathpix_output(".tex.zip", str(p)) is True
