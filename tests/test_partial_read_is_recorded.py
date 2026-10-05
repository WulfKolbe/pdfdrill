"""882 — A STOPPED READ MUST NOT LOOK LIKE A FINISHED ONE.

The corpus re-pass reported 0 failures and was telling the truth: no read
raised. Five stopped partway, and a stopped read used to leave an
`equations.json` byte-shaped exactly like a document with no equations —
zero counts, a one-page map. The fact lived only in the string the command
returned, which reached a run log in /tmp and nothing else.

These tests hold the fact in the two artefacts a consumer actually reads.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pdfdrill import eqlist                                  # noqa: E402


def _equations_json(tmp_path: Path, name: str, partial) -> Path:
    """A minimal `equations.json` of the shape `_document_entry` reads."""
    folder = tmp_path / name
    folder.mkdir()
    (folder / f"{name}.pdf").write_bytes(b"%PDF-1.4\n")
    doc = {
        "bibkey": name,
        "counts": {"total": 0, "display": 0, "inline": 0},
        "pages": {"1": {"width_pt": 612.0, "height_pt": 792.0}},
        "partial_read": partial,
        "equations": [],
    }
    (folder / f"{name}.equations.json").write_text(json.dumps(doc))
    return folder


def test_a_whole_read_carries_no_partial_marker(tmp_path):
    folder = _equations_json(tmp_path, "whole", None)
    entry = eqlist._document_entry(folder, "whole", 0, 0, "pdfTeX", None, 13,
                                   "producer says pdfTeX")
    assert entry["partial_read"] is None, (
        "a document read whole must not be marked partial")


def test_a_stopped_read_says_how_far_it_got(tmp_path):
    folder = _equations_json(tmp_path, "stopped", {
        "pages_read": 1, "pages_in_pdf": 13,
        "error": "list index out of range"})
    entry = eqlist._document_entry(folder, "stopped", 0, 0, "pdfTeX", None, 13,
                                   "producer says pdfTeX")
    p = entry["partial_read"]
    assert p and p["pages_read"] == 1 and p["pages_in_pdf"] == 13
    assert "index out of range" in p["error"]


def test_zero_rows_alone_cannot_distinguish_the_two(tmp_path):
    """The defect this exists to prevent, stated as a test.

    Both documents list zero rows. If `partial_read` were dropped the two
    entries would be identical, which is exactly how th-6236-91 (1 page of
    13) sat among 549 documents that genuinely have no display mathematics.
    """
    whole = eqlist._document_entry(
        _equations_json(tmp_path, "w", None), "w", 0, 0, "pdfTeX", None, 13, "x")
    stopped = eqlist._document_entry(
        _equations_json(tmp_path, "s", {"pages_read": 1, "pages_in_pdf": 13,
                                        "error": "boom"}),
        "s", 0, 0, "pdfTeX", None, 13, "x")
    assert whole["rows_listed"] == stopped["rows_listed"] == 0
    assert whole["partial_read"] != stopped["partial_read"], (
        "with partial_read dropped these two documents are indistinguishable")


def test_cmd_equations_writes_the_field_at_all():
    """The writer must emit the key, present or absent.

    `eqlist` reads `partial_read` from `equations.json`; a writer that only
    emits it on failure means every older artefact is silently "fine", which
    is the same ambiguity one layer back.
    """
    src = (Path(__file__).resolve().parents[1]
           / "src/pdfdrill/commands.py").read_text(encoding="utf-8")
    assert 'data["partial_read"] = ({' in src, (
        "cmd_equations must write partial_read into equations.json")
    assert '"pages_read": len(pages),' in src
    assert '} if partial else None)' in src, (
        "the key must be written as None on a whole read, not omitted")


def test_the_list_summary_counts_them():
    src = (Path(__file__).resolve().parents[1]
           / "src/pdfdrill/eqlist.py").read_text(encoding="utf-8")
    assert '"partial_reads": {' in src, (
        "a per-document field nobody reads is not a report; the summary "
        "has to carry the count")
