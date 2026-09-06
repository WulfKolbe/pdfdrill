"""645 — citations reach the page, and the integrity check sees a REF
tiddler nothing points at.

Three defects, one class. A citation GROUP (`[a, b]`, `(Smith 1999; Jones
2001)`) is recorded by every one of the three `bibliography.py` detectors as
N Citation objects sharing ONE span — the span of the whole group — so the
projector's overlap rule accepts one and drops the rest, and the REF tiddlers
behind the dropped keys are never linked from any paragraph. `tiddler_integrity`
could not see that: it counted a SYNTHETIC (FOX) tiddler nobody points at as an
orphan and nothing else, so 12 of 52 unlinked REF tiddlers on penev_A reported
as "0 dangling, 0 orphan". And a stub Reference, anchored at its citation's
line with a plain surface Realization, CLAIMED that line — 37 doubly-claimed
Paragraph+Reference anchors on penev_A (646-g).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization
from docops.base import OperatorConfig
from docops.projectors.tiddlywiki import TiddlyWikiProjector, tiddler_integrity


# ---------------------------------------------------------------- fixtures

LINE = "Prior work [a, b] shows this."
SPAN = (LINE.index("["), len("[a, b]"))


def _grouped_citation_doc() -> Document:
    """One paragraph carrying the citation group `[a, b]`, two Citation
    objects at the SAME span (what every detector records for a group), and
    the two stub References 639 guarantees exist behind them."""
    doc = Document()
    doc.meta["bibkey"] = "D"
    mp = doc.ensure_stream("mathpix_lines")
    head = mp.append(text="1 Introduction", _page=1, _line_index=0,
                     type="section_header")
    body = mp.append(text=LINE, _page=1, _line_index=1, type="text")

    sec = DocObject(type="Section", props={
        "caption": "Introduction", "level": 1, "flow_index": 0, "page": 1})
    sec.add_realization(Realization(stream="mathpix_lines",
                                    start=head, end=head, role="surface"))
    doc.add(sec)

    par = DocObject(type="Paragraph", props={
        "text": LINE, "page": 1, "flow_index": 1})
    par.add_realization(Realization(stream="mathpix_lines",
                                    start=body, end=body, role="surface"))
    doc.add_child(sec, par)

    for i, key in enumerate(("a", "b")):
        cit = DocObject(type="Citation", props={
            "citekey": key, "page": 1, "flow_index": 2 + i})
        cit.add_realization(Realization(
            stream="mathpix_lines", start=body, end=body, role="surface",
            props={"offset": SPAN[0], "length": SPAN[1]}))
        doc.add(cit)
        ref = DocObject(type="Reference", props={
            "citekey": key, "bibkey": "D", "stub": True,
            "ref_source": "citation"})
        ref.add_realization(Realization(
            stream="mathpix_lines", start=body, end=body, role="surface",
            props={"offset": SPAN[0], "length": SPAN[1]}))
        doc.add(ref)
    return doc


def _project(doc) -> list[dict]:
    proj = TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector"))
    return json.loads(proj.project(doc))


def _para_text(tiddlers) -> str:
    return next(t["text"] for t in tiddlers if t["title"] == "D_PARA_0001")


# ------------------------------------------- 1. the group reaches the prose

def test_a_citation_group_transcludes_one_ref_per_key_in_order():
    """`[a, b]` -> `{{D_REF_a||CIT}}{{D_REF_b||CIT}}`.

    Before 645 the two Citations share one span, `_apply_line_substitutions`
    drops the second as an overlap, and `D_REF_b` is linked from nothing.
    """
    text = _para_text(_project(_grouped_citation_doc()))
    assert "{{D_REF_a||CIT}}" in text, text
    assert "{{D_REF_b||CIT}}" in text, text
    assert text.index("{{D_REF_a||CIT}}") < text.index("{{D_REF_b||CIT}}"), text


def test_the_group_brackets_are_consumed_not_doubled():
    """The CIT template renders `[<$link …>key</$link>]` — it SUPPLIES the
    brackets. The source `[a, b]` must be replaced whole, or the reader gets
    `[[a][b]]`."""
    text = _para_text(_project(_grouped_citation_doc()))
    assert "[a, b]" not in text, text
    assert "Prior work {{D_REF_a||CIT}}{{D_REF_b||CIT}} shows this." in text, text


def test_a_repeated_key_in_one_group_is_transcluded_once():
    doc = _grouped_citation_doc()
    body = doc.streams["mathpix_lines"].anchors[1]
    dup = DocObject(type="Citation", props={
        "citekey": "a", "page": 1, "flow_index": 4})
    dup.add_realization(Realization(
        stream="mathpix_lines", start=body, end=body, role="surface",
        props={"offset": SPAN[0], "length": SPAN[1]}))
    doc.add(dup)
    text = _para_text(_project(doc))
    assert text.count("{{D_REF_a||CIT}}") == 1, text


# --------------------------------------------- 2. the integrity check sees it

def test_tiddler_integrity_reports_no_orphan_ref_when_every_key_is_linked():
    report = tiddler_integrity(_project(_grouped_citation_doc()))
    assert report["orphan_ref"] == [], report["orphan_ref"]
    assert report["unreferenced"] == [], report["unreferenced"]
    # the counts kept from before 645 are unchanged
    assert report["dangling"] == [] and report["orphan_synthetic"] == []


def test_tiddler_integrity_reports_a_ref_tiddler_nothing_points_at():
    """Remove one transclusion from the prose and the check must name it.

    This is exactly penev_A's shape: the REF tiddler EXISTS (so nothing
    dangles) and no text names it (so `orphan_synthetic`, which only looks at
    `synthetic` tiddlers, cannot see it).
    """
    tiddlers = _project(_grouped_citation_doc())
    for t in tiddlers:
        if t["title"] == "D_PARA_0001":
            t["text"] = t["text"].replace("{{D_REF_b||CIT}}", "")
    report = tiddler_integrity(tiddlers)
    assert report["orphan_ref"] == ["D_REF_b"], report["orphan_ref"]
    assert report["dangling"] == [], report["dangling"]
    assert "D_REF_b" in report["unreferenced"], report["unreferenced"]
    assert report["unreferenced_by_prefix"] == {"REF": 1}, \
        report["unreferenced_by_prefix"]


def test_unreferenced_reports_any_non_text_non_template_tiddler_by_prefix():
    """A Formula tiddler nobody transcludes is the same class of loss."""
    doc = _grouped_citation_doc()
    body = doc.streams["mathpix_lines"].anchors[1]
    fo = DocObject(type="Formula", props={
        "latex": "x^2", "page": 1, "flow_index": 5})
    # NO offset/length: nothing substitutes it into any paragraph, so the
    # tiddler is emitted and named by nobody.
    fo.add_realization(Realization(stream="mathpix_lines", start=body,
                                   end=body, role="surface"))
    doc.add(fo)
    report = tiddler_integrity(_project(doc))
    assert report["unreferenced"] == ["D_FO0001"], report["unreferenced"]
    assert report["unreferenced_by_prefix"] == {"FO": 1}, \
        report["unreferenced_by_prefix"]
    # a Paragraph/Section/Page tiddler is TEXT and is never reported here
    assert not any(t.startswith("D_PARA") or t.startswith("D_H")
                   for t in report["unreferenced"]), report["unreferenced"]


# -------------------------------------- 3. the stub does not claim its line

def test_a_reference_stub_does_not_claim_the_line_its_citation_sits_in():
    """646-g. `ensure_reference_stub` anchors the stub at the CITING prose
    line; with a plain surface Realization that line is claimed by the
    Paragraph AND by the stub — 37 doubly-claimed anchors on penev_A. The
    stub is inline like its citation, so it carries the citation's own
    offset/length sub-anchor."""
    from docmodel.modules.citation import ensure_reference_stub
    from docops.conserve import anchor_claims

    doc = Document()
    doc.meta["bibkey"] = "D"
    mp = doc.ensure_stream("mathpix_lines")
    body = mp.append(text=LINE, _page=1, _line_index=0, type="text")
    par = DocObject(type="Paragraph", props={"text": LINE, "page": 1,
                                             "flow_index": 0})
    par.add_realization(Realization(stream="mathpix_lines", start=body,
                                    end=body, role="surface"))
    doc.add(par)
    cit = DocObject(type="Citation", props={"citekey": "a", "page": 1,
                                            "flow_index": 1})
    cit.add_realization(Realization(
        stream="mathpix_lines", start=body, end=body, role="surface",
        props={"offset": SPAN[0], "length": SPAN[1]}))
    doc.add(cit)

    ref = ensure_reference_stub(doc, cit, "D")
    assert ref is not None
    claims = anchor_claims(doc)
    assert claims["doubly_claimed"] == [], claims["doubly_claimed"]
    assert claims["pairs"] == {} or "Reference" not in str(claims["pairs"])
    # the stub is still ANCHORED — it just does not claim the whole line
    r = next(x for x in ref.realizations if x.role == "surface")
    assert r.start == body
    assert r.props.get("offset") == SPAN[0] and r.props.get("length") == SPAN[1]


# ------------------------------------- 4. the detector records a real span

def test_detect_author_year_in_objects_records_the_span_on_the_right_line():
    """The offset a detector records must be a position in the LINE its
    realization anchors, not in the object's own joined text. Rule 5: a span
    that cannot be located is not recorded at all, never guessed.
    """
    from pdfdrill import bibliography as B

    doc = Document()
    doc.meta["bibkey"] = "D"
    mp = doc.ensure_stream("mathpix_lines")
    l0 = mp.append(text="Some earlier prose that fills the first line.",
                   _page=1, _line_index=0, type="text")
    l1 = mp.append(text="and then (Smith 1999) closes it.",
                   _page=1, _line_index=1, type="text")
    par = DocObject(type="Paragraph", props={
        "text": "Some earlier prose that fills the first line. "
                "and then (Smith 1999) closes it.",
        "page": 1, "flow_index": 0})
    par.add_realization(Realization(stream="mathpix_lines", start=l0,
                                    end=l1, role="surface"))
    doc.add(par)

    assert B.detect_author_year_in_objects(doc) == 1
    cit = doc.objects_of_type("Citation")[0]
    r = next(x for x in cit.realizations if x.role == "surface")
    assert r.start == l1, "the span must name the line the group is ON"
    line = mp.payload[l1]["text"]
    off, length = r.props["offset"], r.props["length"]
    assert line[off:off + length] == "(Smith 1999)", line[off:off + length]


def test_a_span_that_cannot_be_located_is_left_unrecorded_and_counted():
    """An object whose text no line reproduces (a mutator rewrote it) must
    not get a fabricated offset. The citation is still created; it carries
    no sub-anchor, and `spans_unrecorded` says so."""
    from pdfdrill import bibliography as B

    doc = Document()
    doc.meta["bibkey"] = "D"
    mp = doc.ensure_stream("mathpix_lines")
    l0 = mp.append(text="raw ocr line that does not contain the group",
                   _page=1, _line_index=0, type="text")
    par = DocObject(type="Paragraph", props={
        "text": "rewritten prose (Smith 1999) here", "page": 1,
        "flow_index": 0})
    par.add_realization(Realization(stream="mathpix_lines", start=l0,
                                    end=l0, role="surface"))
    doc.add(par)

    assert B.detect_author_year_in_objects(doc) == 1
    assert B.spans_unrecorded(doc) == 1
    cit = doc.objects_of_type("Citation")[0]
    r = next((x for x in cit.realizations if x.role == "surface"), None)
    assert r is None or r.props.get("offset") is None, r
