"""646 — the conservation check: no content lost, none mixed up.

Rule 11: a success/failure summariser that can only see one of them sees
neither. Every check here is exercised on a REAL success (a document where
the projection conserves everything -> three zeros) AND on a REAL failure
(one object the projector emits nothing for, one paragraph transcluded from
two parents, one line two objects both claim, one line no object claims).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization
from docops.conserve import anchor_claims, conserve, reachability


# ---------------------------------------------------------------- fixtures

def _conserved() -> Document:
    """A tiny document in which everything IS conserved.

    One top-level Section (listed by the root tiddler and by the rebuilt TOC)
    holding one Paragraph (transcluded from the section body, once). Two
    lines, one claimed by each.
    """
    doc = Document()
    doc.meta["bibkey"] = "DOC"
    mp = doc.ensure_stream("mathpix_lines")
    head = mp.append(text="1 Introduction", _page=1, _line_index=0,
                     type="section_header")
    body = mp.append(text="Hello world.", _page=1, _line_index=1, type="text")

    sec = DocObject(type="Section", props={
        "caption": "Introduction", "level": 1, "flow_index": 0, "page": 1})
    sec.add_realization(Realization(stream="mathpix_lines",
                                    start=head, end=head, role="surface"))
    doc.add(sec)

    par = DocObject(type="Paragraph", props={
        "text": "Hello world.", "page": 1, "flow_index": 1})
    par.add_realization(Realization(stream="mathpix_lines",
                                    start=body, end=body, role="surface"))
    doc.add_child(sec, par)
    return doc


def _lines(doc):
    return doc.streams["mathpix_lines"]


def _para(doc):
    return doc.objects_of_type("Paragraph")[0]


def _reach(doc):
    r = conserve(doc)
    return r["reachability"]


# ---------------------------------------------------------------- (a) green

def test_a_conserved_document_reports_three_zeros():
    r = conserve(_conserved())
    assert r["counts"] == {"unreachable": 0, "unclaimed": 0,
                           "doubly_claimed": 0}, r["counts"]
    assert r["conserved"] is True
    # the population was not empty — a check that measures nothing passes
    # vacuously, which is exactly the masked-success shape rule 11 names.
    assert r["reachability"]["objects"] == 2
    assert r["anchors"]["total"] == 2


# ---------------------------------------- (b) an object with no tiddler

def test_b_object_the_projector_emits_no_tiddler_for_is_unreachable():
    doc = _conserved()
    mp = _lines(doc)
    par = _para(doc)
    par.props["text"] = "Hello world [X1]."
    mp.payload[mp.anchors[1]]["text"] = "Hello world [X1]."
    cit = DocObject(type="Citation", props={"citekey": "X1", "flow_index": 2})
    cit.add_realization(Realization(
        stream="mathpix_lines", start=mp.anchors[1], end=mp.anchors[1],
        role="surface", props={"offset": 13, "length": 2}))
    doc.add(cit)

    r = conserve(doc)
    assert r["counts"]["unreachable"] == 1, r["reachability"]["unreachable"]
    bad = r["reachability"]["unreachable"][0]
    assert bad["type"] == "Citation"
    assert bad["reason"] == "no tiddler"
    # the inline citation marker does not claim its host line
    assert r["counts"]["doubly_claimed"] == 0
    assert r["reachability"]["by_type"]["Citation"]["unreachable"] == 1


# ---------------------------------------- (c) two parents

def test_c_paragraph_transcluded_from_two_sections_is_multi_parent():
    doc = _conserved()
    par = _para(doc)
    sec2 = DocObject(type="Section", props={
        "caption": "Second", "level": 1, "flow_index": 5, "page": 1})
    sec2.children.append(par.id)          # a SECOND parent for the same object
    doc.add(sec2)

    r = conserve(doc)
    mp = r["reachability"]["multi_parent"]
    assert len(mp) == 1, mp
    assert mp[0]["type"] == "Paragraph"
    assert len(mp[0]["parents"]) == 2
    assert r["reachability"]["by_type"]["Paragraph"]["multi_parent"] == 1
    # multi-parent is not unreachable
    assert r["counts"]["unreachable"] == 0


# ---------------------------------------- (d) a line two objects claim

def test_d_line_claimed_by_a_paragraph_and_a_footnote_is_doubly_claimed():
    doc = _conserved()
    mp = _lines(doc)
    fn = DocObject(type="Footnote", props={
        "refnum": 1, "content": "a note", "flow_index": 3})
    fn.add_realization(Realization(stream="mathpix_lines",
                                   start=mp.anchors[1], end=mp.anchors[1],
                                   role="surface"))
    doc.add(fn)

    claims = anchor_claims(doc)
    assert len(claims["doubly_claimed"]) == 1, claims["doubly_claimed"]
    assert claims["pairs"][("Footnote", "Paragraph")] == 1
    got = claims["doubly_claimed"][0]
    assert sorted(c["type"] for c in got["claimants"]) == ["Footnote", "Paragraph"]
    assert conserve(doc)["counts"]["doubly_claimed"] == 1


# ---------------------------------------- (e) a line nobody claims

def test_e_line_no_object_covers_is_unclaimed():
    doc = _conserved()
    mp = _lines(doc)
    mp.append(text="(3.14)", _page=1, _line_index=2, type="equation_number")

    claims = anchor_claims(doc)
    assert len(claims["unclaimed"]) == 1, claims["unclaimed"]
    assert claims["unclaimed"][0]["text"] == "(3.14)"
    assert claims["unclaimed"][0]["line_type"] == "equation_number"
    assert conserve(doc)["counts"]["unclaimed"] == 1
    assert conserve(doc)["conserved"] is False


# ---------------------------------------- definitions that must hold

def test_page_containers_do_not_claim_the_lines_they_span():
    """A Page realization spans every line of its page by construction. If it
    counted as a claim, EVERY anchor would be doubly claimed and the measure
    would say nothing — the documented deviation from the brief's literal
    rule (out/646.txt)."""
    doc = _conserved()
    mp = _lines(doc)
    pg = DocObject(type="Page", props={"page_number": 1})
    pg.add_realization(Realization(stream="mathpix_lines",
                                   start=mp.anchors[0], end=mp.anchors[-1],
                                   role="surface"))
    doc.add(pg)
    claims = anchor_claims(doc)
    assert claims["doubly_claimed"] == []
    assert "Page" in claims["containers_excluded"]


def test_reachability_takes_the_projectors_own_title_map():
    """The three arguments are the ones the brief names: the Document, the
    tiddler array and the projector's title map — no file is read."""
    doc = _conserved()
    from docops.conserve import project_in_memory
    tiddlers, titles, bibkey = project_in_memory(doc)
    assert bibkey == "DOC"
    assert any(t["title"] == "DOC" for t in tiddlers)      # the root
    r = reachability(doc, tiddlers, titles)
    assert r["unreachable"] == [] and r["multi_parent"] == []


def test_two_objects_sharing_one_tiddler_title_are_reported_as_a_collision():
    """Two objects, ONE tiddler title. Nothing is unreachable and nothing is
    unclaimed — the content is MIXED UP, which is the other half of the claim.

    644 CHANGED THE SETUP, NOT THE CHECK. This used to build the collision
    from the projector itself: footnote titles were `FN<refnum>` and refnums
    restart per page, so two Footnotes with refnum 1 became one tiddler (17
    such collisions on penev_A). 644 numbers a footnote by its position in the
    flow, so the scheme no longer produces a collision anywhere — see
    `test_title_scheme.py::test_footnote_titles_are_unique_per_object`. The
    DETECTOR still has to work, because a future scheme change or a
    hand-written title map can still collide, so the collision is now handed
    to `reachability` directly.
    """
    doc = _conserved()
    mp = _lines(doc)
    fns = []
    for i in range(2):
        a = mp.append(text="1 a note", _page=1, _line_index=9 + i, type="text")
        fn = DocObject(type="Footnote", props={"refnum": 1, "content": "note"})
        fn.add_realization(Realization(stream="mathpix_lines",
                                       start=a, end=a, role="surface"))
        doc.add(fn)
        fns.append(fn)
    from docops.conserve import project_in_memory
    tiddlers, titles, _ = project_in_memory(doc)
    assert titles[fns[0].id] != titles[fns[1].id], "the scheme collided again"
    titles[fns[1].id] = titles[fns[0].id]            # force ONE title
    cols = reachability(doc, tiddlers, titles)["collisions"]
    assert len(cols) == 1, cols
    assert cols[0]["title"] == titles[fns[0].id]
    assert [o["type"] for o in cols[0]["objects"]] == ["Footnote", "Footnote"]


def test_dark_anchors_are_lines_whose_every_claimant_is_unreachable():
    """A Toc object claims its whole Contents region and the projector emits
    nothing for it (262). Those lines are CLAIMED — neither headline count
    sees them — and still reach no tiddler."""
    doc = _conserved()
    mp = _lines(doc)
    a = mp.append(text="3.1 Method .... 12", _page=2, _line_index=8,
                  type="toc")
    b = mp.append(text="3.2 Results .... 20", _page=2, _line_index=9,
                  type="toc")
    toc = DocObject(type="Toc", props={"flow_index": 9})
    toc.add_realization(Realization(stream="mathpix_lines", start=a, end=b,
                                    role="surface"))
    doc.add(toc)
    r = conserve(doc)
    assert r["counts"]["unclaimed"] == 0        # the lines ARE claimed
    assert r["counts"]["doubly_claimed"] == 0
    assert r["anchors"]["dark"]["count"] == 2   # …by an object reaching nothing
    assert r["anchors"]["dark"]["by_type"][0]["types"] == ["Toc"]


# ------------- (f)/(g) reachability is a WALK FROM THE ROOTS, not a scan

def test_f_an_island_of_tiddlers_naming_each_other_is_unreachable():
    """Two paragraphs that transclude each other and nothing else.

    A flat "is this title named anywhere?" scan calls both reachable — each
    has a parent. Neither is reachable from a root, so neither is in the
    document: the walk is the whole point of the definition.
    """
    doc = _conserved()
    mp = _lines(doc)
    a = mp.append(text="see {{DOC_PARA_0003||PARA}}", _page=3, _line_index=20,
                  type="text")
    b = mp.append(text="see {{DOC_PARA_0002||PARA}}", _page=3, _line_index=21,
                  type="text")
    for anchor, fi in ((a, 5), (b, 6)):
        p = DocObject(type="Paragraph", props={"page": 3, "flow_index": fi})
        p.add_realization(Realization(stream="mathpix_lines", start=anchor,
                                      end=anchor, role="surface"))
        doc.add(p)

    r = conserve(doc)
    titles = sorted(e["title"] for e in r["reachability"]["unreachable"])
    assert titles == ["DOC_PARA_0002", "DOC_PARA_0003"], titles
    # each IS named by the other — the count that a flat scan would report
    assert all(e["named_by"] == 1 for e in r["reachability"]["unreachable"])


def test_g_a_paragraph_under_an_unreachable_section_is_unreachable():
    """A subsection no root lists and no section lists (empty caption, so the
    rebuilt TOC skips it; a parent_section, so the root skips it) is itself
    unreachable — and so is every paragraph it lists."""
    doc = _conserved()
    mp = _lines(doc)
    top = doc.objects_of_type("Section")[0]
    hidden = DocObject(type="Section", props={
        "caption": "", "level": 2, "flow_index": 5, "page": 3,
        "parent_section": top.id})
    doc.add(hidden)
    anchor = mp.append(text="orphaned body text", _page=3, _line_index=20,
                       type="text")
    child = DocObject(type="Paragraph", props={"page": 3, "flow_index": 6})
    child.add_realization(Realization(stream="mathpix_lines", start=anchor,
                                      end=anchor, role="surface"))
    doc.add_child(hidden, child)

    r = conserve(doc)
    got = {e["type"]: e for e in r["reachability"]["unreachable"]}
    assert set(got) == {"Section", "Paragraph"}, r["reachability"]["unreachable"]
    assert got["Section"]["named_by"] == 0          # nothing names it at all
    assert got["Paragraph"]["named_by"] == 1        # its unreached section does
    assert r["reachability"]["by_type"]["Paragraph"]["unreachable"] == 1
