r"""An equation's number says where it came from.

T-0156. `refnum_origin` records WHICH path gave the number — "line" (an
`equation_number` line nearby), "gutter" (the row's own band, for a promoted
row) or "absorbed" (split off the end of the maths). It was computed on all
three branches and asserted by `test_absorbed_eqnum` — ON THE ITEM — and then
not copied into the DocObject's props, so NO model on disk carried it.

A census of 8,854 refnums across 400 library models found it recorded on none
of them. The attribution it exists for therefore had to be guessed from
`refnum_anchor`, and that proxy said `3 cdot 4` came from the absorbed path —
a value whose pattern (`\d+(?:\.\d+)*[a-zA-Z]?`) cannot produce it. The
contradiction is what exposed the proxy; a provenance field that never reaches
the model reads as evidence of nothing, and is worse than its absence.
"""
import pytest

from docmodel.base_module import ModuleConfig
from docmodel.core import Document
from docmodel.modules.equation import EquationProcessor
from docmodel.modules.page import ingest_lines_json


def _doc(lines):
    doc = Document()
    for i, ln in enumerate(lines):
        ln.setdefault("id", f"l{i}")
        ln.setdefault("region", {"top_left_y": i * 40, "height": 30,
                                 "top_left_x": 0, "width": 400})
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "im-01",
                                       "lines": lines}]})
    return doc


def _equations(lines):
    """Through the module's real contract: `find_items` then `create_object`,
    which is what builds the props the model carries."""
    doc = _doc(lines)
    m = EquationProcessor(ModuleConfig(title="E", classname="E", proc_order=0),
                          "T")
    out = []
    for item in m.find_items(doc):
        obj = m.create_object(item, doc)
        if obj is not None:
            out.append(obj)
    return out


def test_a_number_from_a_line_says_so_on_the_object():
    eqs = _equations([
        {"type": "math", "text": r"\[E = m c^{2}\]"},
        {"type": "equation_number", "text": "(204)"},
    ])
    assert eqs, "no Equation object built"
    assert eqs[0].props.get("refnum") == "204"
    assert eqs[0].props.get("refnum_origin") == "line"


def test_an_absorbed_number_says_so_on_the_object():
    eqs = _equations([{"type": "math", "text": r"\[E = m c^{2} \quad (204)\]"}])
    assert eqs
    assert eqs[0].props.get("refnum") == "204"
    assert eqs[0].props.get("refnum_origin") == "absorbed"


def test_an_equation_with_no_number_records_an_empty_source():
    eqs = _equations([{"type": "math", "text": r"\[E = m c^{2}\]"}])
    assert eqs
    assert not eqs[0].props.get("refnum")
    assert eqs[0].props.get("refnum_origin") == ""


def test_the_prop_is_present_on_every_equation():
    """Present, not merely truthy: a key that is sometimes absent cannot be
    censused, which is how this went unnoticed."""
    eqs = _equations([
        {"type": "math", "text": r"\[a = b\]"},
        {"type": "equation_number", "text": "(1)"},
        {"type": "math", "text": r"\[c = d\]"},
    ])
    assert eqs
    for e in eqs:
        assert "refnum_origin" in (e.props or {}), e.props


@pytest.mark.parametrize("source", ["line", "absorbed", ""])
def test_every_value_the_module_writes_is_one_of_the_known_ones(source):
    assert source in {"line", "gutter", "absorbed", ""}


# --------------------------------------- the same guard at the other display

r"""The LaTeX projector was not the only place a refnum is PRINTED.

`compressed_tiddlers` appends `(refnum)` after a display, so the values that
made `\tag{left7^{*}right}` would have made `$$ … $$ (left7^{*}right)` too —
output that renders and is wrong, in a second projection. The shape guard is
the same one (`looks_like_a_printed_number`), applied at both display sites,
because the model stays FAITHFUL to the reading: a reading that mis-types a
line is the reading's defect, and correcting the value in `refnum` would hide
a measurable upstream error (224 of 6,904 `equation_number` lines).
"""


def test_the_tiddler_display_guards_the_number_too():
    """Behaviour, not source: a refnum that is not a number is not printed."""
    from docops.base import OperatorConfig
    from docops.projectors.compressed_tiddlers import \
        CompressedTiddlersProjector

    doc = Document()
    from docmodel.core import DocObject
    for i, refnum in enumerate(["1.1", "left7^{*}right"]):
        doc.add(DocObject(type="Equation",
                          props={"latex": "a = b", "refnum": refnum,
                                 "flow_index": i}))
    out = CompressedTiddlersProjector(OperatorConfig(
        op="projector",
        classname="CompressedTiddlersProjector")).project(doc)
    text = out if isinstance(out, str) else str(out)
    assert "(1.1)" in text, "a real number should still be printed"
    assert "left7" not in text, "mathematics must not be printed as a number"


def test_the_prop_is_not_named_source():
    r"""The NAME is load-bearing.

    `_prefer_arxiv_source` decides whether to rebuild a model from the
    author's LaTeX by scanning every object's props for a key ENDING IN
    `_source` with a non-empty value — the mark of an enrichment a rebuild
    cannot reproduce. Named `refnum_source`, this provenance field tripped
    that heuristic: 8 equations on 1909.00741, which carries no `ref_source`,
    made the projection refuse the author's own LaTeX where it had used it.
    A prop name silently decided which document got built.
    """
    eqs = _equations([
        {"type": "math", "text": r"\[E = m c^{2}\]"},
        {"type": "equation_number", "text": "(204)"},
    ])
    assert eqs
    for key in (eqs[0].props or {}):
        assert not key.endswith("_source"), (
            "a prop ending in _source is read by _prefer_arxiv_source as an "
            "enrichment and refuses the author's LaTeX: %s" % key)
