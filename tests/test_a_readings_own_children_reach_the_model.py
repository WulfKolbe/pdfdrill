r"""A reading that states which lines belong to another line is believed.

T-0157. Gemma4 7bd3786 writes a figure's printed subcaptions as lines whose
parent is the diagram, in `children_ids`. `page.ingest` keeps every field of a
line (`payload = dict(line)`), so the relation reaches the stream — and nothing
in `src/docmodel/` ever read it, so the objects came out as SIBLINGS under the
same Section.

MEASURED on 2312.11532 pp 6-7 (Gemma4 b696b9f), through drillgroup's own
`pagecheck.py` with the invocation the inspect set uses:

    yolo      overlap_model 14 -> 4    by page {2:1, 6:5, 7:5, 8:1, 9:2} -> {2:1, 8:1, 9:2}
    inklines  overlap_model 12 -> 2    by page {2:1, 6:5, 7:6}           -> {2:1, 7:1}
    box_text_lines, box_text_model, overlap_lines   unchanged in both

Every Diagram/subcaption pair on pp 6-7 is gone. What remains is an Equation
pair on p2, a Table/Paragraph pair on inklines p7 that was never a Diagram
pair, and p8/p9 — none of them this item.

THE SHAPE IS THE ONE THE MODEL ALREADY USES: `Table` owns its `TableCell`s
through `children`/`parent` — 5 Tables and 90 cells on this document, each
cell's `parent` the Table and not a Section — so a content object owning
content children is established here rather than invented. The subcaptions stay
Paragraph objects because a printed subcaption is text a reader cites, and the
owner's second requirement is that every drilled paragraph stay addressable.
`parent_section` is untouched, so the section relation is not lost.

TWO THINGS THAT HAD TO BE RIGHT, and each was wrong first:

  * THE OWNER OF A LINE IS THE NARROWEST CLAIM. Taking "the first object that
    realizes this line" made a `Page` the owner of the diagram line — a Page
    realization spans its whole page — so `child is parent` for all six
    subcaptions and nothing linked. `unclaimed.py` records the same trap and
    skips a type list; the span is sharper, because it also prefers a TableCell
    to its Table without naming either.
  * OWNERSHIP IS EXCLUSIVE. `pagecheck` builds `parents[id]` from `parent` and
    then overwrites it from every object's `children` IN DOCUMENT ORDER, so
    when a Section and a Diagram both list the same Paragraph the LAST one
    wins. The Section won: the Diagram held all six children, each child's
    `parent` was the Diagram, and `ancestors` for every subcaption still came
    out [Document, Section]. The overlap count did not move at all until the
    child was taken OUT of the Section's `children`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

C = pytest.importorskip("docmodel.core")
M = pytest.importorskip("docmodel.modules.document_structure")
BM = pytest.importorskip("docmodel.base_module")

LINES = BM.BaseModule.LINES_STREAM


def _doc(lines):
    """A Document with one lines stream, returning (doc, {line_id: anchor})."""
    doc = C.Document()
    stream = doc.ensure_stream(LINES)
    anchors = {}
    for ln in lines:
        anchors[ln["id"]] = stream.append(**ln)
    return doc, anchors


def _obj(doc, anchors, type_, line_ids, **props):
    o = C.DocObject(type=type_, props=dict(props))
    first, last = anchors[line_ids[0]], anchors[line_ids[-1]]
    o.add_realization(C.Realization(stream=LINES, role="surface",
                                    start=first, end=last))
    return doc.add(o)


def _link(doc):
    M.DocumentStructureProcessor.__new__(
        M.DocumentStructureProcessor)._link_reading_children(doc)


def _fixture():
    """A diagram line owning two subcaption lines, a Section spanning all of
    them, and a Page spanning everything — the real shape on 2312.11532."""
    lines = [
        {"id": "l1", "type": "diagram", "_page": 6,
         "children_ids": ["l2", "l3"]},
        {"id": "l2", "type": "text", "_page": 6, "text": "(a) first."},
        {"id": "l3", "type": "text", "_page": 6, "text": "(b) second."},
        {"id": "l4", "type": "text", "_page": 6, "text": "Ordinary prose."},
    ]
    doc, anchors = _doc(lines)
    page = _obj(doc, anchors, "Page", ["l1", "l4"], page=6)
    section = _obj(doc, anchors, "Section", ["l1", "l4"], page=6, level=1)
    dia = _obj(doc, anchors, "Diagram", ["l1"], page=6)
    p2 = _obj(doc, anchors, "Paragraph", ["l2"], page=6, text="(a) first.",
              parent_section=section.id)
    p3 = _obj(doc, anchors, "Paragraph", ["l3"], page=6, text="(b) second.",
              parent_section=section.id)
    p4 = _obj(doc, anchors, "Paragraph", ["l4"], page=6, text="Ordinary prose.")
    # the section owns them to begin with, as the structure pass leaves it
    for p in (dia, p2, p3, p4):
        p.parent = section.id
        section.children.append(p.id)
    return doc, section, dia, p2, p3, p4, page


def test_the_diagram_owns_the_subcaptions_the_reading_gave_it():
    doc, section, dia, p2, p3, p4, page = _fixture()
    _link(doc)
    assert dia.children == [p2.id, p3.id]
    assert p2.parent == dia.id and p3.parent == dia.id


def test_the_child_leaves_its_previous_owner():
    """The part that made the overlap count move. Without it the Section still
    listed the Paragraph, and `pagecheck` — which overwrites its parent map
    from every `children` list in document order — kept the Section."""
    doc, section, dia, p2, p3, p4, page = _fixture()
    _link(doc)
    assert p2.id not in section.children
    assert p3.id not in section.children
    assert p4.id in section.children        # untouched, it has no owner


def test_a_container_spanning_the_line_does_not_become_the_owner():
    r"""A `Page` realization spans its whole page, so "the first object that
    realizes this line" made the Page the diagram line's owner and nothing
    linked at all."""
    doc, section, dia, p2, p3, p4, page = _fixture()
    _link(doc)
    assert page.children == []
    assert p2.parent == dia.id


def test_the_section_relation_is_not_lost():
    """`parent_section` is the prop that carries it, and this does not touch
    it — the section stays reachable, now through the Diagram as well."""
    doc, section, dia, p2, p3, p4, page = _fixture()
    _link(doc)
    assert p2.props["parent_section"] == section.id


def test_a_child_realized_by_the_parents_own_object_is_not_a_relation():
    r"""A container whose realization spans its own children — a Table over
    its cells — must not be made its own parent, or `_ancestors` loops."""
    lines = [
        {"id": "t1", "type": "table", "_page": 1, "children_ids": ["t2"]},
        {"id": "t2", "type": "table_row", "_page": 1, "text": "a"},
    ]
    doc, anchors = _doc(lines)
    table = _obj(doc, anchors, "Table", ["t1", "t2"], page=1)
    _link(doc)
    assert table.children == []
    assert table.parent is None


def test_a_reading_without_children_ids_changes_nothing():
    lines = [{"id": "x1", "type": "text", "_page": 1, "text": "Only prose."}]
    doc, anchors = _doc(lines)
    p = _obj(doc, anchors, "Paragraph", ["x1"], page=1, text="Only prose.")
    _link(doc)
    assert p.children == [] and p.parent is None


def test_a_child_id_the_reading_names_but_no_object_realizes_is_skipped():
    """An honest no-op rather than a dangling id: the reading may name a line
    that no object claimed (a `ReadingRecord` the unclaimed pass dropped)."""
    lines = [
        {"id": "d1", "type": "diagram", "_page": 2,
         "children_ids": ["d2", "ghost"]},
        {"id": "d2", "type": "text", "_page": 2, "text": "(a) one."},
    ]
    doc, anchors = _doc(lines)
    dia = _obj(doc, anchors, "Diagram", ["d1"], page=2)
    kid = _obj(doc, anchors, "Paragraph", ["d2"], page=2, text="(a) one.")
    _link(doc)
    assert dia.children == [kid.id]
