"""
010 fix round 4 — the stub Reference and the LINKERS/GATES around it.

Rounds 0-3 built `ensure_reference_stub` (a stub Reference per citekey at the
first Citation) and made edge creation idempotent. The review of 639 found the
rest of the system had not been told: a linker that resolves a Citation to a
REAL Reference left the stub behind as a permanent duplicate; three "are there
References yet" gates went permanently false because a stub is a Reference;
two callers read "edges added this call" as "citations linked" and fell into a
destructive branch; the exact-citekey stub pre-empted the fuzzy surname match;
`bibliography --force` retracted a gold-filled Reference by provenance; two
more Citation creators minted no stub at all.

Each test below is one of those findings.
"""
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization, Range, Alignment
from docmodel.modules.citation import ensure_reference_stub
from pdfdrill import bibliography as B


# One \bibitem: alpha label ASV02, citekey smith2002 — the review's own example.
_BBL1 = r"""\begin{thebibliography}{XYZ99}
\bibitem[ASV02]{smith2002}
J.~Smith.
\newblock {\em A Title}.
\newblock AMS, 2002.
\end{thebibliography}
"""

_BIB1 = r"""
@book{smith2002, title={A Title}, author={Smith, J.}, year={2002}}
"""


def _cited_doc(citekey="ASV02", text="As shown in [ASV02], the result holds.",
               added_by=None):
    """A one-line document with one Citation and the stub every Citation
    creator now mints for it."""
    doc = Document()
    doc.meta["bibkey"] = "T"
    mp = doc.ensure_stream("mathpix_lines")
    a = mp.append(type="text", text=text, _page=1)
    props = {"citekey": citekey, "page": 1}
    if added_by:
        props["added_by"] = added_by
    cit = DocObject(type="Citation", props=props)
    cit.add_realization(Realization(stream="mathpix_lines", start=a, end=a,
                                    role="surface"))
    doc.add(cit)
    ensure_reference_stub(doc, cit, "T")
    return doc, cit


def _cites(doc):
    return [a for a in doc.alignments if a.kind == "cites"]


# --------------------------------------------------------------- item 1
def test_label_linker_absorbs_the_stub_into_the_gold_reference():
    """CRITICAL — `link_citations_by_label` added its `cites` edge directly and
    ignored the stub, so a Citation `[ASV02]` ended with TWO edges to TWO
    References (its own stub `ASV02`, and the real `smith2002` labelled
    ASV02) and the stub was permanent. A linker that resolves a Citation to a
    Reference that is NOT its stub must MERGE the stub into it."""
    doc, cit = _cited_doc()
    assert len(doc.objects_of_type("Reference")) == 1          # the stub
    assert doc.objects_of_type("Reference")[0].props.get("stub") is True

    assert B.ingest_bbl(doc, _BBL1) == 1                       # gold: smith2002
    refs = doc.objects_of_type("Reference")
    assert len(refs) == 2                                      # stub + gold, for now

    B.link_citations_by_label(doc)

    refs = doc.objects_of_type("Reference")
    assert [r.props.get("citekey") for r in refs] == ["smith2002"], \
        [(r.props.get("citekey"), r.props.get("stub")) for r in refs]
    gold = refs[0]
    assert gold.props.get("label") == "ASV02"
    assert not gold.props.get("stub")
    # the gold Reference keeps its OWN anchor (the `references` stream), not
    # the stub's citation-line anchor.
    assert any(r.stream == "references" for r in gold.realizations)

    edges = _cites(doc)
    assert len(edges) == 1, [(e.props, e.right.stream) for e in edges]
    assert edges[0].right.stream == "references"
    assert cit.props.get("cited_reference_id") == gold.id


# --------------------------------------------------------------- item 2
def test_cmd_bibsource_does_not_wipe_correctly_linked_citations():
    """CRITICAL — `link_citations` returns edges ADDED, and `cmd_bibsource`
    read that as "citations linked": on a document whose citations were
    already linked (by `ensure_reference_stub`, at creation time) it got 0 and
    fell into its destructive "wipe every bibliography-added Citation and
    re-detect" branch. The branch must run only when nothing is linked in the
    TOTAL sense."""
    from pdfdrill import commands as K, model_io
    from pdfdrill.sidecar import Sidecar

    doc, cit = _cited_doc(citekey="smith2002",
                          text="Building on (Smith, 2002), we begin.",
                          added_by="bibliography")
    cit_id = cit.id

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pdf = d / "t.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        (d / "t.bbl").write_text(_BBL1)
        (d / "t.bib").write_text(_BIB1)
        sc = Sidecar(pdf)
        model_io.save_model(K._model_path(sc), doc)
        sc.add_fact(K.MODEL_BUILT)
        sc.save()

        out = K.cmd_bibsource(pdf)
        after = model_io.load_model(K._model_path(sc))

    ids = {c.id for c in after.objects_of_type("Citation")}
    assert cit_id in ids, (out, sorted(ids))
    assert len(ids) == 1
    # the stub was filled in place by the .bbl, so it is now a real Reference
    refs = after.objects_of_type("Reference")
    assert len(refs) == 1 and not refs[0].props.get("stub")
    assert "1/1 in-text citations linked" in out, out


# --------------------------------------------------------------- item 3
def test_has_filled_references_ignores_stubs():
    doc, _ = _cited_doc()
    assert not B.has_filled_references(doc)      # only a stub exists
    B.ingest_bbl(doc, _BBL1)
    assert B.has_filled_references(doc)


def test_auto_bibliography_gate_fires_on_a_stub_only_document():
    """CRITICAL — `_auto_bibliography` returned early on "any Reference
    exists", which a stub makes permanently true, so a projection that needed
    References never built them."""
    from pdfdrill import commands as K, model_io
    from pdfdrill.sidecar import Sidecar

    doc, _ = _cited_doc()
    sec = DocObject(type="Section", props={"caption": "References"})
    doc.add(sec)

    calls = []
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pdf = d / "t.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf)
        model_io.save_model(K._model_path(sc), doc)
        sc.add_fact(K.MODEL_BUILT)
        sc.save()

        real = K.cmd_bibliography
        K.cmd_bibliography = lambda p, *a, **k: (calls.append(p), "")[1]
        try:
            K._auto_bibliography(pdf, sc, doc)
        finally:
            K.cmd_bibliography = real
    assert calls == [pdf], "the gate must not read a stub as 'References exist'"


def test_tiddlers_gate_fires_on_a_stub_only_document():
    """CRITICAL — same gate, the `cmd_tiddlers` copy."""
    from pdfdrill import commands as K, model_io
    from pdfdrill.sidecar import Sidecar

    class _Fired(Exception):
        pass

    doc, _ = _cited_doc()
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pdf = d / "t.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf)
        model_io.save_model(K._model_path(sc), doc)
        sc.add_fact(K.MODEL_BUILT)
        sc.save()

        real = K.cmd_bibliography

        def _boom(p, *a, **k):
            raise _Fired()

        K.cmd_bibliography = _boom
        try:
            with pytest.raises(_Fired):
                K.cmd_tiddlers(pdf, force=True)
        finally:
            K.cmd_bibliography = real


def test_citation_pass_builds_when_only_stubs_exist():
    """CRITICAL — `CitationPass` gated on "no Reference objects", and counted
    `already` over EVERY `cites` edge. A stub-only document therefore reported
    "already linked" and never built the real bibliography from the source."""
    from passes.base import PassContext
    from passes.builtin import CitationPass

    doc, _ = _cited_doc(citekey="smith2002")
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "texsrc"
        src.mkdir()
        (src / "main.tex").write_text(
            r"\bibliography{biblio}" "\n" r"\cite{smith2002}" "\n")
        (src / "biblio.bib").write_text(_BIB1)
        doc.meta["latex_source_dir"] = str(src)
        res = CitationPass().run(PassContext(doc=doc))

    assert res.status == "ran"
    assert res.changed, res.summary
    refs = doc.objects_of_type("Reference")
    assert len(refs) == 1 and not refs[0].props.get("stub"), \
        [(r.props.get("citekey"), r.props.get("stub")) for r in refs]
    assert res.stats.get("linked") == 1, res.stats


def test_citation_pass_already_counts_only_filled_references():
    """The `already` short-circuit must not count a stub edge as "linked"."""
    from passes.base import PassContext
    from passes.builtin import CitationPass

    doc, _ = _cited_doc(citekey="smith2002")
    assert _cites(doc)                       # the stub edge exists
    res = CitationPass().run(PassContext(doc=doc))
    assert "already linked" not in res.summary, res.summary


# --------------------------------------------------------------- item 4
def test_fuzzy_surname_match_beats_the_citations_own_stub():
    """IMPORTANT — `ensure_reference_stub`'s exact-citekey match made
    `link_citations`' surname-prefix fallback (`[Asai]` -> `Asai2023`) dead:
    the Citation was already "linked" (to its own stub) by the time the
    smarter match got a turn. A stub-linked Citation is UNRESOLVED for
    matching purposes, and a fuzzy hit absorbs the stub."""
    doc, cit = _cited_doc(citekey="Asai", text="See [Asai] for details.")
    s = doc.ensure_stream("references")
    ra = s.append(type="ref")
    gold = DocObject(type="Reference", props={"citekey": "Asai2023",
                                              "ref_source": "bbl"})
    gold.add_realization(Realization(stream="references", start=ra, end=ra,
                                     role="surface"))
    doc.add(gold)

    B.link_citations(doc)

    refs = doc.objects_of_type("Reference")
    assert [r.props.get("citekey") for r in refs] == ["Asai2023"], \
        [(r.props.get("citekey"), r.props.get("stub")) for r in refs]
    edges = _cites(doc)
    assert len(edges) == 1, [e.props for e in edges]
    assert edges[0].right == Range("references", ra, ra)


# --------------------------------------------------------------- item 5
def test_bibliography_force_keeps_a_gold_filled_reference():
    """IMPORTANT — the `added_by` retraction deleted a Reference that
    bibsource/bibfetch had FILLED, because its STUB came from a detector and
    inherited `added_by: "bibliography"`. A filled Reference survives
    `bibliography --force`; only a still-stub one (or one THIS command filled,
    `ref_source: "text"`) is retracted."""
    from pdfdrill import commands as K, model_io
    from pdfdrill.sidecar import Sidecar

    doc = Document()
    doc.meta["bibkey"] = "T"
    mp = doc.ensure_stream("mathpix_lines")
    mp.append(text="Building on (Asai, 2023), we begin.", _page=1, type="text")
    mp.append(text="Finally, (Wu, 2024) agrees.", _page=1, type="text")

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pdf = d / "t.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf)
        model_io.save_model(K._model_path(sc), doc)
        sc.add_fact(K.MODEL_BUILT)
        sc.save()

        K.cmd_bibliography(pdf, force=True)
        built = model_io.load_model(K._model_path(sc))
        asai = next(r for r in built.objects_of_type("Reference")
                    if r.props.get("citekey") == "Asai2023")
        assert asai.props.get("added_by") == "bibliography"   # inherited from the detector
        # bibsource/bibfetch fills it: the stub becomes gold.
        asai.props.pop("stub", None)
        asai.props.update({"ref_source": "bbl", "raw_text": "Asai, T. A Real Entry. 2023.",
                           "author": "Asai, T.", "year": "2023"})
        gold_id = asai.id
        model_io.save_model(K._model_path(sc), built)

        def state():
            m = model_io.load_model(K._model_path(sc))
            return (sorted(c.props.get("citekey")
                           for c in m.objects_of_type("Citation")),
                    sum(1 for a in m.alignments if a.kind == "cites"),
                    m)

        K.cmd_bibliography(pdf, force=True)
        cits2, edges2, after = state()
        # 010 fix round 5 -- and again, and again: keeping the gold Reference
        # (round 4) must not cost the Citation that cites it. `ref_anchors`
        # excluded EVERY Reference realization on mathpix_lines, and a stub
        # filled in place keeps its CITATION's line anchor -- so that line was
        # excluded from re-detection, the Citation (retracted as
        # `added_by == "bibliography"`) never came back, and its `cites` edge
        # survived pointing at a dead left side.
        K.cmd_bibliography(pdf, force=True)
        cits3, edges3, _ = state()

    assert cits2 == ["Asai2023", "Wu2024"], cits2
    assert cits3 == cits2, (cits2, cits3)
    assert edges3 == edges2 == 2, (edges2, edges3)

    survivor = after.objects.get(gold_id)
    assert survivor is not None, "a gold-filled Reference must survive --force"
    assert survivor.props.get("ref_source") == "bbl"
    assert not survivor.props.get("stub")
    # and its citation is re-detected and re-linked to it, not to a new stub
    assert len([r for r in after.objects_of_type("Reference")
                if r.props.get("citekey") == "Asai2023"]) == 1


# --------------------------------------------------------------- item 10
def test_drop_dangling_cites_drops_an_edge_with_a_dead_left_side():
    """010 fix round 5 — `drop_dangling_cites` pruned by the RIGHT side only,
    so an edge whose CITATION had just been retracted survived: the model then
    carried a `cites` Alignment from nothing to a Reference, and the edge count
    outran the Citation count. Either dead side now prunes the edge."""
    doc, cit = _cited_doc()
    assert len(_cites(doc)) == 1
    doc.objects.pop(cit.id)                    # retract the Citation only
    B.drop_dangling_cites(doc)
    assert _cites(doc) == []

    # the live case is untouched
    doc2, _ = _cited_doc()
    B.drop_dangling_cites(doc2)
    assert len(_cites(doc2)) == 1


# --------------------------------------------------------------- item 6
def test_annotate_force_keeps_the_citation_to_reference_edges():
    """IMPORTANT — `cmd_annotate --force` blanket-cleared every `cites`
    Alignment and only ever re-created its OWN (Link -> Citation) ones, so a
    rebuild of the annotation layer silently destroyed the model-build
    Citation -> Reference edges. `cites` is a model-build invariant now."""
    from pdfdrill import commands as K, model_io
    from pdfdrill.sidecar import Sidecar

    doc, cit = _cited_doc()
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pdf = d / "t.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf)
        model_io.save_model(K._model_path(sc), doc)
        sc.add_fact(K.MODEL_BUILT)
        sc.set_urls([{"page": 1, "uri": "https://example.org/", "kind": "url",
                      "rect": [0, 0, 1, 1]}])
        sc.add_fact(K.URLS_KNOWN)
        sc.save()

        K.cmd_annotate(pdf)
        before = model_io.load_model(K._model_path(sc))
        n_before = sum(1 for a in before.alignments if a.kind == "cites")
        assert n_before == 1

        K.cmd_annotate(pdf, force=True)
        after = model_io.load_model(K._model_path(sc))

    assert sum(1 for a in after.alignments if a.kind == "cites") == n_before


# --------------------------------------------------------------- item 7
def test_latex_source_cite_mints_a_stub():
    """IMPORTANT — the arXiv e-print lane creates one Citation per `\\cite`
    key and minted no stub at all."""
    from pdfdrill import latex_source as LS

    with tempfile.TemporaryDirectory() as d:
        tex = Path(d) / "main.tex"
        tex.write_text(r"\documentclass{article}" "\n" r"\begin{document}" "\n"
                       r"Intro \cite{alpha} and \citep{beta}." "\n"
                       r"\end{document}" "\n")
        doc = LS.build_source_model(str(tex), bibkey="T")
    refs = {r.props.get("citekey"): r for r in doc.objects_of_type("Reference")}
    assert sorted(refs) == ["alpha", "beta"], sorted(refs)
    assert all(r.props.get("stub") is True for r in refs.values())
    assert len(_cites(doc)) == 2


def test_markdown_cite_without_a_reference_mints_a_stub():
    """IMPORTANT — `markdown_source.cite_objects` linked only when a gold
    Reference already existed and added its edge directly."""
    from pdfdrill import markdown_source as MS

    doc = MS.build_markdown_model(
        "# T\n\n## Body\n\nUses \\cite{nowhere2020}.\n", bibkey="T")
    refs = {r.props.get("citekey"): r for r in doc.objects_of_type("Reference")}
    assert "nowhere2020" in refs, sorted(refs)
    assert refs["nowhere2020"].props.get("stub") is True
    assert len(_cites(doc)) == 1


# --------------------------------------------------------------- 648
def _prose_doc(pairs, bibkey="T"):
    """One Paragraph per (surname, year) parenthetical citation -- the shape
    `bibliography.detect_author_year_in_objects` (bibsource's own fallback
    detector) scans: a Paragraph object whose `text` prop reproduces its own
    `mathpix_lines` anchor's text exactly, so `_span_on_its_own_line` can
    locate the group. No Citation exists yet -- these are DETECTABLE, not
    detected."""
    doc = Document()
    doc.meta["bibkey"] = bibkey
    mp = doc.ensure_stream("mathpix_lines")
    for i, (surname, year) in enumerate(pairs):
        text = f"Building on ({surname}, {year}), we continue the argument."
        a = mp.append(type="text", text=text, text_display=text, _page=1)
        p = DocObject(type="Paragraph", props={"text": text, "flow_index": i})
        p.add_realization(Realization(stream="mathpix_lines", start=a, end=a,
                                      role="surface"))
        doc.add(p)
    return doc


def test_bibliography_message_reads_stored_state_after_bibsource_fills_gold():
    """648 -- measured on a fixture built for this task: `pdfdrill bibsource
    --bib` fills 1 of 3 detected author-year citations from gold, leaving 2
    citation-stubs; `pdfdrill bibliography` then runs bare (drill_full's own
    order and its own flags -- no --force on either step). The OBJECTS are
    exactly right (010/642 already deliver this: 3 Citations, 1 filled + 2
    stub References, 3 `cites` edges, unchanged by the bibliography call) --
    but the MESSAGE was wrong: `cmd_bibliography`'s early-return path printed
    the SIDECAR's stale `bibliography_*` evidence (never set on this
    document, since bibliography's own heuristic parse never got a turn),
    literally 'Parsed 0 bibliography entries (0 with a year)' with no mention
    that the document already holds 3 citations, 1 of them linked to a filled
    Reference. The fix is the count (rule 10): the message now reads the
    STORED state, exactly as 642 made `bibsource`'s message do."""
    from pdfdrill import commands as K, model_io
    from pdfdrill.sidecar import Sidecar

    doc = _prose_doc([("Asai", "2023"), ("Wu", "2024"), ("Lee", "2025")])
    bib = "@article{asai2023, title={T}, author={Asai}, year={2023}}\n"

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pdf = d / "t.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        bib_path = d / "t.bib"
        bib_path.write_text(bib)
        sc = Sidecar(pdf)
        model_io.save_model(K._model_path(sc), doc)
        sc.add_fact(K.MODEL_BUILT)
        sc.save()

        out_bibsource = K.cmd_bibsource(pdf, bib_path=str(bib_path))
        after_bibsource = model_io.load_model(K._model_path(sc))
        cits = after_bibsource.objects_of_type("Citation")
        refs = after_bibsource.objects_of_type("Reference")
        assert len(cits) == 3, [c.props.get("citekey") for c in cits]
        assert len(refs) == 3, [r.props.get("citekey") for r in refs]
        assert sum(1 for r in refs if not r.props.get("stub")) == 1
        cites_before = sorted((c.id, c.props.get("citekey")) for c in cits)

        out_bibliography = K.cmd_bibliography(pdf)
        after_bibliography = model_io.load_model(K._model_path(sc))

    # the objects: untouched by the bibliography call (early return, or a
    # real run that MUST NOT re-detect what already exists -- either way).
    cits2 = after_bibliography.objects_of_type("Citation")
    assert sorted((c.id, c.props.get("citekey")) for c in cits2) == cites_before
    assert len(after_bibliography.objects_of_type("Reference")) == 3

    # the message: reads the STORED state, not a stale/empty cache.
    assert "3 citations" in out_bibliography, out_bibliography
    assert "1 linked to filled references" in out_bibliography, out_bibliography
    assert "2 to stubs" in out_bibliography, out_bibliography


def test_bibliography_is_idempotent_a_second_bare_call_after_bibsource():
    """648 -- a second bare `bibliography` call (drill_full never issues one,
    but a re-run of the tool, or a retry, might) changes nothing: same
    Citation ids, same count, same message."""
    from pdfdrill import commands as K, model_io
    from pdfdrill.sidecar import Sidecar

    doc = _prose_doc([("Asai", "2023"), ("Wu", "2024"), ("Lee", "2025")])
    bib = "@article{asai2023, title={T}, author={Asai}, year={2023}}\n"

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pdf = d / "t.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        bib_path = d / "t.bib"
        bib_path.write_text(bib)
        sc = Sidecar(pdf)
        model_io.save_model(K._model_path(sc), doc)
        sc.add_fact(K.MODEL_BUILT)
        sc.save()

        K.cmd_bibsource(pdf, bib_path=str(bib_path))
        out1 = K.cmd_bibliography(pdf)
        state1 = model_io.load_model(K._model_path(sc))
        out2 = K.cmd_bibliography(pdf)
        state2 = model_io.load_model(K._model_path(sc))

    ids1 = sorted((c.id, c.props.get("citekey"))
                 for c in state1.objects_of_type("Citation"))
    ids2 = sorted((c.id, c.props.get("citekey"))
                 for c in state2.objects_of_type("Citation"))
    assert ids1 == ids2, (ids1, ids2)
    assert len(state1.objects_of_type("Reference")) == len(state2.objects_of_type("Reference")) == 3
    assert out1 == out2, (out1, out2)


def test_bibliography_force_never_duplicates_a_gold_reference_from_the_heuristic_section():
    """648 -- ruling item 1: 'bibliography MAY parse the References SECTION
    only for citekeys that have NO filled Reference (gold wins; a heuristic
    entry never overwrites a gold one)'. `cmd_bibliography --force`'s
    cleanup deliberately KEEPS a gold-filled Reference (010 fix round 4) and
    then unconditionally re-runs `parse_bibliography`/`add_reference_objects`
    -- and the heuristic's OWN citekey generator (`_citekey`: surname + year)
    produces the exact same string a gold `.bbl`/`.bib` citekey has whenever
    the printed References section names the same author+year the gold entry
    already covers ('Asai, T.' + '2023' -> 'Asai2023' either way). Before
    this fix `add_reference_objects` only checked STUB references by citekey
    -- a citekey that already named a FILLED (non-stub) Reference fell
    through to its `else` branch and created a SECOND Reference object for
    the same work."""
    from pdfdrill import commands as K, model_io
    from pdfdrill.sidecar import Sidecar

    doc = Document()
    doc.meta["bibkey"] = "T"
    mp = doc.ensure_stream("mathpix_lines")
    mp.append(text="Building on (Asai, 2023), we begin.", _page=1, type="text")
    mp.append(text="References", _page=2, type="section_header")
    mp.append(text="Asai, T. A Real Entry Reprinted. 2023.", _page=2, type="text")

    # A gold Reference already FILLED (as bibsource/bibfetch would leave it),
    # same citekey the heuristic parse below will independently generate.
    gold = DocObject(type="Reference", props={
        "citekey": "Asai2023", "ref_source": "bbl", "author": "Asai, T.",
        "year": "2023", "raw_text": "Asai, T. The Original Gold Entry. 2023.",
        "added_by": "bibliography",
    })
    rstream = doc.ensure_stream("references")
    ra = rstream.append(citekey="Asai2023")
    gold.add_realization(Realization(stream="references", start=ra, end=ra,
                                     role="surface", provenance="bbl"))
    doc.add(gold)

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pdf = d / "t.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf)
        model_io.save_model(K._model_path(sc), doc)
        sc.add_fact(K.MODEL_BUILT)
        sc.save()

        K.cmd_bibliography(pdf, force=True)
        after = model_io.load_model(K._model_path(sc))

    asai_refs = [r for r in after.objects_of_type("Reference")
                if r.props.get("citekey") == "Asai2023"]
    assert len(asai_refs) == 1, [r.props for r in asai_refs]
    assert asai_refs[0].id == gold.id
    assert asai_refs[0].props.get("ref_source") == "bbl"
    assert asai_refs[0].props.get("raw_text") == "Asai, T. The Original Gold Entry. 2023."


def test_bare_bibliography_is_idempotent_when_no_reference_is_ever_filled():
    """648/010's OPEN item -- REPRODUCED LIVE on the real corpus while
    measuring this task (penev_A: 81 -> 161 -> 241 Citation objects across
    two bare `pdfdrill bibliography` calls; restored from
    `out/648/model.before.json` after the fact, never committed). penev_A's
    heuristic References-section parse finds 0 entries (no heading MathPix
    segments), so every Reference it ever gets is a citekey stub
    (`ensure_reference_stub`, 010) -- `existing` (non-stub References) is
    permanently empty, the `if existing and not force: return` gate never
    fires, and a bare call always re-runs `detect_numeric_citations`/
    `detect_author_year_citations` unconditionally. Without an identity
    check tying a detected span to a Citation that already covers it, they
    mint a SECOND Citation for the SAME text on every call -- unbounded
    duplication, no `--force` required."""
    from pdfdrill import commands as K, model_io
    from pdfdrill.sidecar import Sidecar

    doc = Document()
    doc.meta["bibkey"] = "T"
    mp = doc.ensure_stream("mathpix_lines")
    mp.append(text="Building on (Asai, 2023), we begin.", _page=1, type="text")
    mp.append(text="Finally, (Wu, 2024) agrees.", _page=1, type="text")

    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pdf = d / "t.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        sc = Sidecar(pdf)
        model_io.save_model(K._model_path(sc), doc)
        sc.add_fact(K.MODEL_BUILT)
        sc.save()

        K.cmd_bibliography(pdf)
        first = model_io.load_model(K._model_path(sc))
        keys1 = sorted(c.props.get("citekey")
                       for c in first.objects_of_type("Citation"))

        K.cmd_bibliography(pdf)
        second = model_io.load_model(K._model_path(sc))
        keys2 = sorted(c.props.get("citekey")
                       for c in second.objects_of_type("Citation"))

        K.cmd_bibliography(pdf)
        third = model_io.load_model(K._model_path(sc))
        keys3 = sorted(c.props.get("citekey")
                       for c in third.objects_of_type("Citation"))

    assert keys1 == ["Asai2023", "Wu2024"], keys1
    assert keys2 == keys1, (keys1, keys2)          # NOT duplicated
    assert keys3 == keys1, (keys1, keys3)          # NOT duplicated a 2nd time
    assert sum(1 for a in third.alignments if a.kind == "cites") == 2


def test_citation_link_breakdown_counts_filled_stub_and_unlinked():
    """648 -- the STORED-state breakdown a message reports: total Citations,
    how many resolve (via a stored `cites` edge) to a FILLED Reference, how
    many to a stub."""
    doc, _ = _cited_doc(citekey="Asai2023")   # 1 Citation, 1 stub
    doc2, cit2 = _cited_doc(citekey="Wu2024")
    # merge doc2's objects/alignments into doc so there are 2 Citations
    for o in doc2.objects.values():
        doc.objects[o.id] = o
    doc.streams["mathpix_lines"].anchors.extend(
        a for a in doc2.streams["mathpix_lines"].anchors
        if a not in doc.streams["mathpix_lines"].anchors)
    doc.streams["mathpix_lines"].payload.update(doc2.streams["mathpix_lines"].payload)
    doc.alignments.extend(doc2.alignments)

    breakdown = B.citation_link_breakdown(doc)
    assert breakdown == {"total": 2, "filled": 0, "stub": 2, "unlinked": 0}, breakdown

    asai = next(r for r in doc.objects_of_type("Reference")
               if r.props.get("citekey") == "Asai2023")
    asai.props.pop("stub")                    # bibsource fills it
    breakdown = B.citation_link_breakdown(doc)
    assert breakdown == {"total": 2, "filled": 1, "stub": 1, "unlinked": 0}, breakdown


if __name__ == "__main__":
    import inspect
    mod = sys.modules[__name__]
    for name, fn in sorted(vars(mod).items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            fn()
            print(f"PASS {name}")
    print("\nAll tests passed.")
