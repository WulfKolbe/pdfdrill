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


# ------------------------------------------- 4. ONE resolver owns citations

def _numbered_ref_doc(line: str, cite: tuple[str, str] | None,
                      ref_key: str = "Realname2001", ref_number: int = 5):
    """A line, optionally one Citation over a span of it, and one FILLED
    Reference carrying `number` — the map `latex_pipeline.reference_map` builds
    and the numeric `[N]` fallback resolves through."""
    doc = Document()
    doc.meta["bibkey"] = "D"
    mp = doc.ensure_stream("mathpix_lines")
    head = mp.append(text="1 Introduction", _page=1, _line_index=0,
                     type="section_header")
    body = mp.append(text=line, _page=1, _line_index=1, type="text")
    refs = doc.ensure_stream("references")
    ra = refs.append(text=ref_key)

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

    if cite is not None:
        key, surface = cite
        off = line.index(surface)
        c = DocObject(type="Citation", props={
            "citekey": key, "page": 1, "flow_index": 2})
        c.add_realization(Realization(
            stream="mathpix_lines", start=body, end=body, role="surface",
            props={"offset": off, "length": len(surface)}))
        doc.add(c)

    ref = DocObject(type="Reference", props={
        "citekey": ref_key, "bibkey": "D", "number": ref_number,
        "author": "Realname", "year": "2001", "title": "A real entry"})
    ref.add_realization(Realization(stream="references", start=ra, end=ra,
                                    role="bibliography"))
    doc.add(ref)
    return doc


def test_a_bracket_a_citation_claims_is_never_rewritten_by_the_number_map():
    """THE MIS-WIRE. `_prose` used to run `latex_pipeline.resolve_citations`
    AFTER the citation resolver had already decided. That pass knows only
    `{Reference.number: citekey}` — not which Citation owns the bracket, and not
    that the resolver deliberately left this one alone. A Citation `NoSuchKey`
    over `[5]` (no Reference: `cite_without_reference == 1`) sat beside an
    unrelated Reference numbered 5, and the document silently cited
    `Realname2001` in its place. It compiles, and it is wrong.

    ONE resolver owns citations: a bracket a Citation covers follows the
    CITATION's decision."""
    line = "Prior work [5] shows this."
    doc = _numbered_ref_doc(line, ("NoSuchKey", "[5]"))
    res = cite_res.resolve(doc)
    assert res.counts["cite_without_reference"] == 1, res.counts
    body = _body(_tex(doc))
    assert "Realname2001" not in body, body
    assert "\\cite" not in body, body
    assert "Prior work [5] shows this." in body, body


def test_a_bare_numeric_bracket_no_citation_claims_still_resolves():
    """The fallback's LEGITIMATE case, kept: `[5]` that no Citation object
    covers, with a Reference numbered 5, still becomes `\\cite{Realname2001}`.
    Removing the old pass without this would have dropped a real capability."""
    line = "Prior work [5] shows this."
    doc = _numbered_ref_doc(line, None)
    res = cite_res.resolve(doc)
    assert res.counts["numeric_brackets_resolved"] == 1, res.counts
    body = _body(_tex(doc))
    assert "Prior work \\cite{Realname2001} shows this." in body, body


def test_a_bracket_whose_numbers_are_not_all_references_stays_raw():
    """An array index / an interval `[0,1]` is not a citation. The fallback
    resolves a bracket only when EVERY number in it is a Reference."""
    line = "The interval [0, 1] and the ratio [5, 9] are shown."
    doc = _numbered_ref_doc(line, None)
    body = _body(_tex(doc))
    assert "[0, 1]" in body, body
    assert "[5, 9]" in body, body          # 9 is no Reference
    assert "\\cite" not in body, body


# ------------------------- 5. the resolver owns citations EVERYWHERE (round 2)

def _footnote_doc(body: str, cite: tuple[str, str] | None, ref_key: str,
                  ref_number: int | None, ref_stub: bool):
    """A paragraph, a Footnote whose BODY carries `body`, one Citation over a
    span of that body, and one Reference. `_footnotetext` renders the body, and
    before round 2 it went through the number map with no idea of the claim."""
    doc = Document()
    doc.meta["bibkey"] = "D"
    mp = doc.ensure_stream("mathpix_lines")
    head = mp.append(text="1 Introduction", _page=1, _line_index=0,
                     type="section_header")
    para = mp.append(text="Body text here.", _page=1, _line_index=1, type="text")
    fnl = mp.append(text=body, _page=1, _line_index=2, type="footnote")

    sec = DocObject(type="Section", props={
        "caption": "Introduction", "level": 1, "flow_index": 0, "page": 1})
    sec.add_realization(Realization(stream="mathpix_lines",
                                    start=head, end=head, role="surface"))
    doc.add(sec)
    p = DocObject(type="Paragraph", props={
        "text": "Body text here.", "page": 1, "flow_index": 1})
    p.add_realization(Realization(stream="mathpix_lines",
                                  start=para, end=para, role="surface"))
    doc.add_child(sec, p)

    fn = DocObject(type="Footnote", props={
        "content": body, "refnum": "1", "anchor_marker": "{ }^{1}",
        "page": 1, "flow_index": 2})
    fn.add_realization(Realization(stream="mathpix_lines",
                                   start=fnl, end=fnl, role="surface"))
    doc.add(fn)

    if cite is not None:
        key, surface = cite
        off = body.index(surface)
        c = DocObject(type="Citation", props={
            "citekey": key, "page": 1, "flow_index": 3})
        c.add_realization(Realization(
            stream="mathpix_lines", start=fnl, end=fnl, role="surface",
            props={"offset": off, "length": len(surface)}))
        doc.add(c)

    props = {"citekey": ref_key, "bibkey": "D"}
    if ref_number is not None:
        props["number"] = ref_number
    if ref_stub:
        props["stub"] = True
    else:
        props.update({"author": "Realname", "year": "2001"})
    refs = doc.ensure_stream("references")
    ra = refs.append(text=ref_key)
    ref = DocObject(type="Reference", props=props)
    ref.add_realization(Realization(stream="references", start=ra, end=ra,
                                    role="bibliography"))
    doc.add(ref)
    return doc


def test_a_footnote_body_citation_is_not_rewritten_by_the_number_map():
    """FIX ROUND 2 — the same mis-wire on the path round 1 left behind.
    `_footnotetext` still ran `_pipe.resolve_citations`, and Citations DO sit on
    footnote lines (8 on penev_A, 5 on penev_B). A Citation `NoSuchKey` over
    `[5]` in a footnote body, beside an unrelated Reference numbered 5, was
    emitted as `\\footnotetext[1]{… \\cite{Realname2001} …}`."""
    doc = _footnote_doc("See earlier discussion [5]", ("NoSuchKey", "[5]"),
                        "Realname2001", 5, ref_stub=False)
    res = cite_res.resolve(doc)
    assert res.counts["cite_without_reference"] == 1, res.counts
    tex = _tex(doc)
    assert "\\footnotetext[1]{See earlier discussion [5]}" in tex, tex
    assert "Realname2001" not in _body(tex), _body(tex)


def test_a_citation_in_a_footnote_body_becomes_a_cite():
    """The other half: a footnote-body Citation WHOSE Reference exists now
    reaches the page as `\\cite`. Part of 645-a closed for the LaTeX lane, and
    counted (`cite_in_footnote`)."""
    doc = _footnote_doc("See earlier discussion (Smith 1999)",
                        ("Smith1999", "(Smith 1999)"),
                        "Smith1999", None, ref_stub=True)
    res = cite_res.resolve(doc)
    assert res.counts["cite_in_footnote"] == 1, res.counts
    tex = _tex(doc)
    assert "\\footnotetext[1]{See earlier discussion \\cite{Smith1999}}" in tex, tex


def _beamer(doc) -> str:
    from docops.projectors.beamer import BeamerProjector
    return BeamerProjector(
        OperatorConfig(op="projector", classname="BeamerProjector")).project(doc)


def test_the_beamer_abstract_follows_the_same_claim():
    """`BeamerProjector._render` renders an Abstract itself (beamer has no
    `abstract` environment) and called `_prose` directly — the third path the
    number map could act on without the claim."""
    line = "Prior work [5] shows this."
    doc = _numbered_ref_doc(line, ("NoSuchKey", "[5]"))
    par = next(o for o in doc.objects.values() if o.type == "Paragraph")
    par.type = "Abstract"
    deck = _beamer(doc)
    assert "Realname2001" not in deck.split("\\begin{thebibliography}")[0], deck
    assert "Prior work [5] shows this." in deck, deck


def test_the_beamer_abstract_still_cites_when_the_reference_exists():
    line = "Prior work [5] shows this."
    doc = _numbered_ref_doc(line, ("Realname2001", "[5]"))
    par = next(o for o in doc.objects.values() if o.type == "Paragraph")
    par.type = "Abstract"
    deck = _beamer(doc)
    assert "Prior work \\cite{Realname2001} shows this." in deck, deck


# ------------------------------------------- 640: a Picture/Diagram caption

def _diagram_doc(caption: str, cite: tuple[str, str] | None, ref_key: str,
                 ref_number: int | None):
    """A Diagram with no `latex_code`, so `_render` falls back to the
    `% figure pN: {caption}` comment — the class 640 measured on Steerable
    (`Adelson's checkerboard illusion [29]`, MathPix's own `\\caption{…}`,
    never scanned because its line type is `diagram`, not `text`/`title`)."""
    doc = Document()
    doc.meta["bibkey"] = "D"
    mp = doc.ensure_stream("mathpix_lines")
    dl = mp.append(text=caption, text_display=caption, _page=1,
                   _line_index=0, type="diagram")

    dia = DocObject(type="Diagram", props={
        "caption": caption, "page": 1, "flow_index": 0})
    dia.add_realization(Realization(stream="mathpix_lines",
                                    start=dl, end=dl, role="surface"))
    doc.add(dia)

    if cite is not None:
        key, surface = cite
        off = caption.index(surface)
        c = DocObject(type="Citation", props={
            "citekey": key, "page": 1, "flow_index": 1})
        c.add_realization(Realization(
            stream="mathpix_lines", start=dl, end=dl, role="surface",
            props={"offset": off, "length": len(surface)}))
        doc.add(c)

    ref = DocObject(type="Reference", props={
        "citekey": ref_key, "bibkey": "D",
        **({"number": ref_number} if ref_number is not None else {})})
    refs = doc.ensure_stream("references")
    ra = refs.append(text=ref_key)
    ref.add_realization(Realization(stream="references", start=ra, end=ra,
                                    role="bibliography"))
    doc.add(ref)
    return doc


def test_a_diagram_caption_citation_is_not_rewritten_by_the_number_map():
    doc = _diagram_doc("Illusion (compare also [5]).", ("NoSuchKey", "[5]"),
                       "Realname2001", 5)
    res = cite_res.resolve(doc)
    assert res.counts["cite_without_reference"] == 1, res.counts
    tex = _tex(doc)
    assert "% figure p1: Illusion (compare also [5])." in tex, tex
    assert "Realname2001" not in _body(tex), _body(tex)


def test_a_diagram_caption_citation_becomes_a_cite_in_the_comment():
    """The other half — closes 640's DIAGRAM class: a caption citation whose
    Reference exists reaches the `.tex`, even though it prints inside a `%`
    comment rather than the body (`Picture`/`Diagram` is in `CITED_TEXT_TYPES`
    for exactly this)."""
    doc = _diagram_doc("Illusion (compare also [29]).", ("Adelson2006", "[29]"),
                       "Adelson2006", 29)
    res = cite_res.resolve(doc)
    assert res.counts["cite_without_reference"] == 0, res.counts
    tex = _tex(doc)
    assert "% figure p1: Illusion (compare also \\cite{Adelson2006})." in tex, tex
    assert "[29]" not in tex, tex


def test_a_table_cell_citation_is_never_rewritten_inside_verbatim():
    """`Table` is deliberately NOT in `CITED_TEXT_TYPES`: a `Table` with no
    `latex_code` renders `raw_text` inside `\\begin{verbatim}…\\end{verbatim}`,
    where LaTeX never interprets `\\cite{…}` — substituting there would print
    the literal command text instead of a citation. The Citation object still
    exists (`bibliography.detect_numeric_citations` now scans cell lines,
    640) and the count says so honestly: `citations_outside_running_text`,
    not a silent 0."""
    doc = Document()
    doc.meta["bibkey"] = "D"
    mp = doc.ensure_stream("mathpix_lines")
    cell = mp.append(text="Forster et al. [10]", text_display="Forster et al. [10]",
                     _page=1, type="simple_cell")
    tab = DocObject(type="Table", props={
        "raw_text": "Forster et al. [10]", "page": 1, "flow_index": 0})
    tab.add_realization(Realization(stream="mathpix_lines", start=cell, end=cell,
                                    role="surface"))
    doc.add(tab)
    c = DocObject(type="Citation", props={"citekey": "Forster2008", "page": 1})
    c.add_realization(Realization(stream="mathpix_lines", start=cell, end=cell,
                                  role="surface", props={"offset": 16, "length": 4}))
    doc.add(c)
    ref = DocObject(type="Reference", props={"citekey": "Forster2008", "bibkey": "D",
                                              "number": 10})
    refs = doc.ensure_stream("references")
    ra = refs.append(text="Forster2008")
    ref.add_realization(Realization(stream="references", start=ra, end=ra,
                                    role="bibliography"))
    doc.add(ref)

    res = cite_res.resolve(doc)
    assert res.counts["citations_outside_running_text"] == 1, res.counts
    tex = _tex(doc)
    assert "\\begin{verbatim}\nForster et al. [10]\n\\end{verbatim}" in tex, tex
    assert "\\cite{Forster2008}" not in tex, tex


# --------------------------- 640: a bare-numeric source is short and risky

def _num_sub(source: str, replacement: str) -> cite_res.Sub:
    return cite_res.Sub(anchor=None, offset=0, length=len(source), source=source,
                        replacement=replacement, keys=("Stein1970",))


def test_a_bare_numeric_source_skips_a_coincidental_digit_inside_a_token():
    """Reproduced end to end on Steerable: a LOCANT citation (640) keyed `"1"`
    landed on `{{…_REF_Stein1970||CIT}}` — a token `clean` had ALREADY
    materialised for a DIFFERENT `[1]` on the same line — because plain
    `str.find` took the `1` inside `Stein1970` as its match. `[1, Ch. III]`
    became the corrupt `[{{…_REF_Stein\\cite{Stein1970}970||CIT}}, Ch. III]`."""
    text = "Here starts {{D_REF_Stein1970||CIT}} and later (see [1, Ch. III])."
    out = cite_res.apply_subs(text, [_num_sub("1", "\\cite{Stein1970}")])
    assert out == ("Here starts {{D_REF_Stein1970||CIT}} and later "
                   "(see [\\cite{Stein1970}, Ch. III]).")


def test_a_bare_numeric_source_skips_a_coincidental_bare_digit_in_prose():
    """The other reproduction: two ORIGINAL paragraphs merged into one object
    put an unrelated `-1` (a plain prose value, not a citation) before the
    real `[1, Ch. III]` — `-1` turned into the nonsensical `-\\cite{Stein1970}`
    while the intended bracket was left untouched."""
    text = "exactly two choices: -1 , i.e., the identity (see [1, Ch. III])."
    out = cite_res.apply_subs(text, [_num_sub("1", "\\cite{Stein1970}")])
    assert out == ("exactly two choices: -1 , i.e., the identity "
                   "(see [\\cite{Stein1970}, Ch. III]).")


def test_a_genuine_bracket_digit_still_resolves_normally():
    """The guard must not turn INTO a new miss: a plain `[6]` with nothing
    ambiguous before it in the text still matches on the first try. (Whether
    the flanking brackets are themselves swallowed is `citation_spans.groups`'s
    job, not `apply_subs`'s — this test calls `apply_subs` directly, as the
    two reproductions above do, so the brackets are left standing.)"""
    text = "Tensor products of Hilbert transforms [6]"
    out = cite_res.apply_subs(text, [_num_sub("6", "\\cite{Chan2004}")])
    assert out == "Tensor products of Hilbert transforms [\\cite{Chan2004}]"


# ------------------- FIX ROUND 1: position 0 is not automatically a citation

def test_a_bare_digit_at_the_very_start_of_the_text_is_not_a_citation():
    """Coordinator review, finding 2. `_numeric_source_in_context`'s
    `j == 0` branch used to accept ANY match with nothing but whitespace
    before it — including position 0 of the WHOLE text — contradicting its
    own docstring ("the bracket that opens it"). A Footnote or caption whose
    OWN text happens to start with a coincidental number ("1970 was...")
    reopened the exact corruption this guard exists to close, at position 0
    instead of mid-text. The real bracket later in the same text must still
    be found."""
    text = "1970 was the year Stein published the result (see [1, Ch. III])."
    out = cite_res.apply_subs(text, [_num_sub("1", "\\cite{Stein1970}")])
    assert out == ("1970 was the year Stein published the result "
                   "(see [\\cite{Stein1970}, Ch. III]).")


def test_bracket_inclusive_source_at_position_zero_is_accepted_by_the_helper():
    """The other half, on `_numeric_source_in_context` directly: position 0
    IS valid when the OPENING BRACKET is itself part of the recorded source
    (the `_numeric_fallback` bracket-inclusive sources, e.g. `"[12]"`) —
    there is nothing before it to check because the bracket IS what is being
    matched, not what precedes it. (`apply_subs`'s own `numeric` gate never
    reaches this branch today — `_BARE_NUMERIC_SOURCE` does not match a
    bracket-inclusive source at all — so the helper is exercised directly,
    the way the bare-digit branch above is exercised through `apply_subs`.)"""
    text = "[12] is the first citation in this footnote body."
    assert cite_res._numeric_source_in_context(text, 0, "[12]") is True
    assert cite_res._numeric_source_in_context(text, 0, "12") is False
