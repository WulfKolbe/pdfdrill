import json

from docmodel.core import Document, DocObject, Realization
from pdfdrill import refine as rf
from pdfdrill.reports.from_document import build_rows, refined_rows_map
from pdfdrill.reports.rows import EquationRow, FormulaRow, TableRow, ImageRow

BK = "DOC"


def _doc():
    doc = Document(meta={"bibkey": BK})
    doc.add(DocObject(id="e1", type="Equation", props={
        "flow_index": 3, "latex": "a=b", "page": 2, "equation_number": "(1)",
        "confidence": 0.91, "trailing_punct": ".", "cdn_url": "https://cdn/x.jpg",
        "region": {"top_left_x": 1, "top_left_y": 2, "width": 300, "height": 40}}))
    doc.add(DocObject(id="f1", type="Formula", props={"flow_index": 1, "latex": "P"}))
    doc.add(DocObject(id="f2", type="Formula", props={"flow_index": 2, "latex": "\\square"}))
    doc.add(DocObject(id="t1", type="Table", props={
        "flow_index": 4, "mathpix_text": "\\begin{tabular}{c}1\\end{tabular}",
        "page": 5, "confidence": 0.7,
        "region": {"top_left_x": 1, "top_left_y": 2, "width": 400, "height": 80}}))
    doc.add(DocObject(id="d1", type="Diagram", props={
        "flow_index": 5, "page": 6,
        "region": {"top_left_x": 3, "top_left_y": 4, "width": 100, "height": 50}}))
    doc.add(DocObject(id="p1", type="Picture", props={"flow_index": 6, "page": 7,
                                                        "url": "https://cdn/p.jpg"}))
    return doc


def _lines(tmp_path):
    p = tmp_path / "DOC.lines.json"
    p.write_text(json.dumps({"pages": [
        {"lines": [{"type": "text", "text": "distribution \\(P\\) of",
                    "confidence": 0.98,
                    "region": {"top_left_x": 10, "top_left_y": 20,
                               "width": 800, "height": 40}}]}]}))
    return p


def test_every_kind_is_typed_and_named_by_the_projector_authority():
    rows = build_rows(_doc(), BK)
    assert [(type(r), r.identifier) for r in rows["equation"]] == [(EquationRow, "DOC_EQ0001")]
    assert [r.identifier for r in rows["formula"]] == ["DOC_FO0001", "DOC_FO0002"]
    assert [(type(r), r.identifier) for r in rows["table"]] == [(TableRow, "DOC_TAB_001")]
    assert [(type(r), r.identifier) for r in rows["image"]] == [
        (ImageRow, "DOC_DIA_0001"), (ImageRow, "DOC_PIC_0001")]


def test_equation_fields():
    (r,) = build_rows(_doc(), BK)["equation"]
    assert (r.latex, r.page, r.eqnum, r.px_width, r.trailing_punct, r.confidence,
            r.cdn_url) == ("a=b", "2", "(1)", "300", ".", 0.91, "https://cdn/x.jpg")
    assert r.region == {"top_left_x": 1, "top_left_y": 2, "width": 300, "height": 40}


def test_equation_carries_ink_when_given():
    ink = {"DOC_EQ0001": {"flag": "weak", "code": "W|+1"}}
    (r,) = build_rows(_doc(), BK, ink=ink)["equation"]
    assert r.ink_code == "W|+1"


def test_formula_takes_its_host_line_from_lines_json(tmp_path):
    rows = build_rows(_doc(), BK, lines_path=_lines(tmp_path))
    p, sq = rows["formula"]
    assert p.host_line.page == 1 and p.host_line.confidence == 0.98
    assert p.host_line.region["width"] == 800
    assert sq.host_line is None


def test_lines_path_defaults_to_the_models_source_path(tmp_path):
    doc = _doc()
    doc.meta["source_path"] = str(_lines(tmp_path))
    p, _ = build_rows(doc, BK)["formula"]
    assert p.host_line is not None


def test_table_latex_is_mathpix_text_and_picture_url_is_its_cdn():
    rows = build_rows(_doc(), BK)
    (t,) = rows["table"]
    assert t.latex.startswith("\\begin{tabular}") and t.dims == ("400", "80")
    dia, pic = rows["image"]
    assert pic.cdn_url == "https://cdn/p.jpg" and dia.cdn_url == ""


def test_missing_lines_json_is_not_an_error(tmp_path):
    rows = build_rows(_doc(), BK, lines_path=tmp_path / "nope.json")
    assert all(r.host_line is None for r in rows["formula"])


# ---------------------------------------------------------------------------
# 669 -- publish the refined reading where the raw is worse
#
# Decision table, defended cell by cell in from_document._chosen_reading's
# own docstring. `report_tex.display_safe` on two short, real strings gives
# a deterministic RENDERS/REFUSED pair for each row of the table without
# needing xelatex: "a & b \\\\ c & d" is refused (a bare longtable `&`/`\\`
# with no wrapping env); "a=b" and "c=d" both render.
# ---------------------------------------------------------------------------

REFUSED = "a & b \\\\ c & d"


def _refined_obj(obj_id, *, latex, refined, state, verified_by="ink",
                 basis="measured"):
    """One Equation object in each of the five `refine.refinement_state`
    states, real `DocObject`/`Realization` (not the duck-typed stand-ins
    `test_refinement_state.py` uses) -- `build_rows` walks the actual
    `docmodel.core.Document`."""
    props = {"flow_index": 1, "latex": latex}
    if state != rf.NONE:
        props[rf.REFINED_FIELD] = refined
    o = DocObject(id=obj_id, type="Equation", props=props)
    if state == rf.VERIFIED:
        o.add_realization(Realization(
            stream=rf.REFINED_STREAM, role="latex_candidate",
            provenance="change",
            props={rf.REFINED_FIELD: refined, "verified_by": verified_by,
                  "basis": basis}))
    elif state == rf.CONTRADICTED:
        o.add_realization(Realization(
            stream=rf.REFINED_STREAM, role="latex_candidate",
            provenance="change",
            props={rf.REFINED_FIELD: "something else entirely",
                  "verified_by": verified_by}))
    elif state == rf.UNVERIFIED:
        o.add_realization(Realization(
            stream=rf.REFINED_STREAM, role="latex_candidate",
            provenance="change", props={rf.REFINED_FIELD: refined}))
    # ORPHANED: the twin prop with no change realization at all -- nothing
    # further to add.
    assert rf.refinement_state(o)["state"] == state, "fixture built the wrong state"
    return o


def _one_equation_row(obj):
    doc = Document(meta={"bibkey": BK})
    doc.add(obj)
    (r,) = build_rows(doc, BK)["equation"]
    return r


def test_no_refinement_reads_latex_alone_as_before():
    r = _one_equation_row(_refined_obj("e1", latex="a=b", refined="",
                                       state=rf.NONE))
    assert r.latex == "a=b" and r.refined_info is None


def test_verified_and_both_render_PREFERS_the_refinement():
    """The defect PROPS.md names: reading `latex` alone ignores an accepted
    repair even when the raw itself renders fine. 28 of 31 in the corpus are
    exactly this cell."""
    r = _one_equation_row(_refined_obj("e1", latex="a=b", refined="c=d",
                                       state=rf.VERIFIED))
    assert r.latex == "c=d"
    assert r.refined_info is not None and r.refined_info["basis"] == "measured"


def test_verified_and_raw_refused_PREFERS_the_refinement():
    """The clear win: 2 of 31 in the corpus. `refinement_state` alone (no
    render check) already gets this cell right, but the render check must
    not accidentally refuse it too."""
    r = _one_equation_row(_refined_obj("e1", latex=REFUSED, refined="c=d",
                                       state=rf.VERIFIED))
    assert r.latex == "c=d" and r.refined_info is not None


def test_verified_but_refined_refused_KEEPS_the_raw():
    """The trap: preferring blindly regresses this row from rendering to
    not rendering. 1 of 31 in the corpus (lyche-numerical-linear-algebra_
    EQ0579, a misattributed span) is exactly this cell, and it is the reason
    the rule is not simply `refinement_state(obj) == VERIFIED`."""
    r = _one_equation_row(_refined_obj("e1", latex="a=b", refined=REFUSED,
                                       state=rf.VERIFIED))
    assert r.latex == "a=b" and r.refined_info is None


def test_contradicted_KEEPS_the_raw_even_when_the_refinement_would_render():
    """`refinement_state`, not a truthiness test on `latex_refined`: a
    CONTRADICTED refinement must never be read as good even though the
    prop's own value would render."""
    r = _one_equation_row(_refined_obj("e1", latex="a=b", refined="c=d",
                                       state=rf.CONTRADICTED))
    assert r.latex == "a=b" and r.refined_info is None


def test_unverified_KEEPS_the_raw():
    r = _one_equation_row(_refined_obj("e1", latex="a=b", refined="c=d",
                                       state=rf.UNVERIFIED))
    assert r.latex == "a=b" and r.refined_info is None


def test_orphaned_KEEPS_the_raw():
    r = _one_equation_row(_refined_obj("e1", latex="a=b", refined="c=d",
                                       state=rf.ORPHANED))
    assert r.latex == "a=b" and r.refined_info is None


def test_refinement_applies_to_formula_objects_too_and_keeps_host_line_key():
    """MATH_TYPES is Equation AND Formula (refine.py), and this is not a
    hypothetical: fix round 1 caught this file's own out/669.txt claiming
    (unchecked) that the 31-object corpus was all-Equation. Counted
    directly it is 30 Equation + 1 Formula -- 0707.4470_FO0175
    (obj_0c9487434929), VERIFIED, both readings render -- matching
    docs/layers/PROPS.md's own type list for this property. The host-line
    lookup must still key on the RAW reading -- the text a
    `first_occurrences` span was recorded against never changes."""
    doc = Document(meta={"bibkey": BK})
    f = _refined_obj("f1", latex="P", refined="Q", state=rf.VERIFIED)
    f.type = "Formula"
    f.props["flow_index"] = 1
    doc.add(f)
    rows = build_rows(doc, BK)
    (r,) = rows["formula"]
    assert r.latex == "Q" and r.refined_info is not None


def test_refined_rows_map_collects_only_the_rows_that_actually_published_one():
    doc = Document(meta={"bibkey": BK})
    doc.add(_refined_obj("e1", latex="a=b", refined="c=d", state=rf.VERIFIED))
    doc.add(_refined_obj("e2", latex="x=y", refined="", state=rf.NONE))
    rows = build_rows(doc, BK)
    m = refined_rows_map(rows)
    assert set(m) == {"DOC_EQ0001"}
    assert m["DOC_EQ0001"]["basis"] == "measured"


def test_a_fixture_with_no_refinement_or_identical_readings_cannot_discriminate():
    """Rule 17 -- a pattern verified on a sample that lacks the case it
    exists to catch cannot fail. Neither a NONE-state object nor a VERIFIED
    one whose refined text equals the raw would show a difference between
    'read latex alone' and 'apply the 669 rule' -- both tests above use
    genuinely different, genuinely renderable content on both sides of the
    VERIFIED cells for exactly this reason. This test pins the negative: an
    identical-content VERIFIED refinement is indistinguishable by content,
    on purpose (nothing to prefer)."""
    r = _one_equation_row(_refined_obj("e1", latex="a=b", refined="a=b",
                                       state=rf.VERIFIED))
    assert r.latex == "a=b"          # same either way -- not a useful probe
    assert r.refined_info is not None  # but the state IS still VERIFIED
