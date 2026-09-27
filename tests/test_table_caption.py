"""819b — a table's caption, so a table can carry a `\\label`.

`table.py` had no caption handling at all: only 196 of 7,765 Table objects
carried one, so almost no table could be `\\ref`ed — and an internal link is
exactly what MathPix's own `.tex` has none of.

Measured over 260 corpus documents: 5,166 of 6,789 `table` container lines (76%)
have a labelled line IMMEDIATELY above, 5,168 of those typed `figure_label`.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from docmodel.modules._captions import (                    # noqa: E402
    FIGURE_KINDS, TABLE_KINDS, adjacent_label_caption)


class _Stream:
    def __init__(self, lines):
        self.anchors = list(range(len(lines)))
        self.payload = {i: ln for i, ln in enumerate(lines)}


def _l(ltype, text, page=1):
    return {"type": ltype, "text": text, "_page": page}


def _cap(lines, i, kinds=TABLE_KINDS, bare=True):
    return adjacent_label_caption(_Stream(lines), i, kinds=kinds, allow_bare=bare)


# ── the 76% case: a figure_label immediately above the table ─────────────────

def test_a_figure_label_above_the_table_is_its_caption():
    lines = [_l("figure_label", "Table 1: Temporal trigger words"),
             _l("table", "\\begin{tabular}...")]
    assert _cap(lines, 1) == "Table 1: Temporal trigger words"


def test_a_figure_label_below_the_table_is_also_its_caption():
    """A table caption sits above in most styles and below in others; a reader
    that assumes one loses the other."""
    lines = [_l("table", "x"),
             _l("figure_label", "Table 7: Performance of formal runs")]
    assert _cap(lines, 0) == "Table 7: Performance of formal runs"


# ── the guards, each load-bearing ────────────────────────────────────────────

def test_a_figure_caption_beside_a_table_is_NOT_the_tables_caption():
    """Without `kinds` a `Fig. 8.` caption next to a table becomes the table's
    own — which is why the helper takes the parameter at all."""
    lines = [_l("figure_label", "Fig. 8. Delta life span over time"),
             _l("table", "x")]
    assert _cap(lines, 1) == ""
    # ...and it IS a figure's caption
    assert _cap(lines, 1, kinds=FIGURE_KINDS) != ""


def test_prose_mentioning_a_table_is_not_a_caption():
    """`Table 4 shows the results.` sits immediately above a table in the
    corpus. It has no `.`/`:` terminator after the number and it continues on
    the same line, so neither rule can take it."""
    lines = [_l("text", "Table 4 shows the results."), _l("table", "x")]
    assert _cap(lines, 1) == ""


def test_a_label_on_another_page_is_not_a_caption():
    lines = [_l("figure_label", "Table 1: On the previous page", page=1),
             _l("table", "x", page=2)]
    assert _cap(lines, 1) == ""


def test_a_label_further_than_the_arrangement_allows_is_refused():
    """A caption that has to be searched for is a guess. Distance three, with
    nothing recognisable between, stays unclaimed."""
    lines = [_l("figure_label", "Table 1: Far away"), _l("text", "a"),
             _l("text", "b"), _l("table", "x")]
    assert _cap(lines, 3) == ""


def test_an_axis_label_that_does_not_parse_is_not_a_caption():
    """253: a `figure_label` is often the float's OWN text — an axis label, a
    legend entry. The parse into kind + number is the discriminator."""
    lines = [_l("figure_label", "frequency (Hz)"), _l("table", "x")]
    assert _cap(lines, 1) == ""


# ── the split shape: a bare label, the body on its own line ──────────────────

def test_a_bare_label_with_the_body_on_the_next_line():
    """`Table 2` / `Description for all message types.` / the table — measured:
    54 occurrences in 12 documents, and every one is a caption. This is the
    shape `_CAPTION_START` cannot take, because it requires the terminator that
    keeps prose out."""
    lines = [_l("text", "Table 2"),
             _l("text", "Description for all message types."),
             _l("table", "x")]
    assert _cap(lines, 2) == "Table 2. Description for all message types."


def test_a_bare_label_immediately_above_with_the_body_below_the_table():
    lines = [_l("table", "x"), _l("text", "Table 5"),
             _l("text", "Components dimensions.")]
    assert _cap(lines, 0) == "Table 5. Components dimensions."


def test_a_bare_label_with_no_body_yields_nothing():
    lines = [_l("text", "Table 2"), _l("table", "x")]
    assert _cap(lines, 1) == ""


def test_a_bare_label_of_the_wrong_kind_is_refused():
    lines = [_l("text", "Fig. 2"), _l("text", "A photograph."), _l("table", "x")]
    assert _cap(lines, 2) == ""


def test_allow_bare_off_keeps_the_old_behaviour():
    lines = [_l("text", "Table 2"), _l("text", "A body."), _l("table", "x")]
    assert _cap(lines, 2, bare=False) == ""


# ── the module attaches it, and the refnum drives the label ─────────────────

def _doc_with_table(lines):
    from docmodel.core import Document
    from docmodel.modules.page import ingest_lines_json
    doc = Document()
    doc.meta["bibkey"] = "doc"
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "i",
                                       "lines": lines}]})
    from docmodel.base_module import ModuleConfig
    from docmodel.modules.table import TableProcessor
    TableProcessor(ModuleConfig(title="T", classname="T"), "doc").process_document(doc)
    return [o for o in doc.objects.values() if o.type == "Table"]


def test_the_table_object_carries_the_caption_and_the_refnum():
    tabs = _doc_with_table([
        {"type": "figure_label", "text": "Table 3: Experiment results"},
        {"type": "table", "text": "t", "children_ids": ["c1"]},
        {"id": "c1", "type": "simple_cell", "text": "a", "cell_row": 0,
         "cell_column": 0},
    ])
    assert tabs, "a table object must still be created"
    assert tabs[0].props.get("caption") == "Table 3: Experiment results"
    assert tabs[0].props.get("refnum") == "3"


def test_a_table_with_no_caption_gets_no_refnum():
    tabs = _doc_with_table([
        {"type": "table", "text": "t", "children_ids": ["c1"]},
        {"id": "c1", "type": "simple_cell", "text": "a", "cell_row": 0,
         "cell_column": 0},
    ])
    assert tabs and not tabs[0].props.get("caption")
    assert not tabs[0].props.get("refnum")


# ── and the label reaches the LaTeX ─────────────────────────────────────────

def test_the_caption_produces_a_caption_and_a_label_in_latex():
    from docmodel.core import Document, DocObject
    from docops.base import OperatorConfig
    from docops.projectors.latex import LaTeXProjector
    doc = Document()
    doc.meta["bibkey"] = "doc"
    obj = DocObject(type="Table", props={
        "caption": "Table 3: Experiment results", "refnum": "3",
        "n_rows": 1, "n_cols": 2,
        "cells": [{"row": 0, "col": 0, "text": "a"},
                  {"row": 0, "col": 1, "text": "b"}]})
    doc.add(obj)
    pr = LaTeXProjector(OperatorConfig(op="projector", classname="LaTeXProjector"))
    pr._all_objects = [obj]
    tex = pr._tabular(obj)
    assert "\\caption{Table 3: Experiment results}" in tex
    assert "\\label{tab:3}" in tex


# ── the real document ───────────────────────────────────────────────────────

_REAL = (Path.home() / "pdfdrill-library" / "1-s2.0-S2590118425000565-main"
         / "model.docmodel.json")


@pytest.mark.skipif(not _REAL.is_file(), reason="corpus document not present")
def test_the_reported_document_gains_table_labels():
    from pdfdrill.model_io import load_model
    doc = load_model(_REAL)
    tabs = [o for o in doc.objects.values() if o.type == "Table"]
    captioned = [o for o in tabs if o.props.get("caption")]
    assert len(captioned) >= 2, "Table 2 and Table 3 carry a caption"
    assert {o.props.get("refnum") for o in captioned} >= {"2", "3"}


# ── the label pattern's own gaps, found while measuring ─────────────────────

@pytest.mark.parametrize("text,kind,num", [
    # 14 `figure_label` lines in the corpus read like this, and without Roman
    # numerals they parse as NO label at all and the table loses its caption.
    ("Table I. Power rating of different components", "Table", "I"),
    ("Table IV. Energy produced per year", "Table", "IV"),
    ("Tabelle 3: Ergebnisse", "Tabelle", "3"),
    ("Table 1.2b: nested and suffixed", "Table", "1.2b"),
])
def test_parse_caption_accepts_the_labels_the_corpus_uses(text, kind, num):
    from docmodel.modules._captions import parse_caption
    k, n, body = parse_caption(text)
    assert (k, n) == (kind, num)
    assert body


def test_no_kind_set_lists_a_kind_the_pattern_cannot_produce():
    """`TABLE_KINDS` held `Tab` and `Tafel` while `_LABEL` knew neither, so two
    of its three entries were dead and could never match."""
    from docmodel.modules import _captions as C
    import re
    producible = set()
    for kind in re.split(r"\|", C._KINDS):
        probe = kind.replace("\\.?", ".").replace("\\", "")
        k, _n, _b = C.parse_caption(f"{probe} 1: body")
        if k:
            producible.add(k)
        k2, _n2, _b2 = C.parse_caption(f"{probe.rstrip('.')} 1: body")
        if k2:
            producible.add(k2)
    assert C.TABLE_KINDS <= producible, C.TABLE_KINDS - producible
    assert C.FIGURE_KINDS <= producible, C.FIGURE_KINDS - producible
    assert not (C.TABLE_KINDS & C.FIGURE_KINDS)
