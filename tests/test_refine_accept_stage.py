"""T-0024 items 2 and 3 at the level the defect lived: the accept STAGE.

`test_refine_no_reference.py` holds the predicate — `refine.ink_verdict` /
`ink_delta` — but the TypeError was raised in `commands.py`'s accept stage,
on `after < before` for a row `select` never gated, and its cost was not the
traceback: the run ended there, which is BEFORE `record`, so proposals that
had already been accepted and ink-verified were never attached to the model.
A test of the predicate alone cannot say that the run now reaches `record`.

So this drives the stage itself over one changes.json holding all three
shapes — a closer proposal, a worse one, and one with no reference — and
asserts on what the stage WROTE: the per-row outcome, the counts, the prose,
and the recorded realization on the model.

Measured on the pre-merge tree (90d07761), the same input raises
`TypeError: '<' not supported between instances of 'int' and 'NoneType'`
at commands.py:20502 and nothing is recorded.
"""
from __future__ import annotations

import json

import pytest

from pdfdrill import commands
from pdfdrill import refine as rf
from pdfdrill.model_io import load_model, save_model
from pdfdrill.sidecar import Sidecar


# ── one document, three proposals ──────────────────────────────────────────

ACCEPTED_ROW = "obj_1"        # ink 40 -> 12: closer to the scan
WORSE_ROW = "obj_2"           # ink 12 -> 40: further away
UNGATED_ROW = "obj_3"         # ink_after only: `select` never gated it


@pytest.fixture()
def refine_doc(tmp_path):
    """A model beside a PDF, and a changes.json the accept stage can read.

    Nothing here needs a scan or a render: `accept` compares two numbers that
    `select` and `measure` have already written.
    """
    from docmodel.core import Document, DocObject

    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    sc = Sidecar(pdf)
    sc.blob_dir.mkdir(parents=True, exist_ok=True)

    doc = Document()
    doc.meta["bibkey"] = "doc"
    for n in (1, 2, 3):
        doc.objects[f"obj_{n}"] = DocObject(
            id=f"obj_{n}", type="Equation", props={"latex": f"x_{n}", "page": 1})
    save_model(sc.blob_dir / "model.docmodel.json", doc)

    cp = rf.changes_path(sc.blob_dir)
    rf.save_changes(cp, {"bibkey": "doc", "proposals": [
        {"id": ACCEPTED_ROW, "status": "proposed", "proposed": "y_1",
         "ink_before": 40, "ink_after": 12},
        {"id": WORSE_ROW, "status": "proposed", "proposed": "y_2",
         "ink_before": 12, "ink_after": 40},
        {"id": UNGATED_ROW, "status": "proposed", "proposed": "y_3",
         "ink_after": 12},
    ]})
    return pdf, sc, cp


def _rows(cp):
    data = json.loads(cp.read_text(encoding="utf-8"))
    return data, {p["id"]: p for p in data["proposals"]}


def test_the_accept_stage_does_not_raise_on_an_ungated_row(refine_doc):
    """`int < None`. The stage used to end the run here."""
    pdf, _sc, cp = refine_doc
    prose = commands.cmd_refine(pdf, stages="accept")
    assert "accept:" in prose


def test_each_row_gets_the_outcome_its_numbers_earn(refine_doc):
    pdf, _sc, cp = refine_doc
    commands.cmd_refine(pdf, stages="accept")
    _data, rows = _rows(cp)
    assert rows[ACCEPTED_ROW]["status"] == "accepted"
    assert rows[WORSE_ROW]["status"] == "rejected"
    assert rows[WORSE_ROW]["reason"] == "no improvement"


def test_an_ungated_row_is_left_proposed_not_rejected(refine_doc):
    """Nothing about it has been found wanting, so a later run that gates it
    can still decide. A rejection would be a verdict nobody reached."""
    pdf, _sc, cp = refine_doc
    commands.cmd_refine(pdf, stages="accept")
    _data, rows = _rows(cp)
    assert rows[UNGATED_ROW]["status"] == "proposed"
    assert "no ink_before" in rows[UNGATED_ROW]["accept_note"]
    assert "reason" not in rows[UNGATED_ROW]


def test_the_count_is_in_the_state_and_in_the_prose(refine_doc):
    pdf, _sc, cp = refine_doc
    prose = commands.cmd_refine(pdf, stages="accept")
    data, _rows_by_id = _rows(cp)
    assert data["accept"] == {
        "accepted": 1, "rejected_no_improvement": 1, "no_reference": 1,
        "median_delta": -28.0, "at": data["accept"]["at"]}
    assert "1 left undecided for want of a reference" in prose


def test_the_run_reaches_record_and_the_model_carries_the_change(refine_doc):
    """The defect's real cost: `record` never ran. One accepted proposal is
    attached, and the ungated row is not."""
    pdf, sc, cp = refine_doc
    prose = commands.cmd_refine(pdf, stages="accept,record")
    assert "record:" in prose
    back = load_model(sc.blob_dir / "model.docmodel.json")
    changed = back.objects[ACCEPTED_ROW]
    assert changed.props.get(rf.REFINED_FIELD) == "y_1"
    assert changed.props["latex"] == "x_1"          # the original is untouched
    assert rf.REFINED_FIELD not in (back.objects[UNGATED_ROW].props or {})
    _data, rows = _rows(cp)
    assert rows[ACCEPTED_ROW].get("recorded")
    assert not rows[UNGATED_ROW].get("recorded")
