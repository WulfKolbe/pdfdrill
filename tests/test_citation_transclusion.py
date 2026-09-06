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
#: each key's OWN span, which is what the detectors record after 645 fix
#: round 1. `SPAN` is the whole bracket — the shape a stub Reference inherits
#: and the shape the pre-645 detectors recorded on every key in a group.
SPAN_A = (LINE.index("[a") + 1, 1)
SPAN_B = (LINE.index("b]"), 1)
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

    for i, (key, span) in enumerate((("a", SPAN_A), ("b", SPAN_B))):
        cit = DocObject(type="Citation", props={
            "citekey": key, "page": 1, "flow_index": 2 + i})
        cit.add_realization(Realization(
            stream="mathpix_lines", start=body, end=body, role="surface",
            props={"offset": span[0], "length": span[1]}))
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
    # LOSSLESS: the `, ` between the keys is kept; only the two recognised
    # spans and the bracket pair that wraps nothing else are replaced.
    assert "Prior work {{D_REF_a||CIT}}, {{D_REF_b||CIT}} shows this." in text, \
        text


def test_a_repeated_key_in_one_group_is_transcluded_once():
    doc = _grouped_citation_doc()
    body = doc.streams["mathpix_lines"].anchors[1]
    dup = DocObject(type="Citation", props={
        "citekey": "a", "page": 1, "flow_index": 4})
    dup.add_realization(Realization(
        stream="mathpix_lines", start=body, end=body, role="surface",
        props={"offset": SPAN_A[0], "length": SPAN_A[1]}))
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
    # the KEY's own extent, not the whole parenthetical — a shared span makes
    # the projector replace the group as one blob (see the Földiák test)
    assert line[off:off + length] == "Smith 1999", line[off:off + length]


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
    # NO realization at all. A `surface` Realization with no sub-anchor is a
    # CLAIM on every line the paragraph covers, and `ensure_reference_stub`
    # would copy that claim onto the stub — undoing 646-g on the path 645
    # created. So the stub is not made either.
    assert cit.realizations == [], cit.realizations
    assert doc.objects_of_type("Reference") == []


def test_a_group_keeps_the_text_no_key_covers():
    """LOSSLESS. `(Linsker 1988; Oja 1989; Földiák 1990; Plumbey 1991)` is
    the real penev_A line: `Földiák` never becomes a Citation, because
    `detect_author_year_citations`'s surname class is ASCII-only (645-b). A
    substitution that replaced the whole parenthetical would DELETE a
    reference the document actually makes. Every character between the
    recognised spans is emitted verbatim.
    """
    line = "as in (Linsker 1988; Oja 1989; Földiák 1990; Plumbey 1991) above."
    doc = Document()
    doc.meta["bibkey"] = "D"
    mp = doc.ensure_stream("mathpix_lines")
    head = mp.append(text="1 Introduction", _page=1, _line_index=0,
                     type="section_header")
    body = mp.append(text=line, _page=1, _line_index=1, type="text")
    sec = DocObject(type="Section", props={"caption": "Introduction",
                                           "level": 1, "flow_index": 0})
    sec.add_realization(Realization(stream="mathpix_lines", start=head,
                                    end=head, role="surface"))
    doc.add(sec)
    par = DocObject(type="Paragraph", props={"text": line, "page": 1,
                                             "flow_index": 1})
    par.add_realization(Realization(stream="mathpix_lines", start=body,
                                    end=body, role="surface"))
    doc.add_child(sec, par)
    for i, key in enumerate(("Linsker 1988", "Oja 1989", "Plumbey 1991")):
        ck = key.replace(" ", "")
        cit = DocObject(type="Citation", props={
            "citekey": ck, "page": 1, "flow_index": 2 + i})
        cit.add_realization(Realization(
            stream="mathpix_lines", start=body, end=body, role="surface",
            props={"offset": line.index(key), "length": len(key)}))
        doc.add(cit)
        ref = DocObject(type="Reference", props={"citekey": ck, "bibkey": "D",
                                                 "stub": True})
        ref.add_realization(Realization(
            stream="mathpix_lines", start=body, end=body, role="surface",
            props={"offset": line.index(key), "length": len(key)}))
        doc.add(ref)

    text = _para_text(_project(doc))
    assert "Földiák 1990" in text, text
    assert ("as in ({{D_REF_Linsker1988||CIT}}; {{D_REF_Oja1989||CIT}}; "
            "Földiák 1990; {{D_REF_Plumbey1991||CIT}}) above.") in text, text
    # the parentheses are KEPT here: they wrap text no key covers, so
    # swallowing them would drop characters too.


def test_a_span_the_line_is_too_short_for_is_dropped_not_clamped():
    """A clamped span replaces the wrong characters and says nothing."""
    doc = _grouped_citation_doc()
    body = doc.streams["mathpix_lines"].anchors[1]
    for c in doc.objects_of_type("Citation"):
        if c.props.get("citekey") == "b":
            c.realizations[0].props["offset"] = len(LINE) + 5
    proj = TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector"))
    tiddlers = json.loads(proj.project(doc))
    text = next(t["text"] for t in tiddlers if t["title"] == "D_PARA_0001")
    assert proj.counters.get("citation_span_out_of_bounds") == 1
    assert "{{D_REF_b||CIT}}" not in text, text
    # the in-bounds key is unaffected, and it does NOT swallow `b]` with it
    assert "{{D_REF_a||CIT}}, b]" in text, text


def test_the_kept_characters_are_counted():
    proj = TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector"))
    json.loads(proj.project(_grouped_citation_doc()))
    assert proj.counters.get("group_text_kept") == len(", "), proj.counters


def test_end_to_end_the_real_penev_A_line_keeps_the_unrecognised_reference():
    """The defect exactly as the corpus has it, through the real detector.

    Before 645 fix round 1 `detect_author_year_citations` gave all four keys
    the span of the WHOLE parenthetical, so the projector replaced it entire
    and `Földiák 1990` — a reference the paper makes, which no detector
    recognises because the surname class is ASCII-only (645-b) — was deleted
    from the page along with the semicolons.
    """
    from pdfdrill import bibliography as B

    line = ("Principal Component Analysis (Linsker 1988; Oja 1989; "
            "Sanger 1989; Földiák 1990; Plumbey 1991), and so on.")
    doc = Document()
    doc.meta["bibkey"] = "D"
    mp = doc.ensure_stream("mathpix_lines")
    head = mp.append(text="1 Introduction", _page=1, _line_index=0,
                     type="section_header")
    body = mp.append(text=line, _page=1, _line_index=1, type="text")
    sec = DocObject(type="Section", props={"caption": "Introduction",
                                           "level": 1, "flow_index": 0})
    sec.add_realization(Realization(stream="mathpix_lines", start=head,
                                    end=head, role="surface"))
    doc.add(sec)
    par = DocObject(type="Paragraph", props={"text": line, "page": 1,
                                             "flow_index": 1})
    par.add_realization(Realization(stream="mathpix_lines", start=body,
                                    end=body, role="surface"))
    doc.add_child(sec, par)

    assert B.detect_author_year_citations(doc) == 4      # Földiák is missed
    assert B.spans_unrecorded(doc) == 0

    text = _para_text(_project(doc))
    assert "Földiák 1990" in text, text
    for key in ("Linsker1988", "Oja1989", "Sanger1989", "Plumbey1991"):
        assert "{{D_REF_%s||CIT}}" % key in text, text
    # the parenthetical is kept, because it wraps text no key covers
    assert "({{D_REF_Linsker1988||CIT}}; " in text, text
    assert "; Földiák 1990; {{D_REF_Plumbey1991||CIT}}), and so on." in text, text
