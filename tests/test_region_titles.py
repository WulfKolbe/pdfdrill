"""The projector's own numbering and the public helper must agree — one
implementation, imported, never re-derived (math_titles' rule)."""
from docmodel.core import Document, DocObject
from docops.projectors.tiddlywiki import TiddlyWikiProjector, region_titles, math_titles
from docops.base import OperatorConfig


def _doc():
    doc = Document(meta={"bibkey": "D"})
    for i, (t, flow) in enumerate([("Table", 5), ("Diagram", 2), ("Picture", 9),
                                   ("Diagram", 1), ("Table", 3)]):
        doc.add(DocObject(id="o%d" % i, type=t, props={"flow_index": flow}))
    return doc


def test_region_titles_number_per_type_in_flow_order():
    t = region_titles(_doc(), "D")
    assert t["o3"] == "D_DIA_0001" and t["o1"] == "D_DIA_0002"
    assert t["o4"] == "D_TAB_001" and t["o0"] == "D_TAB_002"
    assert t["o2"] == "D_PIC_0001"


def test_projector_uses_the_same_numbering():
    doc = _doc()
    proj = TiddlyWikiProjector(OperatorConfig(op="projector",
                                              classname="TiddlyWikiProjector"))
    title, _inv = proj._assign_titles(doc, "D")
    for k, v in region_titles(doc, "D").items():
        assert title[k] == v
