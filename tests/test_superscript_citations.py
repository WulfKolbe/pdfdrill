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
