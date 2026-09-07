r"""641 — a superscript citation becomes `\cite`, and how it differs from a
footnote marker.

Both are the SAME inline maths: `\({ }^{7}\)`, an empty-base superscript
carrying nothing but a number. MathPix writes a numeric superscript citation
and a footnote reference identically, so the maths cannot tell them apart. The
DOCUMENT can:

  * a FOOTNOTE marker has a body on its own page — a `Footnote` object with
    that refnum whose page is the marker's page (638's rule, unchanged);
  * a CITATION superscript has a numbered `\bibitem` — a `Reference` whose
    `props["number"]` is that number — and no such body.

The order is fixed and the first rule that fires wins: the footnote body being
physically on the page is the stronger evidence, because a numbered reference
list and footnotes on the same page both exist. A marker that matches BOTH is a
footnote, and that case is COUNTED (`marker_both`) rather than smoothed over.

Rule (b) fires only when the reference list is NUMBERED at all: on an
author-year document (penev_A: 52 References, 0 with a `number`) it can never
fire, which is the designed outcome and not a failure.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization
from docops.base import OperatorConfig
from docops.projectors import footnotes as fnres
from docops.projectors.latex import LaTeXProjector


MARK7 = "\\({ }^{7}\\)"
LINE7 = f"Sparse coding{MARK7} predates the transform."


def _project(doc: Document) -> str:
    return LaTeXProjector(
        OperatorConfig(op="projector", classname="LaTeXProjector")).project(doc)


def _doc(*, numbered: bool = True, footnote_on_page: bool = False,
         refnum: str = "7") -> Document:
    """One paragraph on page 4 carrying `{ }^{<refnum>}`, a Reference numbered
    7 (`key7`), and optionally a Footnote with that refnum whose body is on
    page 4."""
    mark = f"\\({{ }}^{{{refnum}}}\\)"
    line = f"Sparse coding{mark} predates the transform."
    doc = Document()
    doc.meta["bibkey"] = "D"
    mp = doc.ensure_stream("mathpix_lines")
    head = mp.append(text="1 Coding", _page=4, _line_index=0,
                     type="section_header")
    body = mp.append(text=line, _page=4, _line_index=1, type="text")

    sec = DocObject(type="Section", props={
        "caption": "Coding", "level": 1, "flow_index": 0, "page": 4})
    sec.add_realization(Realization(stream="mathpix_lines",
                                    start=head, end=head, role="surface"))
    doc.add(sec)

    par = DocObject(type="Paragraph", props={
        "text": line, "page": 4, "flow_index": 1})
    par.add_realization(Realization(stream="mathpix_lines",
                                    start=body, end=body, role="surface"))
    doc.add_child(sec, par)

    if footnote_on_page:
        fnline = mp.append(text=f"\\footnotetext{{Body {refnum}.}}", _page=4,
                           _line_index=2, type="footnote")
        foot = DocObject(type="Footnote", props={
            "refnum": refnum, "anchor_marker": f"{{ }}^{{{refnum}}}",
            "page": 4, "content": f"Body {refnum}.", "flow_index": 2})
        foot.add_realization(Realization(stream="mathpix_lines",
                                         start=fnline, end=fnline,
                                         role="surface"))
        doc.add(foot)

    ref = DocObject(type="Reference", props={
        "citekey": "key7", "text": "A. Author, A paper, 1999.",
        "flow_index": 9})
    if numbered:
        ref.props["number"] = 7
    doc.add(ref)
    return doc


def _par(doc: Document) -> DocObject:
    return next(o for o in doc.objects.values() if o.type == "Paragraph")


# ───────────────────────────────────────────────────────────────── rule (b)

def test_a_marker_naming_a_numbered_bibitem_becomes_a_cite():
    """No footnote 7 anywhere; Reference 7 is `key7`. The superscript is a
    CITATION and must set as one."""
    doc = _doc()
    res = fnres.resolve(doc)
    marks = res.marks_for(_par(doc).id)
    assert len(marks) == 1
    assert marks[0].footnote_id is None
    assert marks[0].citekey == "key7"
    assert res.counts["markers_cited"] == 1
    assert res.counts["markers_unresolved"] == 0
    assert res.counts["marker_both"] == 0
    assert res.counts["references_numbered"] == 1

    tex = _project(doc)
    assert "\\cite{key7}" in tex, tex
    assert "{ }^{7}" not in tex, tex
    assert "\\bibitem{key7}" in tex, tex        # 639: the key cannot dangle


def test_the_cite_from_a_marker_is_inspectable_in_the_resolution_table():
    tex_res = fnres.resolve(_doc())
    rows = tex_res.table()["marks"]
    assert len(rows) == 1
    assert rows[0]["citekey"] == "key7"
    assert rows[0]["outcome"] == "cite"
    assert tex_res.table()["counts"]["markers_cited"] == 1


# ─────────────────────────────────────────────────── the disambiguation itself

def test_a_footnote_body_on_the_page_beats_a_numbered_bibitem():
    """The marker matches BOTH — footnote 7's body is on page 4 AND bibitem 7
    exists. The footnote wins (the body is physically there) and the collision
    is counted."""
    doc = _doc(footnote_on_page=True)
    res = fnres.resolve(doc)
    mark = res.marks_for(_par(doc).id)[0]
    assert mark.footnote_id is not None
    assert mark.citekey is None
    assert res.counts["marker_both"] == 1
    assert res.counts["markers_cited"] == 0
    assert res.counts["markers_resolved"] == 1

    tex = _project(doc)
    assert "\\footnotemark[7]" in tex, tex
    assert "\\footnotetext[7]{Body 7.}" in tex, tex
    assert "\\cite{key7}" not in tex, tex


def test_a_marker_matching_neither_stands_and_is_counted():
    """Marker 9: no footnote 9, no bibitem 9. It is left byte-for-byte."""
    doc = _doc(refnum="9")
    res = fnres.resolve(doc)
    mark = res.marks_for(_par(doc).id)[0]
    assert mark.footnote_id is None and mark.citekey is None
    assert res.counts["markers_unresolved"] == 1
    assert res.counts["markers_cited"] == 0

    tex = _project(doc)
    assert "\\({ }^{9}\\)" in tex, tex
    assert "\\cite{" not in tex, tex


def test_rule_b_never_fires_on_an_unnumbered_reference_list():
    """penev_A's shape: References exist and carry a citekey, none carries a
    printed `number`. A superscript cannot be a numeric citation in a document
    with no numeric citations, so the marker stands."""
    doc = _doc(numbered=False)
    res = fnres.resolve(doc)
    mark = res.marks_for(_par(doc).id)[0]
    assert mark.citekey is None
    assert res.counts["markers_cited"] == 0
    assert res.counts["references_numbered"] == 0
    assert res.counts["markers_unresolved"] == 1
    assert "\\({ }^{7}\\)" in _project(doc)


# ────────────────────────── the marker reaches the walk at all (brief item 2)

def test_a_bare_marker_is_no_formula_and_stays_in_the_paragraph_text():
    """`FormulaProcessor` refuses a bare `{ }^{n}` (`_is_footnote_marker`), and
    a marker it refuses must still be IN the paragraph's text — which is the
    text the resolver walks. Both halves in one test: a Formula would hide the
    marker from the walk, and a marker dropped from the text would too."""
    from docmodel.modules.page import ingest_lines_json, PageProcessor
    from docmodel.modules.formula import FormulaProcessor
    from docmodel.modules.paragraph import ParagraphProcessor
    from docmodel.base_module import ModuleConfig

    lines = {"pages": [{"page": 1, "image_id": "i", "lines": [
        {"id": "p1", "type": "text",
         "text": r"Sparse coding \({ }^{3}\) and the tensor \(x_{0}{ }^{2}\)."},
    ]}]}
    doc = Document()
    doc.meta["bibkey"] = "T"
    ingest_lines_json(doc, lines)
    for cls in (PageProcessor, FormulaProcessor, ParagraphProcessor):
        cls(ModuleConfig(title=cls.__name__,
                         classname=cls.__name__), "T").process_document(doc)

    formulas = [o.props.get("latex", "")
                for o in doc.objects.values() if o.type == "Formula"]
    assert not any(fnres.marker_refnum("\\(" + f + "\\)") is not None
                   for f in formulas), formulas
    assert any("{ }^{2}" in f for f in formulas), formulas   # the real exponent

    par = next(o for o in doc.objects.values() if o.type == "Paragraph")
    text = fnres.object_text(par)
    assert [rn for _s, _e, rn in fnres.find_markers(text)] == ["3"], text


# ───────────────────── fix round 1: the SAME rule behind the other spelling

def _doc_sup(*, numbered: bool = True, footnote_on_page: bool = False,
             n: str = "7") -> Document:
    """The MATERIALISED spelling of the same marker. After `clean`, a marker
    whose refnum named no Footnote is `<sup>N</sup>` in the paragraph's own
    text (644's `_substitute_footnotes`), and 640 turned every one of those
    into `\\footnotemark[N]` before rule (b) could look at it."""
    doc = _doc(numbered=numbered, footnote_on_page=footnote_on_page, refnum=n)
    par = _par(doc)
    par.props["text"] = f"Sparse coding<sup>{n}</sup> predates the transform."
    return doc


def test_a_materialised_sup_marker_naming_a_numbered_bibitem_becomes_a_cite():
    tex = _project(_doc_sup())
    assert "\\cite{key7}" in tex, tex
    assert "<sup>" not in tex, tex
    assert "\\footnotemark[7]" not in tex, tex
    assert "\\bibitem{key7}" in tex, tex


def test_a_materialised_sup_marker_with_a_footnote_on_its_page_stays_a_mark():
    doc = _doc_sup(footnote_on_page=True)
    proj = LaTeXProjector(
        OperatorConfig(op="projector", classname="LaTeXProjector"))
    tex = proj.project(doc)
    assert "\\footnotemark[7]" in tex, tex
    assert "\\cite{key7}" not in tex, tex
    assert "<sup>" not in tex, tex
    assert proj._footnotes.counts["marker_both"] == 1
    assert proj._footnotes.counts["sup_marker_both"] == 1


def test_a_materialised_sup_marker_matching_neither_stands_as_a_mark():
    """`stands` in THIS spelling is `\\footnotemark[N]` — 640's ruling, "a mark
    with no body IS \\footnotemark[n]". Reverting to the literal `<sup>` tag
    would re-open 640-a, which put 44 HTML tags into penev_A's .tex. It is
    counted so the default is visible."""
    doc = _doc_sup(numbered=False)
    proj = LaTeXProjector(
        OperatorConfig(op="projector", classname="LaTeXProjector"))
    tex = proj.project(doc)
    assert "\\footnotemark[7]" in tex, tex
    assert "\\cite{" not in tex, tex
    assert proj._footnotes.counts["sup_marker_default"] == 1
    assert proj._footnotes.counts["sup_markers"] == 1
    assert proj._footnotes.counts["markers_cited"] == 0


def test_one_rule_behind_both_spellings():
    """The bare `{ }^{7}` and the materialised `<sup>7</sup>` reach the SAME
    decision on the SAME document — that is the whole point of extracting it.
    """
    from docops.projectors.footnotes import BY_LOOKUP, decide, marker_lookups
    for maker in (_doc, _doc_sup):
        for kwargs, expected in ((dict(), "cite"),
                                 (dict(footnote_on_page=True), "footnote"),
                                 (dict(numbered=False), "unresolved")):
            doc = maker(**kwargs)
            look = marker_lookups(doc)
            d = decide("7", 4, look, rule_a=BY_LOOKUP)
            assert d.outcome == expected, (maker.__name__, kwargs, d)


# ─────────── fix round 2: the two callers mean different things by "no body"

def _doc_back_reference() -> Document:
    """638-e, with a numbered bibliography over it. TWO bare markers `{ }^{7}`
    on page 4 and ONE Footnote 7 whose body is on that page, plus Reference 7
    (`key7`). The first marker takes the body; the second is a back-reference
    to the SAME footnote and there is no second body for it."""
    doc = _doc(footnote_on_page=True)
    par = _par(doc)
    line = par.props["text"] + " And again\\({ }^{7}\\) later."
    par.props["text"] = line
    mp = doc.streams["mathpix_lines"]
    for anchor in list(mp.anchors):
        if mp.payload[anchor].get("_line_index") == 1:
            mp.payload[anchor]["text"] = line
    return doc


def test_a_consumed_body_is_not_offered_to_the_second_marker():
    """The bug fix round 2 exists for: pass 1 correctly gave the ONE body to the
    first marker and left the second unresolved, and `decide` then re-derived
    the CONSUMED body for it — setting `both` and counting `marker_both` twice.
    A body belongs to one marker."""
    res = fnres.resolve(_doc_back_reference())
    marks = res.marks_for(_par(_doc_back_reference()).id) or \
        next(iter(res.marks.values()))
    assert len(marks) == 2, marks
    first, second = marks
    assert first.outcome == "footnote" and first.both is True
    assert second.footnote_id is None
    assert second.both is False
    assert second.outcome == "unresolved", second
    assert res.counts["marker_both"] == 1
    assert res.counts["markers_resolved"] == 1
    assert res.counts["markers_unresolved"] == 1
    assert res.counts["markers_cited"] == 0


def test_the_bare_walk_never_asks_decide_to_re_derive_rule_a():
    """The handoff itself: `BY_CALLER` means `footnote_id` is the caller's WHOLE
    answer, so None there is `tried, none` — never `look it up`. Asked of
    `decide` directly, on the fixture whose body IS on the page."""
    from docops.projectors import footnotes as f
    doc = _doc(footnote_on_page=True)
    look = f.marker_lookups(doc)
    by_caller = f.decide("7", 4, look, rule_a=f.BY_CALLER, footnote_id=None)
    assert by_caller.footnote_id is None and by_caller.both is False
    assert by_caller.outcome == "unresolved"          # a taken body is evidence
    by_lookup = f.decide("7", 4, look, rule_a=f.BY_LOOKUP)
    assert by_lookup.outcome == "footnote"
    import pytest
    with pytest.raises(ValueError):
        f.decide("7", 4, look, rule_a="whatever")


def _doc_marker_far_from_its_body(*, with_footnote: bool) -> Document:
    """A paragraph on page 2 carrying `{ }^{3}`, and (optionally) the ONLY
    Footnote with refnum 3 seven pages away on page 9. A page-scoped map would
    not find it; the document-wide one does."""
    doc = Document()
    doc.meta["bibkey"] = "D"
    mp = doc.ensure_stream("mathpix_lines")
    line = "The code lengths\\({ }^{3}\\) are proportional."
    body = mp.append(text=line, _page=2, _line_index=0, type="text")
    par = DocObject(type="Paragraph", props={
        "text": line, "page": 2, "flow_index": 0})
    par.add_realization(Realization(stream="mathpix_lines",
                                    start=body, end=body, role="surface"))
    doc.add(par)
    if with_footnote:
        fnl = mp.append(text="\\footnotetext{Page nine body.}", _page=9,
                        _line_index=1, type="footnote")
        foot = DocObject(type="Footnote", props={
            "refnum": "3", "anchor_marker": "{ }^{3}", "page": 9,
            "content": "Page nine body.", "flow_index": 1})
        foot.add_realization(Realization(stream="mathpix_lines",
                                         start=fnl, end=fnl, role="surface"))
        doc.add(foot)
    return doc


def _paragraph_tiddler_text(doc: Document) -> str:
    import json
    from docops.projectors.tiddlywiki import TiddlyWikiProjector
    arr = json.loads(TiddlyWikiProjector(
        OperatorConfig(op="projector",
                       classname="TiddlyWikiProjector")).project(doc))
    return next(t["text"] for t in arr if "paragraph" in (t.get("tags") or ""))


def test_a_sup_marker_is_only_emitted_when_no_footnote_has_that_refnum():
    """THE CROSS-FILE INVARIANT `decide`'s BY_LOOKUP branch leans on: the
    tiddler projector emits `<sup>n</sup>` only where its DOCUMENT-WIDE
    `fn_by_refnum` has no Footnote with that refnum (644-a). If that map is ever
    scoped to a page, the `<sup>` lane starts resolving footnotes and
    `latex._sup_page` becomes load-bearing (641-c).

    Exercised through the REAL construction — `project()` builds the map — and
    across a SEVEN-page gap, so a page-scoped map fails the first assertion
    rather than quietly agreeing with a hand-built dict."""
    with_body = _paragraph_tiddler_text(
        _doc_marker_far_from_its_body(with_footnote=True))
    assert "||FN}}" in with_body, with_body          # document-wide map found it
    assert "<sup>3</sup>" not in with_body, with_body
    assert "{ }^{" not in with_body, with_body

    without = _paragraph_tiddler_text(
        _doc_marker_far_from_its_body(with_footnote=False))
    assert "<sup>3</sup>" in without, without        # no Footnote 3 anywhere
    assert "||FN}}" not in without, without
