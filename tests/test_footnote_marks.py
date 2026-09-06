"""638 — the footnote markers the LaTeX projector left as inline maths.

A drilled document carries the footnote BODY as a `Footnote` object (`refnum`,
`anchor_marker`, `content`, `page`) and the printed MARKER as raw inline maths
inside the paragraph's own text — `\\({ }^{3}\\)`, exactly as MathPix writes it.
The LaTeX projection emitted the body as a bare `\\footnotetext{…}` (no number:
the footnote counter is never stepped, so every one of them printed as "0") and
left the marker as a superscript with an empty base, which typesets as a lone
raised digit joined to nothing.

`refnum` is the PRINTED number and restarts per chapter, so it is not a key.
The marker is resolved by (page, refnum) with marker-order-vs-body-order as the
tie-break — never by refnum alone, and never guessed: an unresolved marker
stays as it is and is counted.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization
from docops.base import OperatorConfig
from docops.projectors import footnotes as fnres
from docops.projectors import latex_pipeline as _pipe
from docops.projectors.latex import LaTeXProjector


MARKER = "\\({ }^{3}\\)"
P4_LINE = f"The code lengths{MARKER} are proportional to the information."
P9_LINE = f"A second chapter re-uses the number{MARKER} entirely."


def _project(doc: Document) -> str:
    return LaTeXProjector(
        OperatorConfig(op="projector", classname="LaTeXProjector")).project(doc)


def _doc_two_footnotes_one_refnum() -> Document:
    """Two Footnotes with refnum 3, bodies on page 4 and on page 9; one
    paragraph on page 4 carrying the marker `{ }^{3}`. Only the page-4 body
    belongs to it."""
    doc = Document()
    doc.meta["bibkey"] = "D"
    mp = doc.ensure_stream("mathpix_lines")
    head = mp.append(text="1 Coding", _page=4, _line_index=0,
                     type="section_header")
    body4 = mp.append(text=P4_LINE, _page=4, _line_index=1, type="text")
    fn4 = mp.append(text="\\footnotetext{Page four body.}", _page=4,
                    _line_index=2, type="footnote")
    body9 = mp.append(text=P9_LINE, _page=9, _line_index=0, type="text")
    fn9 = mp.append(text="\\footnotetext{Page nine body.}", _page=9,
                    _line_index=1, type="footnote")

    sec = DocObject(type="Section", props={
        "caption": "Coding", "level": 1, "flow_index": 0, "page": 4})
    sec.add_realization(Realization(stream="mathpix_lines",
                                    start=head, end=head, role="surface"))
    doc.add(sec)

    par4 = DocObject(type="Paragraph", props={
        "text": P4_LINE, "page": 4, "flow_index": 1})
    par4.add_realization(Realization(stream="mathpix_lines",
                                     start=body4, end=body4, role="surface"))
    doc.add_child(sec, par4)

    foot4 = DocObject(type="Footnote", props={
        "refnum": "3", "anchor_marker": "{ }^{3}", "page": 4,
        "content": "Page four body.", "flow_index": 2})
    foot4.add_realization(Realization(stream="mathpix_lines",
                                      start=fn4, end=fn4, role="surface"))
    doc.add(foot4)

    par9 = DocObject(type="Paragraph", props={
        "text": P9_LINE, "page": 9, "flow_index": 3})
    par9.add_realization(Realization(stream="mathpix_lines",
                                     start=body9, end=body9, role="surface"))
    doc.add_child(sec, par9)

    foot9 = DocObject(type="Footnote", props={
        "refnum": "3", "anchor_marker": "{ }^{3}", "page": 9,
        "content": "Page nine body.", "flow_index": 4})
    foot9.add_realization(Realization(stream="mathpix_lines",
                                      start=fn9, end=fn9, role="surface"))
    doc.add(foot9)
    return doc


# ─────────────────────────────────────────────────────────── the marker itself

def test_the_marker_spelling_is_recognised_and_a_real_exponent_is_not():
    """`{ }^{n}` is a footnote marker only when it is the WHOLE inline-math
    span. `\\sigma_{r}{ }^{2}` is σ_r² — 74 of penev_A's 220 `{ }^{n}`
    occurrences are that shape and none of them is a footnote."""
    assert fnres.marker_refnum("\\({ }^{3}\\)") == "3"
    assert fnres.marker_refnum("\\( { }^{12} \\)") == "12"
    assert fnres.marker_refnum("${ }^{4}$") == "4"
    assert fnres.marker_refnum("\\({}^{5}\\)") == "5"
    assert fnres.marker_refnum("\\(\\sigma_{r}{ }^{2}\\)") is None
    assert fnres.marker_refnum("\\(x^{2}\\)") is None
    assert fnres.marker_refnum("plain text") is None


def test_markers_are_found_with_the_page_of_the_line_they_sit_on():
    doc = _doc_two_footnotes_one_refnum()
    res = fnres.resolve(doc)
    par4 = next(o for o in doc.objects.values()
                if o.type == "Paragraph" and o.props["page"] == 4)
    marks = res.marks_for(par4.id)
    assert len(marks) == 1
    assert marks[0].refnum == "3"
    assert marks[0].page == 4


# ────────────────────────────────────────────────── the disambiguation itself

def test_the_page_4_marker_takes_the_page_4_body_and_leaves_the_page_9_one():
    doc = _doc_two_footnotes_one_refnum()
    res = fnres.resolve(doc)
    par4 = next(o for o in doc.objects.values()
                if o.type == "Paragraph" and o.props["page"] == 4)
    foot4 = next(o for o in doc.objects.values()
                 if o.type == "Footnote" and o.props["page"] == 4)
    foot9 = next(o for o in doc.objects.values()
                 if o.type == "Footnote" and o.props["page"] == 9)
    (mark,) = res.marks_for(par4.id)
    assert mark.footnote_id == foot4.id
    # the page-9 body is untouched by THAT marker — it belongs to the page-9 one
    par9 = next(o for o in doc.objects.values()
                if o.type == "Paragraph" and o.props["page"] == 9)
    assert res.marks_for(par9.id)[0].footnote_id == foot9.id
    assert not res.counts["markers_ambiguous"]


def test_the_projection_marks_the_page_4_line_and_prints_the_page_4_body():
    doc = _doc_two_footnotes_one_refnum()
    tex = _project(doc)
    assert tex.count("\\footnotemark[3]") == 2      # one per paragraph
    assert "The code lengths\\footnotemark[3] are proportional" in tex
    assert "\\footnotetext[3]{Page four body.}" in tex
    assert "\\footnotetext[3]{Page nine body.}" in tex
    # the page-4 body follows the page-4 paragraph, not the page-9 one
    assert (tex.index("\\footnotetext[3]{Page four body.}")
            < tex.index("A second chapter re-uses the number"))
    # and NO bare marker survives in the running text
    assert "{ }^{3}" not in tex
    # the counter-less form is gone: every emitted body carries its number
    assert "\\footnotetext{" not in tex


# ───────────────────────────────────────── the two "never guess" obligations

def test_a_marker_with_no_footnote_stays_and_is_counted():
    doc = _doc_two_footnotes_one_refnum()
    for fn in [o for o in doc.objects.values() if o.type == "Footnote"]:
        doc.objects.pop(fn.id)
    res = fnres.resolve(doc)
    assert res.counts["markers_total"] == 2
    assert res.counts["markers_resolved"] == 0
    assert res.counts["markers_unresolved"] == 2
    tex = _project(doc)
    assert "\\footnotemark" not in tex
    assert tex.count("{ }^{3}") == 2         # left exactly as it was


def test_a_footnote_lacking_a_refnum_is_counted_and_never_marked():
    doc = _doc_two_footnotes_one_refnum()
    foot4 = next(o for o in doc.objects.values()
                 if o.type == "Footnote" and o.props["page"] == 4)
    foot4.props["refnum"] = ""
    foot4.props["anchor_marker"] = ""
    res = fnres.resolve(doc)
    assert res.counts["footnotes_without_a_refnum"] == 1
    assert res.counts["footnotes_without_an_anchor_marker"] == 1
    assert foot4.id not in res.used
    tex = _project(doc)
    assert "\\footnotemark[]" not in tex
    assert "\\footnotetext[]" not in tex
    # it still reaches the page — as an unnumbered body, which is what it is
    assert "Page four body." in tex


# ──────────────────────────────────────────────────── same page, two bodies

def test_two_bodies_with_one_refnum_on_one_page_pair_in_order_and_count():
    """646-a. Marker order on the page against body order on the page —
    first marker to first body — and the pairing is reported as ambiguous
    rather than presented as a fact."""
    doc = Document()
    doc.meta["bibkey"] = "D"
    mp = doc.ensure_stream("mathpix_lines")
    head = mp.append(text="1 X", _page=4, _line_index=0, type="section_header")
    l1 = mp.append(text=f"first{MARKER} here", _page=4, _line_index=1,
                   type="text")
    l2 = mp.append(text=f"second{MARKER} here", _page=4, _line_index=2,
                   type="text")
    f1 = mp.append(text="\\footnotetext{A}", _page=4, _line_index=3,
                   type="footnote")
    f2 = mp.append(text="\\footnotetext{B}", _page=4, _line_index=4,
                   type="footnote")
    sec = DocObject(type="Section", props={"caption": "X", "level": 1,
                                           "flow_index": 0, "page": 4})
    sec.add_realization(Realization(stream="mathpix_lines", start=head,
                                    end=head, role="surface"))
    doc.add(sec)
    pars = []
    for i, ln in enumerate((l1, l2)):
        p = DocObject(type="Paragraph", props={
            "text": mp.payload[ln]["text"], "page": 4, "flow_index": 1 + i})
        p.add_realization(Realization(stream="mathpix_lines", start=ln,
                                      end=ln, role="surface"))
        doc.add_child(sec, p)
        pars.append(p)
    foots = []
    for i, (ln, body) in enumerate(((f1, "A"), (f2, "B"))):
        f = DocObject(type="Footnote", props={
            "refnum": "3", "anchor_marker": "{ }^{3}", "page": 4,
            "content": body, "flow_index": 3 + i})
        f.add_realization(Realization(stream="mathpix_lines", start=ln,
                                      end=ln, role="surface"))
        doc.add(f)
        foots.append(f)

    res = fnres.resolve(doc)
    assert res.marks_for(pars[0].id)[0].footnote_id == foots[0].id
    assert res.marks_for(pars[1].id)[0].footnote_id == foots[1].id
    assert res.counts["markers_ambiguous"] == 2
    tex = _project(doc)
    assert tex.index("\\footnotetext[3]{A}") < tex.index("second")


def test_a_body_that_spilled_to_the_next_page_still_resolves():
    doc = _doc_two_footnotes_one_refnum()
    foot4 = next(o for o in doc.objects.values()
                 if o.type == "Footnote" and o.props["page"] == 4)
    foot4.props["page"] = 5                       # the body spilled over
    res = fnres.resolve(doc)
    par4 = next(o for o in doc.objects.values()
                if o.type == "Paragraph" and o.props["page"] == 4)
    assert res.marks_for(par4.id)[0].footnote_id == foot4.id
    assert res.counts["markers_resolved_on_a_later_page"] == 1


def test_a_body_five_pages_later_is_a_different_chapters_footnote_and_is_not_taken():
    """The forward search is capped at `MAX_SPILL_PAGES`. On penev_A an
    uncapped one attached ten markers to a body 4–12 pages away — a different
    chapter's footnote n, which is content MIXED UP, not content recovered."""
    doc = _doc_two_footnotes_one_refnum()
    foot4 = next(o for o in doc.objects.values()
                 if o.type == "Footnote" and o.props["page"] == 4)
    foot4.props["page"] = 4 + fnres.MAX_SPILL_PAGES + 1
    res = fnres.resolve(doc)
    par4 = next(o for o in doc.objects.values()
                if o.type == "Paragraph" and o.props["page"] == 4)
    assert res.marks_for(par4.id)[0].footnote_id is None
    assert res.counts["markers_unresolved"] == 1
    tex = _project(doc)
    assert "{ }^{3}" in tex                       # the marker stands


def test_a_body_only_on_an_earlier_page_does_not_resolve():
    """A footnote body never precedes its marker. Resolving backwards is how
    a per-chapter renumbering silently attaches the wrong text."""
    doc = _doc_two_footnotes_one_refnum()
    foot9 = next(o for o in doc.objects.values()
                 if o.type == "Footnote" and o.props["page"] == 9)
    doc.objects.pop(next(o for o in doc.objects.values()
                         if o.type == "Footnote"
                         and o.props["page"] == 4).id)
    res = fnres.resolve(doc)
    par9 = next(o for o in doc.objects.values()
                if o.type == "Paragraph" and o.props["page"] == 9)
    par4 = next(o for o in doc.objects.values()
                if o.type == "Paragraph" and o.props["page"] == 4)
    assert res.marks_for(par9.id)[0].footnote_id == foot9.id
    assert res.marks_for(par4.id)[0].footnote_id is None


def test_a_runaway_footnotetext_in_PROSE_is_contained_to_its_paragraph():
    """MathPix leaves a `\\footnotetext{` in the prose of a line a Paragraph
    also claims — 1 penev_A / 4 penev_B paragraphs — and one of penev_B's is
    never closed. Emitted verbatim it swallows the rest of the file ('File
    ended while scanning use of \\@footnotetext', Emergency stop) and every
    page after it is absent from the PDF. Same containment `balance_math`
    already gives a runaway `\\(`."""
    doc = _doc_two_footnotes_one_refnum()
    par4 = next(o for o in doc.objects.values()
                if o.type == "Paragraph" and o.props["page"] == 4)
    par4.props["text"] = "\\footnotetext{a body MathPix never closed"
    tex = _project(doc)
    depth = 0
    for ch in tex:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        assert depth >= 0
    assert depth == 0, "the projection's braces do not balance"
    assert "a body MathPix never closed" in tex          # nothing deleted


# ───────────────────────────────────────────────────────────── the stage dump

def test_the_stage_dump_carries_the_resolution_table():
    doc = _doc_two_footnotes_one_refnum()
    stages = _pipe.run_stages(doc, "D")
    assert "03-footnotes" in stages
    table = stages["03-footnotes"]
    assert table["counts"]["markers_total"] == 2
    assert table["counts"]["markers_resolved"] == 2
    rows = table["marks"]
    assert [r["refnum"] for r in rows] == ["3", "3"]
    assert all(r["footnote_page"] == r["marker_page"] for r in rows)
