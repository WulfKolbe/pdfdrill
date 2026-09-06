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


if __name__ == "__main__":
    import inspect
    mod = sys.modules[__name__]
    for name, fn in sorted(vars(mod).items()):
        if name.startswith("test_") and inspect.isfunction(fn):
            fn()
            print(f"PASS {name}")
    print("\nAll tests passed.")
