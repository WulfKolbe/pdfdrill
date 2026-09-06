"""
010 — a Reference stub at first citation.

penev_A had 81 Citations over 52 distinct citekeys but only 8 References (the
8 bibsource supplied): 44 cited keys had no Reference at all. This pins the
fix: CitationProcessor creates ONE empty (`stub`) Reference per distinct
citekey, anchored at that key's FIRST Citation and linked (a `cites`
Alignment) to every Citation with that key; the three Reference creators in
`pdfdrill.bibliography` FILL a stub in place (same id, same anchor) instead
of creating a second Reference for the same key.
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
    mod.process_document(doc)
    mod.process_objects(doc)
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


if __name__ == "__main__":
    for fn in [test_stub_created_at_first_citation_per_distinct_key,
               test_stub_anchored_at_first_citation_of_its_key,
               test_every_citation_links_to_its_keys_reference,
               test_fill_updates_stub_in_place_others_untouched]:
        fn(); print(f"PASS {fn.__name__}")
    print("\nAll tests passed.")
