"""Cross-check pdfdrill's table grid against inkdrill's, and classify every
disagreement rather than reporting a score.

The two tools see different things and are both right. Measured on a
Word-produced handbook page: inkdrill finds the ruled table as ONE connected
component with 52 holes and recovers 13 rows x 4 columns (column widths
45.7 / 43.2 / 100.1 / 279.0 pt); `pdfdrill tables` on the same page reports a
different 6x5 table — the nameplate figure above it — and misses the ruled one
entirely. A number that averaged those two would describe neither.

So the output is a classification, never a percentage. `agree` is one outcome
among several and the others each name what differs.

NOTE ON THE PREMISE: inkdrill does not yet write `lines.json` — the contract is
specified but has no producer (measured on inkdrill@f48706c: the only mentions
of `lines.json` are in `tools/premise/measure.py`, which READS pdfdrill's).
These tests are therefore written against the documented contract and the
measured example above, and the ingest half is exercised against a synthetic
line carrying `ink.*` keys.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill.ink_crosscheck import (AGREE, GRID_DISAGREE, ONLY_IN_INK,
                                     ONLY_IN_MODEL, crosscheck_tables,
                                     ink_props, region_iou)


def _t(x, y, w, h, rows, cols, ncells=None):
    return {"region": {"top_left_x": x, "top_left_y": y, "width": w, "height": h},
            "n_rows": rows, "n_cols": cols,
            "cells": [{"row": 0, "col": 0, "row_span": 1, "col_span": 1}] * (
                ncells if ncells is not None else rows * cols)}


# --------------------------------------------------------------------------
# ink.* survives onto the object
# --------------------------------------------------------------------------

def test_namespaced_ink_keys_are_carried_and_nothing_else_is():
    line = {"type": "simple_cell", "text": "12", "cell_row": 2, "cell_column": 1,
            "ink.component_id": 41, "ink.holes": 52, "ink.rule_width_px": 3.4,
            "confidence": 0.98, "cnt": [[0, 0]]}
    out = ink_props(line)
    assert out == {"ink.component_id": 41, "ink.holes": 52, "ink.rule_width_px": 3.4}


def test_a_line_with_no_ink_keys_adds_nothing():
    assert ink_props({"type": "text", "text": "hello"}) == {}
    assert ink_props({}) == {}
    assert ink_props(None) == {}


def test_a_key_merely_containing_ink_is_not_namespaced():
    """`inkjet` and `thinking` are not the namespace; the dot is the contract."""
    assert ink_props({"inkjet": 1, "thinking": 2, "ink": 3}) == {}


# --------------------------------------------------------------------------
# matching two views of the same page
# --------------------------------------------------------------------------

def test_region_iou_is_1_for_identical_and_0_for_disjoint():
    a = {"top_left_x": 0, "top_left_y": 0, "width": 10, "height": 10}
    b = {"top_left_x": 100, "top_left_y": 100, "width": 10, "height": 10}
    assert region_iou(a, a) == 1.0
    assert region_iou(a, b) == 0.0
    assert region_iou(a, None) == 0.0


def test_the_same_table_seen_by_both_agrees():
    model = [_t(50, 100, 468, 300, 13, 4)]
    ink = [_t(50, 100, 468, 300, 13, 4)]
    res = crosscheck_tables(model, ink)
    assert [f["verdict"] for f in res] == [AGREE]


def test_the_measured_disagreement_is_classified_not_averaged():
    """The handbook page: inkdrill's 13x4 ruled table and pdfdrill's 6x5
    nameplate figure are DIFFERENT objects, not a 13-vs-6 discrepancy."""
    model = [_t(60, 40, 300, 120, 6, 5)]          # the nameplate figure, above
    ink = [_t(50, 300, 468, 300, 13, 4)]          # the ruled table, below
    res = crosscheck_tables(model, ink)
    verdicts = sorted(f["verdict"] for f in res)
    assert verdicts == [ONLY_IN_INK, ONLY_IN_MODEL]
    only_ink = [f for f in res if f["verdict"] == ONLY_IN_INK][0]
    assert only_ink["ink"]["n_rows"] == 13 and only_ink["ink"]["n_cols"] == 4


def test_the_same_region_with_a_different_grid_is_a_grid_disagreement():
    model = [_t(50, 100, 468, 300, 12, 4)]
    ink = [_t(50, 100, 468, 300, 13, 4)]
    res = crosscheck_tables(model, ink)
    assert [f["verdict"] for f in res] == [GRID_DISAGREE]
    assert res[0]["detail"]["n_rows"] == {"model": 12, "ink": 13}


def test_a_cell_count_disagreement_is_reported_with_both_counts():
    model = [_t(50, 100, 468, 300, 13, 4, ncells=52)]
    ink = [_t(50, 100, 468, 300, 13, 4, ncells=48)]
    res = crosscheck_tables(model, ink)
    assert res[0]["verdict"] == GRID_DISAGREE
    assert res[0]["detail"]["cells"] == {"model": 52, "ink": 48}


def test_every_table_on_both_sides_appears_exactly_once():
    """The classification must partition — a table silently dropped from the
    report is the failure this whole exercise exists to avoid."""
    model = [_t(0, 0, 10, 10, 2, 2), _t(0, 50, 10, 10, 3, 3)]
    ink = [_t(0, 0, 10, 10, 2, 2), _t(0, 100, 10, 10, 4, 4)]
    res = crosscheck_tables(model, ink)
    assert len(res) == 3
    seen_model = sum(1 for f in res if f.get("model") is not None)
    seen_ink = sum(1 for f in res if f.get("ink") is not None)
    assert seen_model == 2 and seen_ink == 2


def test_the_structural_warnings_from_check_are_carried_through():
    """`table_structure.check` is the existing validator; the cross-check
    reports what it says rather than re-implementing overlap detection."""
    bad = _t(0, 0, 10, 10, 2, 2)
    bad["cells"] = [{"row": 0, "col": 0, "row_span": 3, "col_span": 1}]   # out of grid
    res = crosscheck_tables([bad], [])
    assert res[0]["verdict"] == ONLY_IN_MODEL
    assert res[0]["warnings"] and "exceeds" in res[0]["warnings"][0]


def test_no_tables_at_all_is_an_empty_report_not_an_error():
    assert crosscheck_tables([], []) == []


def test_a_slight_overlap_is_not_a_match():
    """The nameplate figure and the ruled table below it can touch. A shared
    edge is not evidence that two tools are describing the same object, and
    matching on any overlap at all silently merges two findings into one."""
    model = [_t(50, 100, 400, 200, 6, 5)]           # y 100..300
    ink = [_t(50, 280, 400, 200, 13, 4)]            # y 280..480 — 10% overlap
    assert 0.0 < region_iou(model[0]["region"], ink[0]["region"]) < 0.30
    res = crosscheck_tables(model, ink)
    assert sorted(f["verdict"] for f in res) == [ONLY_IN_INK, ONLY_IN_MODEL]


def test_a_substantial_overlap_is_a_match():
    """Two views of one table never agree to the pixel; the threshold has to
    admit the real case as well as reject the near-miss."""
    model = [_t(50, 100, 400, 200, 13, 4)]
    ink = [_t(52, 104, 396, 194, 13, 4)]
    assert region_iou(model[0]["region"], ink[0]["region"]) > 0.30
    assert [f["verdict"] for f in crosscheck_tables(model, ink)] == [AGREE]


# --------------------------------------------------------------------------
# the seam: an ink.* key on a line must reach the DocObject
# --------------------------------------------------------------------------

def test_an_ink_key_on_a_cell_line_reaches_the_TableCell_object():
    """`ingest_lines_json` keeps every field of a line in the stream payload,
    but object construction copies only the props it names — so an `ink.*` key
    arrived in the stream and died there."""
    from docmodel.core import Document
    from docmodel.modules.page import ingest_lines_json
    from docmodel.base_module import ModuleConfig
    from docmodel.modules.table import TableProcessor

    lines = {"pages": [{"page": 1, "page_width": 595, "page_height": 842, "lines": [
        {"id": "t1", "type": "table", "text": "", "children_ids": ["c1"],
         "region": {"top_left_x": 50, "top_left_y": 100, "width": 468, "height": 300}},
        {"id": "c1", "type": "simple_cell", "text": "12",
         "cell_row": 0, "cell_column": 0,
         "ink.component_id": 41, "ink.holes": 52},
    ]}]}
    doc = Document(meta={"bibkey": "k"})
    ingest_lines_json(doc, lines)
    proc = TableProcessor(ModuleConfig(title="t", path="", type="", tags=""), "k")
    for item in proc.find_items(doc):
        proc.create_object(item, doc)

    cells = [o for o in doc.objects.values() if o.type == "TableCell"]
    assert cells, "no TableCell was built"
    assert cells[0].props.get("ink.component_id") == 41
    assert cells[0].props.get("ink.holes") == 52
    assert cells[0].props["text"] == "12"          # the existing props survive
