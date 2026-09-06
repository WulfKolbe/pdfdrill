"""642 — the citation link is stored, and `\\cite` points only at bibitems that exist.

Two halves, one defect class.

THE OUTPUT SIDE. 639 prints a `\\bibitem` for every Reference (a stub as
`[unresolved: key]`), so no key CAN dangle — but only if the body emits
`\\cite` at all, and it did not: penev_A's projected `.tex` held 81 Citation
objects, 52 `\\bibitem`s and **zero** `\\cite`. The LaTeX projector now
substitutes each citation GROUP in the running text exactly as 645 does for
TiddlyWiki, through the SAME group logic (`docops.citation_spans`) rather than
a second derivation of it, and it emits `\\cite` only where a Reference for the
key actually exists — a citation with none is left as its original text and
counted (`cite_without_reference`).

THE STORED SIDE. `cmd_bibsource` printed the linkers' own running total, which
is incremented when a Reference is FOUND — before the edge is built, and
whether or not either side has a surface to anchor it at. So the message could
name links the model does not hold. It now reads the SAVED state:
`bibliography.resolved_citations`, the Citations whose stored `cites` edge (or
stored `cited_reference_id`) reaches a non-stub Reference.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization
from docops.base import OperatorConfig
from docops import citation_spans
from docops.projectors import citations as cite_res
from docops.projectors.latex import LaTeXProjector
from docops.projectors.tiddlywiki import TiddlyWikiProjector


# ---------------------------------------------------------------- fixtures

def _doc(line: str, cites: list[tuple[str, str]],
         refs: list[str] | None = None) -> Document:
    """One Section + one Paragraph carrying `line`, one Citation per
    `(citekey, surface_text)` pair anchored at that text's own span, and a stub
    Reference for each key in `refs` (default: every cited key)."""
    doc = Document()
    doc.meta["bibkey"] = "D"
    mp = doc.ensure_stream("mathpix_lines")
    head = mp.append(text="1 Introduction", _page=1, _line_index=0,
                     type="section_header")
    body = mp.append(text=line, _page=1, _line_index=1, type="text")

    sec = DocObject(type="Section", props={
        "caption": "Introduction", "level": 1, "flow_index": 0, "page": 1})
    sec.add_realization(Realization(stream="mathpix_lines",
                                    start=head, end=head, role="surface"))
    doc.add(sec)

    par = DocObject(type="Paragraph", props={
        "text": line, "page": 1, "flow_index": 1})
    par.add_realization(Realization(stream="mathpix_lines",
                                    start=body, end=body, role="surface"))
    doc.add_child(sec, par)

    for i, (key, surface) in enumerate(cites):
        off = line.index(surface)
        cit = DocObject(type="Citation", props={
            "citekey": key, "page": 1, "flow_index": 2 + i})
        cit.add_realization(Realization(
            stream="mathpix_lines", start=body, end=body, role="surface",
            props={"offset": off, "length": len(surface)}))
        doc.add(cit)

    for key in (refs if refs is not None else [k for k, _ in cites]):
        ref = DocObject(type="Reference", props={
            "citekey": key, "bibkey": "D", "stub": True,
            "ref_source": "citation"})
        ref.add_realization(Realization(
            stream="mathpix_lines", start=body, end=body, role="surface",
            props={"offset": line.index(key[:5]) if key[:5] in line else 0,
                   "length": 1}))
        doc.add(ref)
    return doc


def _tex(doc) -> str:
    return LaTeXProjector(
        OperatorConfig(op="projector", classname="LaTeXProjector")).project(doc)


def _body(tex: str) -> str:
    """The document body — everything between `\\begin{document}` and the
    bibliography, so a `\\bibitem`'s own key is never mistaken for a `\\cite`."""
    start = tex.index("\\begin{document}")
    end = tex.find("\\begin{thebibliography}")
    return tex[start:end if end > 0 else len(tex)]


# ------------------------------------------- 1. one group logic, two readers

def test_tiddlywiki_and_latex_read_the_same_groups_from_one_line():
    """The shared `docops.citation_spans`: the TiddlyWiki projector's groups and
    the LaTeX resolver's groups are the SAME extents on the same line. 645
    derived them inside `tiddlywiki.py`; a second derivation in the LaTeX
    projector is how the two drift."""
    line = "As shown (Smith 1999; Foldiak 1990; Jones 2001) the effect holds."
    doc = _doc(line, [("Smith1999", "Smith 1999"), ("Jones2001", "Jones 2001")])
    body = doc.streams["mathpix_lines"].anchors[1]
    par = next(o for o in doc.objects.values() if o.type == "Paragraph")

    spans = [(r.props["offset"], r.props["length"], c.props["citekey"])
             for c in doc.objects.values() if c.type == "Citation"
             for r in c.realizations]
    tw = TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector"))
    tw_groups = [(off, length)
                 for off, length, _r, _n in tw._citation_groups(doc, body, spans)]

    lx = cite_res.resolve(doc)
    lx_groups = [(s.offset, s.length) for s in lx.subs_for(par.id)]

    assert tw_groups == lx_groups, (tw_groups, lx_groups)
    assert len(tw_groups) == 2, tw_groups        # Foldiak splits the run


# ---------------------------------------------- 2. the group reaches the .tex

def test_a_bracket_group_becomes_one_cite_with_both_keys():
    """`[a, b]` -> `\\cite{a,b}`. The group's own brackets are swallowed: LaTeX's
    `\\cite` prints its own, so keeping them gives `[[1, 2]]`."""
    line = "Prior work [a, b] shows this."
    doc = _doc(line, [("a", "a"), ("b", "b")])
    body = _body(_tex(doc))
    assert "\\cite{a,b}" in body, body
    assert "[a, b]" not in body, body
    assert "Prior work \\cite{a,b} shows this." in body, body


def test_an_unrecognised_name_inside_a_group_is_kept_verbatim():
    """`(Smith 1999; Foldiak 1990; Jones 2001)` with no Reference for Foldiak ->
    `(\\cite{Smith1999}; Foldiak 1990; \\cite{Jones2001})`.

    LOSSLESS, for 645's reason: `Foldiak 1990` is a reference the document
    actually makes and no detector recognises (645-b). A substitution that
    swallowed the parenthetical would delete it from the page; it stands as
    prose beside the keys that were recognised, which is what makes the gap
    visible instead of silent. The parentheses stay because the group does NOT
    wrap the whole of what is between them."""
    line = "As shown (Smith 1999; Foldiak 1990; Jones 2001) the effect holds."
    doc = _doc(line, [("Smith1999", "Smith 1999"), ("Jones2001", "Jones 2001")])
    body = _body(_tex(doc))
    assert ("As shown (\\cite{Smith1999}; Foldiak 1990; \\cite{Jones2001}) "
            "the effect holds." in body), body


def test_a_citation_with_no_reference_keeps_its_text_and_is_counted():
    """"Only where a Reference exists". A `\\cite{key}` with no `\\bibitem{key}`
    prints as a bold `?`; the citation is emitted as the text it was and
    counted, so a document where this happens says so."""
    line = "Prior work (Smith 1999) shows this."
    doc = _doc(line, [("Smith1999", "Smith 1999")], refs=[])
    res = cite_res.resolve(doc)
    assert res.counts["cite_without_reference"] == 1, res.counts
    body = _body(_tex(doc))
    assert "\\cite" not in body, body
    assert "Prior work (Smith 1999) shows this." in body, body


def test_every_cite_key_in_the_projection_has_a_bibitem():
    """639 + 642 together: the body's keys are a SUBSET of the bibliography's.
    This is the check the user's 40-keys-against-8-bibitems report is about."""
    import re
    line = "Prior work [a, b] and (Smith 1999) show this."
    doc = _doc(line, [("a", "a"), ("b", "b"), ("Smith1999", "Smith 1999")])
    tex = _tex(doc)
    keys = {k.strip() for m in re.finditer(r"\\cite\{([^}]*)\}", _body(tex))
            for k in m.group(1).split(",")}
    bibitems = set(re.findall(r"\\bibitem\{([^}]*)\}", tex))
    assert keys == {"a", "b", "Smith1999"}, keys
    assert keys <= bibitems, (keys - bibitems, bibitems)


def test_the_cite_key_is_the_references_key_not_the_in_text_label():
    """A `\\bibitem` carries the REFERENCE's citekey. When a linker resolved an
    in-text label (`ASV02`) to a differently-keyed gold Reference
    (`smith2002`), `\\cite{ASV02}` would dangle — the stored link
    (`cited_reference_id`) is what the projector emits."""
    line = "Prior work [ASV02] shows this."
    doc = _doc(line, [("ASV02", "ASV02")], refs=["smith2002"])
    gold = next(o for o in doc.objects.values() if o.type == "Reference")
    gold.props.pop("stub", None)
    cit = next(o for o in doc.objects.values() if o.type == "Citation")
    cit.props["cited_reference_id"] = gold.id
    body = _body(_tex(doc))
    assert "\\cite{smith2002}" in body, body
    assert "ASV02" not in body, body


# ---------------------------------------- 3. the message reads STORED state

def test_resolved_citations_counts_what_the_model_holds():
    """The stored state: a Citation counts as linked only when its own `cites`
    edge lands on a NON-stub Reference (or its `cited_reference_id` names
    one)."""
    from pdfdrill import bibliography as B
    from docmodel.modules.citation import ensure_reference_stub

    line = "Prior work [a, b] shows this."
    doc = _doc(line, [("a", "a"), ("b", "b")], refs=[])
    for c in [o for o in doc.objects.values() if o.type == "Citation"]:
        ensure_reference_stub(doc, c, "D")
    assert B.resolved_citations(doc) == 0        # two stubs, two edges, 0 gold
    ref_a = next(r for r in doc.objects.values()
                 if r.type == "Reference" and r.props.get("citekey") == "a")
    ref_a.props.pop("stub")                      # bibsource fills ONE of them
    assert B.resolved_citations(doc) == 1


def test_bibsource_message_equals_the_stored_count():
    """3 in-text citations, 1 gold entry -> "1/3", and the saved model holds
    exactly that. The old message read the linker's running total, which counts
    a Reference it FOUND whether or not an edge was ever stored."""
    import tempfile
    from pdfdrill import bibliography as B
    from pdfdrill.sidecar import Sidecar
    from pdfdrill.commands import cmd_bibsource, MODEL_BUILT
    from pdfdrill.model_io import load_model

    bbl = ("\\begin{thebibliography}{XYZ99}\n"
           "\\bibitem[Awo10]{awodey2010category}\n"
           "Steve Awodey.\n"
           "\\newblock {\\em Category Theory}.\n"
           "\\end{thebibliography}\n")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pdf = d / "doc.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
        (d / "doc.bbl").write_text(bbl)
        doc = Document()
        mp = doc.ensure_stream("mathpix_lines")
        a = mp.append(type="text", _page=1, text="See [Awo10], [Zzz99], [Qqq88].")
        for i, key in enumerate(("Awo10", "Zzz99", "Qqq88")):
            c = DocObject(type="Citation", props={"citekey": key, "page": 1,
                                                  "flow_index": i})
            c.add_realization(Realization(stream="mathpix_lines", start=a, end=a,
                                          role="surface"))
            doc.add(c)
        sc = Sidecar(pdf); sc.blob_dir.mkdir(parents=True, exist_ok=True)
        (sc.blob_dir / "model.docmodel.json").write_text(json.dumps(doc.to_dict()))
        sc.add_fact(MODEL_BUILT); sc.save()

        out = cmd_bibsource(pdf)
        assert "1/3 in-text citations linked" in out, out
        saved = load_model(sc.blob_dir / "model.docmodel.json")
        assert B.resolved_citations(saved) == 1


def test_the_message_cannot_exceed_what_the_model_stores():
    """The defect itself. A Citation with NO surface Realization has nowhere to
    anchor a `cites` edge, and the linker counts it anyway — it increments the
    moment it MATCHES a Reference. Two `Awo10` citations, one of them
    unanchored, and one gold entry: the linker's own total is 2, the model holds
    1, and the message says 1."""
    import tempfile
    from pdfdrill import bibliography as B
    from pdfdrill.sidecar import Sidecar
    from pdfdrill.commands import cmd_bibsource, MODEL_BUILT
    from pdfdrill.model_io import load_model

    bbl = ("\\begin{thebibliography}{XYZ99}\n"
           "\\bibitem[Awo10]{awodey2010category}\n"
           "Steve Awodey.\n"
           "\\newblock {\\em Category Theory}.\n"
           "\\end{thebibliography}\n")
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pdf = d / "doc.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
        (d / "doc.bbl").write_text(bbl)
        doc = Document()
        mp = doc.ensure_stream("mathpix_lines")
        a = mp.append(type="text", _page=1, text="See [Awo10] and [Awo10].")
        for i, anchored in enumerate((True, False)):
            c = DocObject(type="Citation", props={"citekey": "Awo10", "page": 1,
                                                  "flow_index": i})
            if anchored:
                c.add_realization(Realization(stream="mathpix_lines", start=a,
                                             end=a, role="surface"))
            doc.add(c)
        c = DocObject(type="Citation", props={"citekey": "Zzz99", "page": 1,
                                              "flow_index": 2})
        c.add_realization(Realization(stream="mathpix_lines", start=a, end=a,
                                      role="surface"))
        doc.add(c)
        sc = Sidecar(pdf); sc.blob_dir.mkdir(parents=True, exist_ok=True)
        (sc.blob_dir / "model.docmodel.json").write_text(json.dumps(doc.to_dict()))
        sc.add_fact(MODEL_BUILT); sc.save()

        out = cmd_bibsource(pdf)
        saved = load_model(sc.blob_dir / "model.docmodel.json")
        # what the LINKER would have said, on the saved document:
        assert B.link_citations_by_label(saved)["linked"] == 2
        assert B.resolved_citations(saved) == 1
        assert "1/3 in-text citations linked" in out, out
