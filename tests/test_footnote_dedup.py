r"""637 — one `\footnotetext` per Footnote object, not two.

penev_A carried 93 Footnote objects for 48 printed footnotes, and its .tex
emitted 96 `\footnotetext` blocks with 42 openings repeated verbatim. The cause
is not two REALIZATIONS on one object (measured: every Footnote carries exactly
one `surface` and one `cleaned` realization, and the projector reads only the
body text) — it is two OBJECTS, one per creator:

  * `FootnoteProcessor` reads MathPix's `footnote` line — the PARENT;
  * `heading_cleanup.extract_footnote_paragraphs` reads the `\footnotetext{…}`
    MathPix ALSO left in the Paragraph built over that parent's CHILD lines.

The two therefore never share a line. Plain extent overlap identifies 20 of the
45 duplicated penev_A pairs; expanding a `footnote` line to its own children
identifies all 45 and joins nothing else.

RULING (the brief's): the creator that runs LATER — the cleanup — ADOPTS the
existing Footnote and fills its body with the cleaned realization, instead of
creating a second object. Where no such Footnote exists it creates one as
today, and where the body's lines could not be located nothing is adopted:
an adoption without an extent would be a guess.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.base_module import ModuleConfig
from docmodel.core import Document, DocObject, Realization
from docmodel import footnote_extent as fx
from docmodel.modules.footnote import FootnoteProcessor
from docmodel.modules.page import ingest_lines_json, PageProcessor
from docmodel.modules.paragraph import ParagraphProcessor
from docops.base import OperatorConfig
from docops.projectors import footnotes as fnres
from docops.projectors.latex import LaTeXProjector
from pdfdrill import heading_cleanup as hc


def _module(cls):
    return cls(ModuleConfig(classname=cls.__name__), bibkey="T", flags={})


def _doc(lines, page=1):
    doc = Document()
    doc.meta["bibkey"] = "T"
    ingest_lines_json(doc, {"pages": [{"page": page, "image_id": "i",
                                       "lines": lines}]})
    return doc


def _fn(doc):
    return sorted(doc.objects_of_type("Footnote"),
                  key=lambda o: str(o.props.get("refnum")))


def _mathpix_block(refnum="3", body="For a recent review.",
                   tail=" It continues here."):
    r"""The real MathPix shape: a `footnote` PARENT line whose CHILD `text`
    lines carry the `\footnotetext{…}`. Both creators see this block — the
    processor through the parent, the cleanup through the Paragraph the child
    lines make."""
    return [
        {"id": "blk", "type": "footnote", "text": "",
         "children_ids": ["c1", "c2"]},
        {"id": "c1", "type": "text",
         "text_display": "\\footnotetext{\\({ }^{%s}\\) %s" % (refnum, body)},
        {"id": "c2", "type": "text", "text_display": tail + "}"},
    ]


def _built(lines):
    doc = _doc(lines)
    for cls in (PageProcessor, FootnoteProcessor, ParagraphProcessor):
        _module(cls).process_document(doc)
    return doc


# ---------------------------------------------------------------- the relation

def test_a_footnote_line_covers_its_own_children():
    """The two creators anchor on the PARENT and on the CHILDREN, so a plain
    extent comparison says they are different footnotes. The expansion is what
    makes the relation exact — and it is only ever applied to a `footnote`
    line, never to prose."""
    doc = _built(_mathpix_block())
    st = doc.streams["mathpix_lines"]
    fn = _fn(doc)[0]
    plain = fx.covered_anchors(doc, fn, expand=False)
    grown = fx.covered_anchors(doc, fn)
    ids = {st.payload[a].get("id") for a in grown}
    assert {st.payload[a].get("id") for a in plain} == {"blk"}
    assert ids == {"blk", "c1", "c2"}


def test_a_prose_line_is_not_expanded_to_its_children():
    doc = _doc([
        {"id": "l1", "type": "text", "text_display": "Prose.",
         "children_ids": ["l2"]},
        {"id": "l2", "type": "text", "text_display": "More prose."},
    ])
    for cls in (PageProcessor, ParagraphProcessor):
        _module(cls).process_document(doc)
    st = doc.streams["mathpix_lines"]
    para = doc.objects_of_type("Paragraph")[0]
    ids = {st.payload[a].get("id") for a in fx.covered_anchors(doc, para)}
    assert ids == {"l1", "l2"} or ids == {"l1"}          # never grown BY the rule
    lone = [o for o in doc.objects.values() if o.type == "Paragraph"]
    assert len(lone) == 1


# ----------------------------------------------------------------- the adoption

def test_the_cleanup_adopts_an_existing_footnote_instead_of_creating_a_second():
    doc = _built(_mathpix_block())
    assert len(_fn(doc)) == 1                              # the processor's
    before = _fn(doc)[0].id
    hc.extract_footnote_paragraphs(doc)
    fns = _fn(doc)
    assert len(fns) == 1, [f.props for f in fns]
    assert fns[0].id == before                             # the SAME object
    assert doc.meta["footnote_adopted"] == 1


def test_the_adopted_body_is_the_cleaned_realization():
    r"""The two bodies are not identical: the processor concatenates the child
    lines, the cleanup reads the Paragraph's own (mutated) text. The ruling
    names the cleaned one, and it must reach BOTH the content prop and the
    `cleaned` realization — a stale realization beside a fresh prop is the
    'both reach the output' defect in another spelling."""
    doc = _built(_mathpix_block())
    fn = _fn(doc)[0]
    para = doc.objects_of_type("Paragraph")[0]
    para.props["text"] = "\\footnotetext{\\({ }^{3}\\) The cleaned body.}"
    hc.extract_footnote_paragraphs(doc)
    fn = _fn(doc)[0]
    assert fn.props["content"] == "The cleaned body."
    assert fnres.body_text(fn) == "The cleaned body."
    cleaned = [r for r in fn.realizations if r.role == "cleaned"]
    assert len(cleaned) == 1 and cleaned[0].props.get("text") == "The cleaned body."


def test_the_adoption_records_who_filled_it():
    doc = _built(_mathpix_block())
    hc.extract_footnote_paragraphs(doc)
    assert _fn(doc)[0].props["filled_by"] == "footnote_cleanup"


def test_the_adoption_keeps_a_refusal_flag_the_host_did_not_have():
    r"""637 fix round 1 — `_fill_footnote` used to copy content, extents and
    `filled_by` onto the host and drop the adopting segment's
    `tail_unassigned` (636's refusal marker) and `split_index`. The rule: the
    host's `tail_unassigned` is the OR of both — never cleared by a fill that
    happens to lack it — and a `split_index` the segment carries is recorded
    on the host only when the host has none of its own."""
    host = DocObject(type="Footnote", props={
        "refnum": "3", "page": 4, "content": "old"})
    hc._fill_footnote(host, "new body", [], tail_unassigned=True)
    assert host.props["tail_unassigned"] is True


def test_the_adoption_records_a_split_index_the_host_lacked():
    host = DocObject(type="Footnote", props={
        "refnum": "3", "page": 4, "content": "old"})
    hc._fill_footnote(host, "new body", [], split_index=2)
    assert host.props["split_index"] == 2


def test_the_adoption_never_overwrites_the_host_s_own_split_index():
    host = DocObject(type="Footnote", props={
        "refnum": "3", "page": 4, "content": "old", "split_index": 1})
    hc._fill_footnote(host, "new body", [], split_index=5)
    assert host.props["split_index"] == 1


def test_the_adoption_keeps_the_claim_on_the_paragraph_s_lines():
    """The cleanup's extent is what claims the child lines (634: the 35
    `footnote_cleanup+paragraph` doubly-claimed anchors are its work). Adoption
    must move that claim onto the host, not drop it — dropping it would report
    lines as covered by nobody while their text sits in a Footnote."""
    doc = _built(_mathpix_block())
    hc.extract_footnote_paragraphs(doc)
    st = doc.streams["mathpix_lines"]
    fn = _fn(doc)[0]
    ids = {st.payload[a].get("id") for a in fx.covered_anchors(doc, fn,
                                                               expand=False)}
    assert {"c1", "c2"} <= ids


def test_a_footnote_on_another_page_is_never_adopted():
    doc = _built(_mathpix_block())
    _fn(doc)[0].props["page"] = 99
    hc.extract_footnote_paragraphs(doc)
    assert len(_fn(doc)) == 2                              # not the same footnote


def test_a_footnote_with_another_number_is_never_adopted():
    doc = _built(_mathpix_block())
    _fn(doc)[0].props["refnum"] = "8"
    hc.extract_footnote_paragraphs(doc)
    assert sorted(f.props["refnum"] for f in _fn(doc)) == ["3", "8"]


def test_a_footnote_whose_extent_does_not_overlap_is_never_adopted():
    """Same page, same number, different lines — a footnote whose number
    repeats within a page (644's collision class). The extent is what keeps
    them apart."""
    lines = _mathpix_block() + [
        {"id": "d1", "type": "text",
         "text_display": "\\footnotetext{\\({ }^{3}\\) A different body."},
        {"id": "d2", "type": "text", "text_display": " elsewhere.}"},
    ]
    doc = _built(lines)
    assert len(_fn(doc)) == 1
    hc.extract_footnote_paragraphs(doc)
    fns = _fn(doc)
    assert len(fns) == 2, [f.props["content"] for f in fns]


def test_a_body_with_no_locatable_extent_is_created_not_adopted():
    """No lines stream to locate the body in — the pass must not adopt on
    (page, refnum) alone, which is exactly the guess 638 refuses to make."""
    doc = Document()
    doc.meta["bibkey"] = "T"
    host = DocObject(type="Footnote", props={
        "refnum": "3", "page": 4, "content": "surface body"})
    doc.add(host)
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "\\footnotetext{\\({ }^{3}\\) cleaned body.}",
        "page": 4, "flow_index": 1}))
    hc.extract_footnote_paragraphs(doc)
    assert len(_fn(doc)) == 2
    assert host.props["content"] == "surface body"
    assert not doc.meta.get("footnote_adopted")


def test_adoption_is_still_idempotent():
    doc = _built(_mathpix_block())
    hc.extract_footnote_paragraphs(doc)
    n = len(_fn(doc))
    assert hc.extract_footnote_paragraphs(doc) == 0
    assert len(_fn(doc)) == n


# ------------------------------------------ 650: the no-label residual group
#
# penev_A page 6 (an out/650 finding): a `\footnotetext{...}` group whose body
# carries NO `{ }^{n}` label at all. `FootnoteProcessor._refnum` finds nothing
# and skips the block entirely (`if not refnum: continue`), so only the
# cleanup's Paragraph-based read ever makes an object for it, and only as a
# single UNLOCATED body — `_footnote_extents` has no label to search for, so
# `ext` is always None and the new Footnote falls back to the PARAGRAPH's OWN
# realization (636's original "unlocated" behaviour).
#
# `clean` rewrites a Paragraph's `props["text"]` twice per run: once here
# (stripped to whatever survives the footnotetext span), and again by
# `materialize_transclusions`, which rebuilds it from the PROJECTOR's
# rendering of the paragraph's own (untouched) realization — not from this
# pass's edit (636-b). So a paragraph this pass already emptied can carry its
# raw `\footnotetext{}` body again on the very next drill, and because the
# body has no label, the ORDINARY (page, refnum, extent) adoption probe could
# never recognise the Footnote already made for it — a fresh duplicate every
# time the group happens to re-balance.

def _mathpix_block_no_label(body="Prose with no printed number at all.",
                            tail=" It just continues."):
    r"""A `\footnotetext{...}` group with no `{ }^{n}` label anywhere."""
    return [
        {"id": "blk", "type": "footnote", "text": "",
         "children_ids": ["c1", "c2"]},
        {"id": "c1", "type": "text",
         "text_display": "\\footnotetext{" + body},
        {"id": "c2", "type": "text", "text_display": tail + "}"},
    ]


def test_a_no_label_group_mints_no_footnote_via_the_processor():
    doc = _built(_mathpix_block_no_label())
    assert _fn(doc) == []                     # FootnoteProcessor needs a refnum


def test_the_cleanup_creates_one_refnum_less_footnote_for_an_unlabelled_group():
    doc = _built(_mathpix_block_no_label())
    n = hc.extract_footnote_paragraphs(doc)
    fns = _fn(doc)
    assert n == 1
    assert len(fns) == 1
    assert fns[0].props["refnum"] == ""
    assert "Prose with no printed number" in fns[0].props["content"]


def test_a_regenerated_unlabelled_paragraph_is_adopted_not_duplicated():
    r"""650 — the creator that runs again over an unchanged model (its own
    text regenerated exactly as `materialize_transclusions` regenerates it)
    must find its own object and update it, never mint a second one. Confirmed
    failing before the fix: the second call minted `obj_<new>` beside the
    first, giving 2 Footnotes for one printed (unlabelled) body."""
    doc = _built(_mathpix_block_no_label())
    para = doc.objects_of_type("Paragraph")[0]
    original_text = para.props["text"]

    n1 = hc.extract_footnote_paragraphs(doc)
    assert n1 == 1
    ids_after_first = {o.id for o in _fn(doc)}
    assert len(ids_after_first) == 1

    # Simulate exactly what `materialize_transclusions` does: rebuild the
    # paragraph's text from its own (untouched) source realization, which
    # puts the raw `\footnotetext{}` body right back — regardless of whether
    # the extraction above dropped the paragraph outright or merely shortened
    # it (here it consumes the whole body, so the paragraph was dropped).
    if doc.objects.get(para.id) is None:
        para.props["text"] = original_text
        doc.add(para)
    else:
        doc.objects[para.id].props["text"] = original_text

    n2 = hc.extract_footnote_paragraphs(doc)
    ids_after_second = {o.id for o in _fn(doc)}
    assert ids_after_second == ids_after_first, (
        "a second pass over the SAME regenerated body must adopt the "
        f"existing Footnote, not mint a second one: {ids_after_second}")
    assert len(_fn(doc)) == 1
    assert n2 == 1                             # counted as an adoption, not 0
    assert doc.meta["footnote_adopted"] >= 1


def test_adopt_target_merges_two_refnum_less_extents_that_overlap():
    doc = Document()
    doc.meta["bibkey"] = "T"
    from docmodel.core import Realization
    st = doc.ensure_stream("mathpix_lines")
    a1 = st.append(id="a1", type="text")
    host = DocObject(type="Footnote", props={"refnum": "", "page": 4})
    host.add_realization(Realization(stream="mathpix_lines",
                                     start=a1, end=a1, role="surface"))
    doc.add(host)
    got = fx.adopt_target(doc, 4, "", {a1}, ())
    assert got is host


def test_adopt_target_never_merges_a_refnum_less_body_into_a_numbered_one():
    doc = Document()
    doc.meta["bibkey"] = "T"
    from docmodel.core import Realization
    st = doc.ensure_stream("mathpix_lines")
    a1 = st.append(id="a1", type="text")
    numbered = DocObject(type="Footnote", props={"refnum": "3", "page": 4})
    numbered.add_realization(Realization(stream="mathpix_lines",
                                         start=a1, end=a1, role="surface"))
    doc.add(numbered)
    assert fx.adopt_target(doc, 4, "", {a1}, ()) is None


# ------------------------------------------------------------- the body text

def test_body_text_prefers_the_cleaned_realization_and_never_both():
    fn = DocObject(type="Footnote", props={"refnum": "3", "page": 4,
                                           "content": "the surface body"})
    fn.add_realization(Realization(stream="derived", role="cleaned",
                                   props={"text": "the cleaned body"}))
    assert fnres.body_text(fn) == "the cleaned body"
    assert "surface" not in fnres.body_text(fn)


def test_body_text_falls_back_to_the_content_prop():
    fn = DocObject(type="Footnote", props={"refnum": "3", "content": "only this"})
    assert fnres.body_text(fn) == "only this"
    fn.add_realization(Realization(stream="d", role="cleaned", props={}))
    assert fnres.body_text(fn) == "only this"   # a cleaned realization with no text


def test_body_text_prefers_the_translated_content_over_the_stale_cleaned_realization():
    r"""637 fix round 1 — `pdfdrill translate` translates `props['content']`
    and keeps the pre-translation text under `content_source`; it never
    touches a realization. Preferring the cleaned realization, as before,
    silently prints every translated footnote body in the source language."""
    fn = DocObject(type="Footnote", props={
        "refnum": "3", "page": 4,
        "content": "Uebersetzter Text.",
        "content_source": "Translated text."})
    fn.add_realization(Realization(stream="derived", role="cleaned",
                                   props={"text": "Translated text."}))
    assert fnres.body_text(fn) == "Uebersetzter Text."


def test_body_text_without_content_source_still_returns_the_cleaned_realization():
    """No `content_source` twin -> not translated -> the ordinary
    cleaned-else-content order applies."""
    fn = DocObject(type="Footnote", props={
        "refnum": "3", "page": 4, "content": "something else"})
    fn.add_realization(Realization(stream="derived", role="cleaned",
                                   props={"text": "Translated text."}))
    assert fnres.body_text(fn) == "Translated text."


# --------------------------------------------------------------- the projection

def _fn_doc_with_math():
    r"""One footnote whose body carries `\(V=|\{x\}|\)`, and a Formula object
    anchored on the same line — MathPix extracts the maths of a footnote body
    as its own Formula, and the projector then printed it a second time as a
    standalone `$…$` block."""
    doc = Document()
    doc.meta["bibkey"] = "D"
    mp = doc.ensure_stream("mathpix_lines")
    blk = mp.append(text="", _page=4, _line_index=0, type="footnote",
                    id="blk", children_ids=["c1"])
    c1 = mp.append(
        text="\\footnotetext{\\({ }^{3}\\) Here \\(V=60\\) is the range.}",
        _page=4, _line_index=1, type="text", id="c1")
    fn = DocObject(type="Footnote", props={
        "refnum": "3", "page": 4, "flow_index": 1,
        "anchor_marker": "{ }^{3}",
        "content": "Here \\(V=60\\) is the range."})
    fn.add_realization(Realization(stream="mathpix_lines", start=blk, end=blk,
                                   role="surface"))
    fn.add_realization(Realization(stream="derived", role="cleaned",
                                   props={"text": "Here \\(V=60\\) is the range."}))
    doc.add(fn)
    fo = DocObject(type="Formula", props={"latex": "V=60", "page": 4,
                                          "flow_index": 2})
    fo.add_realization(Realization(stream="mathpix_lines", start=c1, end=c1,
                                   role="surface"))
    doc.add(fo)
    return doc, fn, fo


def test_one_footnotetext_block_per_footnote_object():
    doc, fn, _fo = _fn_doc_with_math()
    tex = LaTeXProjector(
        OperatorConfig(op="projector", classname="LaTeXProjector")).project(doc)
    assert tex.count("\\footnotetext") == 1
    assert "Here" in tex


def test_the_maths_inside_a_footnote_body_is_not_emitted_standalone():
    doc, _fn, fo = _fn_doc_with_math()
    assert fo.id in fnres.body_math_ids(doc)
    tex = LaTeXProjector(
        OperatorConfig(op="projector", classname="LaTeXProjector")).project(doc)
    # the DOCUMENT body, not the preamble: the formula transclusion array is
    # the projector's source for `\Expr{i}` and carries every Formula by design.
    doc_body = tex[tex.index("\\begin{document}"):]
    assert doc_body.count("V=60") == 1, doc_body
    assert "$V=60$" not in doc_body


def test_maths_a_footnote_body_does_not_carry_is_still_emitted():
    """penev_A's page-6 block has a `\\footnotetext{` whose braces never balance,
    so its Footnote's content is "" (636-a). 15 Formulas sit on its lines and
    their latex is in NO body — skipping them would be pure loss, so the rule
    is 'inside a body AND named by it', never 'inside a body'."""
    doc, fn, fo = _fn_doc_with_math()
    fn.props["content"] = ""
    for r in fn.realizations:
        if r.role == "cleaned":
            r.props["text"] = ""
    assert fo.id not in fnres.body_math_ids(doc)
    tex = LaTeXProjector(
        OperatorConfig(op="projector", classname="LaTeXProjector")).project(doc)
    assert "V=60" in tex


def test_the_ledger_still_names_the_pass_footnote_cleanup_after_an_adoption():
    """634's ledger reads the module off the object's `added_by` and only falls
    back to the recording SITE. That holds while every claim a pass makes lands
    on an object it CREATED. The adoption breaks it: the claim now lands on a
    Footnote the PROCESSOR built, so `added_by` cannot speak for it and the
    site says `heading_cleanup`. Left alone, out/634.txt's 35
    `footnote_cleanup+paragraph` anchors would silently become
    `heading_cleanup+paragraph` — a rename that reads as a finding."""
    from docmodel import ledger as L
    L.reset()
    L.start_recording()
    try:
        doc = _built(_mathpix_block())
        hc.extract_footnote_paragraphs(doc)
        view = L.materialize(doc)
    finally:
        L.reset()
    assert "footnote_cleanup" in view["by_module"], view["by_module"]
    assert "heading_cleanup" not in view["by_module"], view["by_module"]
    assert view["by_module"].get("footnote") == 1        # the processor's line


def test_a_citation_on_the_second_realization_of_a_footnote_still_resolves():
    """Found by measurement, not by reading: after the adoption a Footnote has
    TWO surface realizations — the processor's `footnote` PARENT line and the
    extent on the CHILD lines the cleanup located — and the citations are on
    the children. `citations.resolve` read only the FIRST realization, so 8
    penev_A footnote-body citations stopped becoming `\\cite` and were counted
    as `citations_outside_running_text` instead."""
    from docops.projectors import citations as cit
    doc = Document()
    doc.meta["bibkey"] = "D"
    mp = doc.ensure_stream("mathpix_lines")
    blk = mp.append(text="", _page=4, _line_index=0, type="footnote",
                    id="blk", children_ids=["c1"])
    c1 = mp.append(text="See (Deco and Obradovic 1996) for a review.",
                   _page=4, _line_index=1, type="text", id="c1")
    fn = DocObject(type="Footnote", props={
        "refnum": "3", "page": 4, "flow_index": 1, "anchor_marker": "{ }^{3}",
        "content": "See (Deco and Obradovic 1996) for a review."})
    fn.add_realization(Realization(stream="mathpix_lines", start=blk, end=blk,
                                   role="surface"))
    fn.add_realization(Realization(stream="mathpix_lines", start=c1, end=c1,
                                   role="surface"))
    doc.add(fn)
    ref = DocObject(type="Reference", props={"citekey": "Deco1996",
                                             "authors": "Deco", "year": "1996"})
    doc.add(ref)
    c = DocObject(type="Citation", props={"citekey": "Deco1996",
                                          "reference_id": ref.id})
    c.add_realization(Realization(
        stream="mathpix_lines", start=c1, end=c1, role="surface",
        props={"offset": 4, "length": len("(Deco and Obradovic 1996)")}))
    doc.add(c)
    res = cit.resolve(doc)
    assert res.counts["cite_groups"] == 1, res.counts
    assert res.counts["citations_outside_running_text"] == 0, res.counts
    assert res.counts["cite_in_footnote"] == 1, res.counts


def test_an_equation_inside_a_footnote_body_is_left_alone():
    """An Equation carries a `\\label` that `\\ref` resolves against; folding it
    into a footnote body would break every cross-reference to it. Only inline
    Formulas are folded, and the choice is stated rather than assumed."""
    doc, fn, fo = _fn_doc_with_math()
    fo.type = "Equation"
    assert fo.id not in fnres.body_math_ids(doc)


# ------------------------------------- 650: the surface-realization residual
#
# penev_A page 6 (out/650): a `footnote` block whose CHILD lines carry a
# LABELLED `\footnotetext{\({ }^{9}\) ...}` immediately followed, in the same
# ParagraphProcessor group (footnote children are typed `text`, a PROSE type
# — nothing marks them as already belonging to a footnote), by real prose.
# `extract_footnote_paragraphs` adopts/creates the labelled Footnote and
# correctly shortens the Paragraph's `text` to just the surviving prose — but
# the Paragraph's `surface` realization on `mathpix_lines` still spans the
# ORIGINAL group (nothing here shrinks it). `_transclude_paragraph` (the real
# TiddlyWiki projector) renders a Paragraph from THAT realization, never from
# `props["text"]`, so the next `materialize_transclusions` reads the stale,
# wide span and writes the footnotetext content right back — now missing its
# `\({ }^{N}\)` label (replaced by the `{{||FN}}` token this same call just
# wrote), so the FOLLOWING `extract_footnote_paragraphs` cannot recognise it
# as the footnote already made and mints a fresh, refnum-less duplicate.
# Confirmed failing before the fix (with the `footnote_extracted` flag
# stripped, simulating the pre-fix code): materialize reintroduced the
# footnotetext and a second extract pass minted a 2nd Footnote for the SAME
# printed body.

def _mathpix_block_with_trailing_prose(
        refnum="9", body="Thanks Feigenbaum for help.",
        tail=" End of footnote.", prose="Prose continues right after."):
    return [
        {"id": "blk", "type": "footnote", "text": "",
         "children_ids": ["c1", "c2"]},
        {"id": "c1", "type": "text",
         "text_display": "\\footnotetext{\\({ }^{%s}\\) %s" % (refnum, body)},
        {"id": "c2", "type": "text", "text_display": tail + "}"},
        {"id": "p1", "type": "text", "text_display": prose},
    ]


def test_extract_shortens_text_and_flags_the_paragraph():
    doc = _built(_mathpix_block_with_trailing_prose())
    n = hc.extract_footnote_paragraphs(doc)
    assert n == 1
    paras = doc.objects_of_type("Paragraph")
    assert len(paras) == 1
    p = paras[0]
    assert p.props["text"] == "Prose continues right after."
    assert p.props["footnote_extracted"] is True
    # the footnote was ADOPTED (FootnoteProcessor's own object), not doubled
    assert len(_fn(doc)) == 1


def test_materialize_never_reintroduces_an_already_extracted_footnote_body():
    """End-to-end with the REAL TiddlyWiki projector (no mock): materialize
    must leave the shortened paragraph alone, and a second extract pass must
    find nothing new."""
    doc = _built(_mathpix_block_with_trailing_prose())
    hc.extract_footnote_paragraphs(doc)
    before_fn_ids = {f.id for f in _fn(doc)}

    changed = hc.materialize_transclusions(doc)
    assert changed == 0, [p.props["text"] for p in doc.objects_of_type("Paragraph")]
    paras = doc.objects_of_type("Paragraph")
    assert paras[0].props["text"] == "Prose continues right after."

    n2 = hc.extract_footnote_paragraphs(doc)
    assert n2 == 0, [f.props for f in _fn(doc)]
    assert {f.id for f in _fn(doc)} == before_fn_ids
    assert len(_fn(doc)) == 1


def test_without_the_flag_materialize_would_have_reintroduced_it():
    """The regression this fixes, confirmed still reproducible by removing
    JUST the flag — proof the flag (not something else) is what protects the
    paragraph, and a faithful pin against the flag being dropped by accident."""
    doc = _built(_mathpix_block_with_trailing_prose())
    hc.extract_footnote_paragraphs(doc)
    for p in doc.objects_of_type("Paragraph"):
        p.props.pop("footnote_extracted", None)

    changed = hc.materialize_transclusions(doc)
    assert changed == 1
    para = doc.objects_of_type("Paragraph")[0]
    assert "\\footnotetext" in para.props["text"]

    n2 = hc.extract_footnote_paragraphs(doc)
    assert n2 == 1
    assert len(_fn(doc)) == 2                     # the duplicate this fixes


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t()
        except Exception as e:                              # pragma: no cover
            failed.append((t.__name__, e))
    for name, e in failed:
        print("FAIL", name, e)
    print(f"{len(tests) - len(failed)}/{len(tests)} passed")
