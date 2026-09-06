"""
010 — a Reference stub at first citation.

penev_A had 81 Citations over 52 distinct citekeys but only 8 References (the
8 bibsource supplied): 44 cited keys had no Reference at all. The fix,
per the spec's own words ("Create an empty Reference on first Citation"):
`docmodel.modules.citation.ensure_reference_stub(doc, citation, bibkey)` is
called by EVERY Citation creator at the moment it creates a citation --
`CitationProcessor.create_object` (`[key]`) here, and
`detect_numeric_citations`/`detect_author_year_citations`/
`detect_author_year_in_objects` in `pdfdrill.bibliography` -- so "first
occurrence" falls out of creation order for free. It returns the existing
Reference for a citekey (stub or filled) or creates a stub (`stub: True`,
`ref_source: "citation"`) anchored at THIS citation, and links the citation
to it (a `cites` Alignment) either way. The three Reference-CONTENT creators
in `pdfdrill.bibliography` (parsed References section, `.bbl`, `.bib`) FILL
a stub in place (same id, same anchor) instead of creating a second
Reference for the same key.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document
from docmodel.modules.page import ingest_lines_json
from docmodel.modules.citation import CitationProcessor
from docmodel.base_module import ModuleConfig
from pdfdrill import bibliography as B


def _mod(cls, bibkey="T"):
    return cls(ModuleConfig(title=cls.__name__, classname=cls.__name__, proc_order=0), bibkey)


def _doc():
    doc = Document()
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "i", "lines": [
        {"id": "l1", "type": "text", "text": "First [a].", "text_display": "First [a]."},
        {"id": "l2", "type": "text", "text": "Then [b].", "text_display": "Then [b]."},
        {"id": "l3", "type": "text", "text": "Then [a, c].", "text_display": "Then [a, c]."},
    ]}]})
    return doc


def _run_citation_processor(doc):
    mod = _mod(CitationProcessor)
    mod.process_document(doc)   # ensure_reference_stub runs inline, per Citation
    return mod


def test_stub_created_at_first_citation_per_distinct_key():
    doc = _doc()
    _run_citation_processor(doc)

    citations = doc.objects_of_type("Citation")
    assert len(citations) == 4, [c.props.get("citekey") for c in citations]
    keys = sorted(c.props.get("citekey") for c in citations)
    assert keys == ["a", "a", "b", "c"]

    refs = doc.objects_of_type("Reference")
    assert len(refs) == 3, [r.props.get("citekey") for r in refs]
    ref_keys = sorted(r.props.get("citekey") for r in refs)
    assert ref_keys == ["a", "b", "c"]
    for r in refs:
        assert r.props.get("stub") is True
        assert r.props.get("ref_source") == "citation"


def test_stub_anchored_at_first_citation_of_its_key():
    doc = _doc()
    _run_citation_processor(doc)

    refs_by_key = {r.props.get("citekey"): r for r in doc.objects_of_type("Reference")}
    citations = doc.objects_of_type("Citation")

    # "a" appears twice (line 1 and line 3) -- the stub must anchor at the
    # FIRST (line 1), not the second.
    a_citations = [c for c in citations if c.props.get("citekey") == "a"]
    assert len(a_citations) == 2
    first_a, second_a = a_citations
    first_surface = next(r for r in first_a.realizations if r.role == "surface")
    second_surface = next(r for r in second_a.realizations if r.role == "surface")

    ref_a = refs_by_key["a"]
    ref_surface = next(r for r in ref_a.realizations if r.role == "surface")
    assert ref_surface.stream == first_surface.stream
    assert ref_surface.start is first_surface.start
    assert ref_surface.end is first_surface.end
    assert ref_surface.start is not second_surface.start


def test_every_citation_links_to_its_keys_reference():
    doc = _doc()
    _run_citation_processor(doc)

    refs_by_key = {r.props.get("citekey"): r for r in doc.objects_of_type("Reference")}
    cites = [a for a in doc.alignments if a.kind == "cites"]
    assert len(cites) == 4          # one per Citation, including both "a"s

    for c in doc.objects_of_type("Citation"):
        key = c.props.get("citekey")
        c_surface = next(r for r in c.realizations if r.role == "surface")
        ref_surface = next(r for r in refs_by_key[key].realizations if r.role == "surface")
        # Two citations from a comma list (`[a, c]`) share one line anchor, so
        # the Range alone doesn't disambiguate them -- the Alignment's own
        # `citekey` prop does (same as `bibliography.link_citations`'s edges).
        match = [a for a in cites
                 if a.props.get("citekey") == key
                 and (a.left.stream, a.left.start, a.left.end)
                 == (c_surface.stream, c_surface.start, c_surface.end)]
        assert len(match) == 1, (key, c.id)
        a = match[0]
        assert (a.right.stream, a.right.start, a.right.end) == \
            (ref_surface.stream, ref_surface.start, ref_surface.end)


def test_fill_updates_stub_in_place_others_untouched():
    doc = _doc()
    _run_citation_processor(doc)

    refs_by_key = {r.props.get("citekey"): r for r in doc.objects_of_type("Reference")}
    stub_a_id = refs_by_key["a"].id
    stub_a_surface = next(r for r in refs_by_key["a"].realizations if r.role == "surface")

    entries = [{
        "citekey": "a", "raw_text": "A. Author. A Paper. Venue, 2020.",
        "year": "2020", "author": "A. Author", "number": 1,
    }]
    n = B.add_reference_objects(doc, entries)
    assert n == 1

    refs = doc.objects_of_type("Reference")
    assert len(refs) == 3, [r.props.get("citekey") for r in refs]
    refs_by_key = {r.props.get("citekey"): r for r in refs}

    filled = refs_by_key["a"]
    assert filled.id == stub_a_id                        # same object, filled
    assert not filled.props.get("stub")
    assert filled.props["ref_source"] == "text"
    assert filled.props["raw_text"] == "A. Author. A Paper. Venue, 2020."
    assert filled.props["year"] == "2020"
    assert filled.props["author"] == "A. Author"
    filled_surface = next(r for r in filled.realizations if r.role == "surface")
    assert filled_surface.start is stub_a_surface.start   # anchor kept

    for key in ("b", "c"):
        r = refs_by_key[key]
        assert r.props.get("stub") is True
        assert r.props.get("ref_source") == "citation"
        assert "raw_text" not in r.props


def test_bibsource_bib_fill_updates_stub_in_place():
    """The `.bib` creator (`load_bibtex_file`, `cmd_bibsource`'s ~line-486
    path) must FILL a citation-stub Reference in place, not add a second
    Reference for the same key -- pinned even though the corpus measurement
    (penev_A) can't exercise it: no `.bbl`/`.bib` is on disk for that
    document (see tasks/010.report.md OPEN)."""
    doc = _doc()
    _run_citation_processor(doc)

    refs_by_key = {r.props.get("citekey"): r for r in doc.objects_of_type("Reference")}
    stub_a_id = refs_by_key["a"].id
    stub_a_surface = next(r for r in refs_by_key["a"].realizations if r.role == "surface")

    bibtext = (
        "@article{a,\n"
        "  author = {A. Author},\n"
        "  year = {2020},\n"
        "  title = {A Paper},\n"
        "}\n"
    )
    result = B.load_bibtex_file(doc, bibtext)
    assert result["created"] == 0          # filled the stub, didn't create one
    assert result["attached"] == 1

    refs = doc.objects_of_type("Reference")
    assert len(refs) == 3, [r.props.get("citekey") for r in refs]     # no 2nd "a"
    refs_by_key = {r.props.get("citekey"): r for r in refs}

    filled = refs_by_key["a"]
    assert filled.id == stub_a_id                          # same object, filled
    assert not filled.props.get("stub")
    assert filled.props["ref_source"] == "bib"
    assert filled.props["author"] == "A. Author"
    assert filled.props["year"] == "2020"
    assert "bibtex" in filled.props
    filled_surface = next(r for r in filled.realizations if r.role == "surface")
    assert filled_surface.start is stub_a_surface.start     # anchor kept

    for key in ("b", "c"):
        r = refs_by_key[key]
        assert r.props.get("stub") is True
        assert r.props.get("ref_source") == "citation"


def test_link_citations_is_idempotent_against_ensure_reference_stub():
    """010 fix round 2 — penev_A had 162 `cites` Alignments for 81 Citations:
    `ensure_reference_stub` links each Citation to its Reference at creation
    time, and `cmd_bibliography` unconditionally calls `link_citations`
    afterward, which used to add a SECOND, identical edge for every citekey
    already linked. `link_citations` must skip an edge that already exists
    (`docmodel.modules.citation.add_cites_alignment`, shared by both)."""
    doc = _doc()
    _run_citation_processor(doc)   # ensure_reference_stub links all 4 already

    cites_before = [a for a in doc.alignments if a.kind == "cites"]
    assert len(cites_before) == 4          # one per Citation, from stub creation

    added = B.link_citations(doc)
    assert added == 0                       # every key already linked, by citekey exact match

    cites_after = [a for a in doc.alignments if a.kind == "cites"]
    assert len(cites_after) == 4            # unchanged -- exactly one per Citation, not 8


def test_two_new_keys_sharing_one_line_each_get_their_own_edge():
    """Found while measuring penev_A for fix round 2: a citation is anchored
    at LINE granularity (`start == end == the line`, sub-position is a
    prop, not part of the Range), so two DIFFERENT, never-seen-before
    citekeys parsed off the SAME line (`[d, e]`) share one `left` Range --
    and each gets its own brand-new stub anchored at THAT line, so their
    `right` Ranges collide too. Deduping `add_cites_alignment` on
    `(left, right)` alone (round 2's first cut) silently dropped one of
    these as "already linked" when it was a distinct edge to a distinct
    Reference (10 of penev_A's 81 Citations lost this way); `citekey` has
    to be part of the identity check."""
    doc = Document()
    ingest_lines_json(doc, {"pages": [{"page": 1, "image_id": "i", "lines": [
        {"id": "l1", "type": "text", "text": "First [a].", "text_display": "First [a]."},
        {"id": "l2", "type": "text", "text": "Then [b].", "text_display": "Then [b]."},
        {"id": "l3", "type": "text", "text": "Then [a, c].", "text_display": "Then [a, c]."},
        {"id": "l4", "type": "text", "text": "Also [d, e].", "text_display": "Also [d, e]."},
    ]}]})
    _run_citation_processor(doc)

    d_cite = next(c for c in doc.objects_of_type("Citation") if c.props.get("citekey") == "d")
    e_cite = next(c for c in doc.objects_of_type("Citation") if c.props.get("citekey") == "e")
    d_surface = next(r for r in d_cite.realizations if r.role == "surface")
    e_surface = next(r for r in e_cite.realizations if r.role == "surface")
    assert (d_surface.start, d_surface.end) == (e_surface.start, e_surface.end)  # same line anchor

    refs_by_key = {r.props.get("citekey"): r for r in doc.objects_of_type("Reference")}
    assert "d" in refs_by_key and "e" in refs_by_key
    d_ref_surface = next(r for r in refs_by_key["d"].realizations if r.role == "surface")
    e_ref_surface = next(r for r in refs_by_key["e"].realizations if r.role == "surface")
    # each stub is anchored at its OWN citation, which is the shared line --
    # so the two References' Ranges collide too; only `citekey` tells them apart.
    assert (d_ref_surface.start, d_ref_surface.end) == (e_ref_surface.start, e_ref_surface.end)

    cites = [a for a in doc.alignments if a.kind == "cites"]
    d_edges = [a for a in cites if a.props.get("citekey") == "d"]
    e_edges = [a for a in cites if a.props.get("citekey") == "e"]
    assert len(d_edges) == 1, "d's edge must not be dropped as a false duplicate of e's"
    assert len(e_edges) == 1, "e's edge must not be dropped as a false duplicate of d's"


if __name__ == "__main__":
    for fn in [test_stub_created_at_first_citation_per_distinct_key,
               test_stub_anchored_at_first_citation_of_its_key,
               test_every_citation_links_to_its_keys_reference,
               test_fill_updates_stub_in_place_others_untouched,
               test_bibsource_bib_fill_updates_stub_in_place,
               test_link_citations_is_idempotent_against_ensure_reference_stub,
               test_two_new_keys_sharing_one_line_each_get_their_own_edge]:
        fn(); print(f"PASS {fn.__name__}")
    print("\nAll tests passed.")
