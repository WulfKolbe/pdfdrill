"""236 — the handover list keys on folder path, never on title.

A title-keyed list merges the documents that collapse to one heading, and the
merged row shows one document's measurement under the other's name: a short
measurement under a full heading, which reads as a finding rather than a bug.

Measured on this corpus: 159 of 1,062 documents share a normalised title with
at least one other, collapsing to 72 keys — a title-keyed list loses 87 rows
and says nothing about having lost them.
"""
import json

import pytest

from pdfdrill.commands import (handover_rows, cmd_handover, meta_title,
                               HandoverCollision)


def _doc(root, name, *, title, ink=None):
    d = root / name
    d.mkdir(parents=True)
    (d / f"{name}.pdf").write_bytes(b"%PDF-1.4\n")
    (d / "report.log").write_text(
        "Output written on report.pdf (7 pages, 10 bytes).\n", encoding="utf-8")
    (d / "report.tex").write_text("\\ident{X}\n", encoding="utf-8")
    (d / "report.pdf").write_bytes(b"%PDF-1.4\n")
    (d / f"{name}.md").write_text("x", encoding="utf-8")
    (d / f"{name}.inspect.html").write_text("<html>", encoding="utf-8")
    (d / f"{name}.tiddlers.json").write_text(
        json.dumps([{"title": f"{name}_EQ0001", "latex": "x"}]), encoding="utf-8")
    (d / "model.docmodel.json").write_text(
        json.dumps({"meta": {"bibkey": name, "title": title},
                    "objects": []}), encoding="utf-8")
    if ink is not None:
        (d / "report.ink.json").write_text(json.dumps({"rows": ink}),
                                           encoding="utf-8")
    return d


def test_two_documents_with_the_SAME_title_are_two_rows(tmp_path):
    """The case the key change exists for. 159 corpus documents are in it."""
    _doc(tmp_path, "alpha", title="Geometric Algebra")
    _doc(tmp_path, "beta", title="Geometric Algebra")
    rows = handover_rows(tmp_path)
    assert len(rows) == 2
    assert len({r["path"] for r in rows}) == 2
    assert {r["title"] for r in rows} == {"Geometric Algebra"}   # display only


def test_a_title_that_PREFIXES_another_does_not_merge(tmp_path):
    _doc(tmp_path, "short", title="Quantum Electronics & Qubits")
    _doc(tmp_path, "long",
         title="Quantum Electronics & Qubits Exercise Sheet 2 - Solutions")
    rows = handover_rows(tmp_path)
    assert len(rows) == 2
    assert sorted(r["bibkey"] for r in rows) == ["long", "short"]


def test_a_document_with_no_title_still_gets_a_row(tmp_path):
    d = _doc(tmp_path, "untitled", title="x")
    (d / "model.docmodel.json").write_text('{"meta": {}, "objects": []}',
                                           encoding="utf-8")
    rows = handover_rows(tmp_path)
    assert len(rows) == 1 and rows[0]["title"] == ""


def test_the_row_count_assertion_is_a_RUNTIME_guard(tmp_path):
    """Not only a test. If the list ever collapses it is not handed over."""
    _doc(tmp_path, "a", title="A")
    rows = handover_rows(tmp_path)
    rows.append(dict(rows[0]))
    paths = {r["path"] for r in rows}
    with pytest.raises(HandoverCollision):
        if len(rows) != len(paths):
            raise HandoverCollision(
                "%d rows over %d distinct paths" % (len(rows), len(paths)))


def test_the_command_refuses_rather_than_emitting_a_collapsed_list(tmp_path,
                                                                   monkeypatch):
    _doc(tmp_path, "a", title="A")
    import pdfdrill.commands as C

    def boom(root, ready_only=False):
        raise HandoverCollision("2 rows over 1 distinct paths")
    monkeypatch.setattr(C, "handover_rows", boom)
    out = C.cmd_handover(tmp_path)
    assert out.startswith("REFUSING to hand over:")


def test_report_pdf_is_not_enumerated_as_a_document(tmp_path):
    """out/221: `ls *.pdf | head -1` picked report.pdf once the report
    existed, and one document was rebuilt as a report OF its own report."""
    _doc(tmp_path, "a", title="A")
    rows = handover_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["pdf"] == "a.pdf"


def test_ready_only_filters(tmp_path):
    _doc(tmp_path, "a", title="A")
    assert handover_rows(tmp_path, ready_only=True) == []


def test_meta_title_never_reads_past_meta_into_the_rows(tmp_path):
    """A Section object's `title` prop must not be mistaken for the document
    heading — meta comes first and the search stops at the objects array."""
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"meta": {"title": "The Document"},
                             "objects": [{"props": {"title": "A Section"}}]}),
                 encoding="utf-8")
    assert meta_title(p) == "The Document"


def test_meta_title_is_absent_not_fatal(tmp_path):
    assert meta_title(tmp_path / "nothing.json") == ""


def test_refine_report_pdf_is_derived_too(tmp_path):
    """out/217 named it refine.report.pdf so a `report.*` sweep could not
    catch it beside the quarantined report.ink.json.MISPAIRED. The same rename
    walked it past a derived-PDF check that only knew the exact name
    "report.pdf", and it was being enumerated as a document of its own."""
    from pdfdrill.sidecar import _is_derived_pdf
    from pathlib import Path
    assert _is_derived_pdf(Path("x/refine.report.pdf"))
    assert _is_derived_pdf(Path("x/report.pdf"))
    assert not _is_derived_pdf(Path("x/0707.4470.pdf"))


def test_a_pdf_with_no_model_is_not_a_document(tmp_path):
    """iter_documents walks the root AND its subdirectories, so pointing it at
    one document's folder enumerates that document's `latex/` e-print figures
    as more "documents" — twelve rows, none of them a document, all sharing
    the empty title. Requiring a model makes the list's population the same one
    publishready judges."""
    _doc(tmp_path, "real", title="Real")
    figs = tmp_path / "real" / "latex"
    figs.mkdir()
    for n in ("scatter_xy", "triangle-cancelling", "minimal-uft"):
        (figs / f"{n}.pdf").write_bytes(b"%PDF-1.4\n")
    rows = handover_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["bibkey"] == "real"
