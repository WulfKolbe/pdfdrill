"""636 — each footnote body is cut at the NEXT footnote's number.

MathPix puts every footnote of a page into ONE `\\footnotetext{...}` group, so
the body of footnote 3 ran to the end of the group and swallowed footnote 4's
printed number and its text ("...(Deco and Obradovic 1996).\\({ }^{4}\\) PCA has
also been utilized..."). 29 of penev_A's 53 Footnote bodies were that shape.

The cut is exact: a footnote LABEL is `{ }^{n}` at the HEAD of an inline-math
span — a superscript with an EMPTY BASE. `\\(\\sigma_{r}{ }^{2}\\)` is a real
exponent and is never a cut point.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.base_module import ModuleConfig
from docmodel.core import Document, DocObject
from docmodel import footnote_split as fs
from docmodel.modules.footnote import FootnoteProcessor
from docmodel.modules.page import ingest_lines_json, PageProcessor
from docmodel.modules.paragraph import ParagraphProcessor
from pdfdrill import heading_cleanup as hc


def _module(cls):
    return cls(ModuleConfig(classname=cls.__name__), bibkey="T", flags={})


def _doc(lines):
    doc = Document()
    doc.meta["bibkey"] = "T"
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "i", "lines": lines}]})
    return doc


def _fn(doc):
    return sorted(doc.objects_of_type("Footnote"),
                  key=lambda o: str(o.props.get("refnum")))


def _interior(content):
    """Labels at a position > 0 — the next footnote's number inside this body."""
    return [(m.start(), m.group(1)) for m in fs.LABEL.finditer(content or "")
            if m.start() > 0]


# ------------------------------------------------------------- the recogniser

def test_a_label_is_an_empty_base_superscript_at_the_head_of_a_span():
    assert fs.find_labels(r"\({ }^{3}\) body") == [(0, "3")]
    assert fs.find_labels(r"${ }^{12}$ body") == [(0, "12")]
    assert fs.find_labels(r"\({ }^{13}(\Phi \hat{x}, \Phi \hat{y})\) is") == [(0, "13")]


def test_a_real_exponent_is_never_a_label():
    """penev_A carries 52 `{ }^{n}` occurrences that are real exponents — a base
    precedes the superscript. Cutting there would destroy the maths."""
    assert fs.find_labels(r"the ratio \(\sigma_{r}{ }^{2}\) is small") == []
    assert fs.find_labels(r"\(10^{12}\) and \(x_{0}{ }^{-1} g_{ik}\)") == []


def test_no_label_means_no_split():
    assert fs.split_bodies("plain body text with no number") == []


# ----------------------------------------------------- the cut, on one string

def test_two_footnotes_in_one_group_split_into_two_bodies():
    text = r"\({ }^{3}\) first body.\({ }^{4}\) PCA second body."
    segs = fs.split_bodies(text)
    assert [s.refnum for s in segs] == ["3", "4"]
    assert segs[0].body == "first body."
    assert segs[1].body == "PCA second body."
    assert not any(_interior(s.body) for s in segs)


def test_the_glued_label_keeps_its_own_math_span():
    """`\\({ }^{21} \\mathbf{K}^{2} \\equiv ...\\)` — the number shares its span
    with the body's maths. Cutting inside the span would unbalance it, so the
    span is left exactly as it stands (which is what bodies do today)."""
    text = r"\({ }^{21} \mathbf{K}^{2}\) is missing.\({ }^{22}\) next."
    segs = fs.split_bodies(text)
    assert [s.refnum for s in segs] == ["21", "22"]
    assert segs[0].body == r"\({ }^{21} \mathbf{K}^{2}\) is missing."
    assert segs[1].body == "next."


def test_a_repeated_number_is_not_a_second_footnote():
    """A second `{ }^{3}` in the same block would give two objects one printed
    number on one page — the title collision 644 removed. The split refuses:
    the tail stays on the earlier body, marked `tail_unassigned`, and counted."""
    segs = fs.split_bodies(r"\({ }^{3}\) first.\({ }^{3}\) repeat.")
    assert len(segs) == 1
    assert segs[0].tail_unassigned is True
    assert "repeat." in segs[0].body                       # never dropped
    assert fs.orphan_tails(segs) == 1


# ------------------------------------------------- FootnoteProcessor, on lines

def test_a_footnote_line_with_two_numbers_yields_two_footnotes():
    doc = _doc([{"id": "fn", "type": "footnote",
                 "text": r"\footnotetext{\({ }^{3}\) first body.\({ }^{4}\) PCA second body.}"}])
    _module(FootnoteProcessor).process_document(doc)
    fns = _fn(doc)
    assert [f.props["refnum"] for f in fns] == ["3", "4"]
    assert fns[0].props["content"] == "first body."
    assert fns[1].props["content"] == "PCA second body."
    assert not any(_interior(f.props["content"]) for f in fns)


def test_a_body_spanning_two_lines_is_cut_at_the_label_on_the_second_line():
    """MathPix's real shape: the footnote block is a `footnote` line whose
    CHILDREN carry the text, one printed number starting mid-child."""
    doc = _doc([
        {"id": "blk", "type": "footnote", "text": "",
         "children_ids": ["c1", "c2"]},
        {"id": "c1", "type": "text",
         "text_display": "\n\n\\footnotetext{\n\\({ }^{3}\\) For a recent review."},
        {"id": "c2", "type": "text",
         "text_display": "\n\\({ }^{4}\\) PCA has also been utilized.\n}"},
    ])
    _module(FootnoteProcessor).process_document(doc)
    fns = _fn(doc)
    assert [f.props["refnum"] for f in fns] == ["3", "4"]
    assert fns[0].props["content"] == "For a recent review."
    assert fns[1].props["content"] == "PCA has also been utilized."


def test_the_split_footnote_claims_its_line_inline_not_whole():
    """646 counts a line claimed by two objects as content MIXED UP. The body
    cut out of a line covers only part of it, so its realization carries a
    sub-anchor (offset/length) — which `conserve` does not count as a claim."""
    doc = _doc([
        {"id": "blk", "type": "footnote", "text": "", "children_ids": ["c1"]},
        {"id": "c1", "type": "text",
         "text_display": "\\footnotetext{\\({ }^{3}\\) one.\\({ }^{4}\\) two.}"},
    ])
    _module(FootnoteProcessor).process_document(doc)
    four = next(f for f in _fn(doc) if f.props["refnum"] == "4")
    r = next(r for r in four.realizations
             if r.stream == "mathpix_lines" and r.role == "surface")
    assert isinstance(r.props.get("offset"), int)
    assert isinstance(r.props.get("length"), int)
    line = "\\footnotetext{\\({ }^{3}\\) one.\\({ }^{4}\\) two.}"
    assert line[r.props["offset"]:].startswith("\\({ }^{4}\\)")


def test_the_first_body_keeps_the_block_line_it_always_claimed():
    """Only the CUT-OUT bodies are new. The first stays anchored on the
    `footnote` line exactly as before, so nothing that was claimed stops
    being claimed."""
    doc = _doc([{"id": "fn", "type": "footnote",
                 "text": r"\footnotetext{\({ }^{3}\) a.\({ }^{4}\) b.}"}])
    _module(FootnoteProcessor).process_document(doc)
    three = next(f for f in _fn(doc) if f.props["refnum"] == "3")
    r = next(r for r in three.realizations
             if r.stream == "mathpix_lines" and r.role == "surface")
    assert "offset" not in r.props and "length" not in r.props


def test_one_footnote_per_line_is_unchanged():
    doc = _doc([{"id": "fn", "type": "footnote",
                 "text": r"\footnotetext{\({ }^{1}\) The footnote body.}"}])
    _module(FootnoteProcessor).process_document(doc)
    fns = _fn(doc)
    assert len(fns) == 1 and fns[0].props["content"] == "The footnote body."


# --------------------------------------------- heading_cleanup, on a Paragraph

def test_a_paragraph_footnotetext_with_two_numbers_yields_two_footnotes():
    """`extract_footnote_paragraphs` is the SECOND creator of Footnote objects
    (25 of penev_A's 53), and it bled exactly as badly: 15 of its 25 bodies
    carried the next footnote's number and text."""
    doc = Document()
    doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "\\footnotetext{\\({ }^{3}\\) first body.\\({ }^{4}\\) PCA second.}",
        "page": 4, "flow_index": 1}))
    assert hc.extract_footnote_paragraphs(doc) == 2
    fns = _fn(doc)
    assert [f.props["refnum"] for f in fns] == ["3", "4"]
    assert fns[0].props["content"] == "first body."
    assert fns[1].props["content"] == "PCA second."
    assert not any(_interior(f.props["content"]) for f in fns)


def test_a_paragraph_footnote_does_not_claim_the_paragraph_s_lines():
    """The cleanup copied the PARAGRAPH's realizations onto the Footnote, so
    every line of the paragraph was claimed by both — all 35 of penev_A's
    Footnote+Paragraph doubly-claimed anchors. The claim is now the sub-anchor
    where the footnote's own number sits."""
    doc = _doc([
        {"id": "l1", "type": "text",
         "text_display": "Prose. \\footnotetext{\\({ }^{3}\\) first.\\({ }^{4}\\) second.}"},
    ])
    for cls in (PageProcessor, ParagraphProcessor):
        _module(cls).process_document(doc)
    hc.extract_footnote_paragraphs(doc)
    from docops import conserve as C
    pairs = C.conserve(doc)["anchors"]["pairs"]
    assert not [e for e in pairs if "Footnote" in e["types"]], pairs


def test_a_pure_footnote_paragraph_still_claims_every_line_it_covers():
    """The claim is the footnote's real EXTENT, not just its label's line.
    Claiming only the label's line dropped 193 penev_A lines to "covered by no
    object": two thirds of these paragraphs are pure footnote text, so the
    Footnote was their only claimant. Each line is claimed exactly once."""
    doc = _doc([
        {"id": "l1", "type": "text",
         "text_display": "\\footnotetext{\\({ }^{3}\\) For a recent review."},
        {"id": "l2", "type": "text",
         "text_display": "\\({ }^{4}\\) PCA has also been utilized,"},
        {"id": "l3", "type": "text",
         "text_display": " described in Section 4.2.}"},
    ])
    for cls in (PageProcessor, ParagraphProcessor):
        _module(cls).process_document(doc)
    hc.extract_footnote_paragraphs(doc)
    from docops import conserve as C
    rep = C.conserve(doc)
    assert rep["counts"]["unclaimed"] == 0, rep["anchors"]["unclaimed"]
    assert rep["counts"]["doubly_claimed"] == 0, rep["anchors"]["pairs"]


def test_a_body_spilling_in_from_the_previous_page_is_still_claimed():
    """Two penev_A blocks open with text that has no number — a footnote
    spilling in from the page before. `split_bodies` keeps it on the first body
    rather than inventing an owner, so the first body's claim starts at the
    GROUP, not at its number: 11 lines that would otherwise be claimed by
    nothing while their text sits in a Footnote."""
    doc = _doc([
        {"id": "l1", "type": "text",
         "text_display": "\\footnotetext{\nshould have this in mind."},
        {"id": "l2", "type": "text", "text_display": " Nevertheless, many facts"},
        {"id": "l3", "type": "text",
         "text_display": "\\({ }^{4}\\) In the restrictive treatment.}"},
    ])
    for cls in (PageProcessor, ParagraphProcessor):
        _module(cls).process_document(doc)
    hc.extract_footnote_paragraphs(doc)
    from docops import conserve as C
    rep = C.conserve(doc)
    assert rep["counts"]["unclaimed"] == 0, rep["anchors"]["unclaimed"]
    assert rep["counts"]["doubly_claimed"] == 0, rep["anchors"]["pairs"]


def test_a_paragraph_footnote_that_cannot_be_located_keeps_its_shared_claim():
    """No sub-anchor is invented. When the label is in no single line of the
    paragraph's span, the realizations stay as they were and the refusal is
    counted rather than guessed at."""
    doc = Document()
    doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "\\footnotetext{\\({ }^{7}\\) body}", "flow_index": 1}))
    hc.extract_footnote_paragraphs(doc)                    # no lines stream at all
    fns = _fn(doc)
    assert len(fns) == 1 and fns[0].props["refnum"] == "7"


def test_extract_footnote_paragraphs_is_still_idempotent():
    doc = Document()
    doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "\\footnotetext{\\({ }^{1}\\) x.\\({ }^{2}\\) y.}", "flow_index": 1}))
    assert hc.extract_footnote_paragraphs(doc) == 2
    assert hc.extract_footnote_paragraphs(doc) == 0


# ---------------------------------------------------------- the whole document

def test_the_projection_of_a_split_block_carries_both_bodies_once():
    from docops.base import OperatorConfig
    from docops.projectors.tiddlywiki import TiddlyWikiProjector
    doc = _doc([
        {"id": "p1", "type": "text",
         "text": r"See \({ }^{3}\) and \({ }^{4}\) here."},
        {"id": "fn", "type": "footnote",
         "text": r"\footnotetext{\({ }^{3}\) first body.\({ }^{4}\) second body.}"},
    ])
    for cls in (PageProcessor, FootnoteProcessor, ParagraphProcessor):
        _module(cls).process_document(doc)
    arr = json.loads(TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector")).project(doc))
    bodies = [t["text"] for t in arr if "footnote" in t.get("tags", "")]
    assert len(bodies) == 2
    assert any("first body." in b for b in bodies)
    assert any("second body." in b for b in bodies)
    assert not any("{ }^{4}" in b and "first body." in b for b in bodies)


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
