"""103 — the per-document notation table."""
import json

import pytest

from pdfdrill.notation import Entry, NotationTable, load, path_for, save


def test_absent_file_is_an_empty_table_and_not_an_error(tmp_path):
    """Most documents declare no special notation. Absence must not raise and
    must be distinguishable from a table that exists and is empty."""
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF")
    t = load(pdf)
    assert len(t) == 0 and t.present is False


def test_present_but_empty_is_distinguishable_from_absent(tmp_path):
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF")
    path_for(pdf).write_text(json.dumps({"version": 1, "entries": []}))
    t = load(pdf)
    assert len(t) == 0 and t.present is True


def test_roundtrip(tmp_path):
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF")
    tbl = NotationTable(bibkey="d", entries=[
        Entry(r"\mathbf{S}_{a}^{b}", "discrete_integral",
              r"\sum_{k=a}^{b} f(k)\,\Delta k", note="p.42", examples=["d_EQ0007"])])
    save(pdf, tbl)
    got = load(pdf)
    assert got.present and len(got) == 1
    e = got.by_macro("discrete_integral")
    assert e.definition.startswith(r"\sum") and e.examples == ["d_EQ0007"]


def test_incomplete_entry_raises_naming_the_field(tmp_path):
    """A table that exists and cannot be read is NOT the same as no table. A
    typo must not silently disable a document's notation."""
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF")
    path_for(pdf).write_text(json.dumps(
        {"entries": [{"glyph_context": "S", "macro_name": "x"}]}))
    with pytest.raises(ValueError, match="definition"):
        load(pdf)


def test_duplicate_macro_name_raises(tmp_path):
    pdf = tmp_path / "d.pdf"
    pdf.write_bytes(b"%PDF")
    path_for(pdf).write_text(json.dumps({"entries": [
        {"glyph_context": "a", "macro_name": "m", "definition": "1"},
        {"glyph_context": "b", "macro_name": "m", "definition": "2"}]}))
    with pytest.raises(ValueError, match="duplicate"):
        load(pdf)
