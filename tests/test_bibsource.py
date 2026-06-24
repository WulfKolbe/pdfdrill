"""
Tests for the gold-bibliography ingest (pdfdrill.bibliography .bbl/.bib path).

Covers the .bbl parser, OCR-tolerant alpha-label normalization, Reference
creation with addressable `references`-stream anchors, structured-field
enrichment from a .bib, and label-based citation linking (incl. an OCR-garbled
label like `ASVo2` -> `ASV02`).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization
from pdfdrill import bibliography as B


_BBL = r"""\begin{thebibliography}{XYZ99}
\bibitem[ASV02]{kitaev2002classical}
A.~Y. Kitaev, A.~Shen, and M.~N. Vyalyi.
\newblock {\em Classical and Quantum Computation}.
\newblock AMS, 2002.

\bibitem[Awo10]{awodey2010category}
Steve Awodey.
\newblock {\em Category Theory}.
\newblock Oxford University Press, 2010.
\end{thebibliography}
"""

_BIB = r"""
@book{kitaev2002classical,
  title={Classical and Quantum Computation},
  author={Kitaev, A. Y. and Shen, A. and Vyalyi, M. N.},
  year={2002}, publisher={AMS}
}
@book{awodey2010category,
  title={Category Theory}, author={Awodey, Steve}, year={2010}
}
"""


def test_norm_label_ocr_tolerant():
    assert B._norm_label("ASVo2") == B._norm_label("ASV02")   # o->0
    assert B._norm_label("NCoo") == B._norm_label("NC00")
    assert B._norm_label("[Awo10]") == B._norm_label("Awo10")  # strips brackets


def test_parse_bbl():
    items = B.parse_bbl(_BBL)
    assert [i["label"] for i in items] == ["ASV02", "Awo10"]
    assert [i["citekey"] for i in items] == ["kitaev2002classical", "awodey2010category"]
    assert "Classical and Quantum Computation" in items[0]["text"]
    assert "newblock" not in items[0]["text"] and "{" not in items[0]["text"]
    assert items[1]["number"] == 2


def test_ingest_bbl_and_enrich_and_link():
    doc = Document()
    # An in-text citation whose OCR'd label is the garbled "ASVo2".
    mp = doc.ensure_stream("mathpix_lines")
    a = mp.append(type="text", _page=3)
    cit = DocObject(type="Citation", props={"citekey": "ASVo2", "page": 3})
    cit.add_realization(Realization(stream="mathpix_lines", start=a, end=a, role="surface"))
    doc.add(cit)

    created = B.ingest_bbl(doc, _BBL)
    assert created == 2
    refs = doc.objects_of_type("Reference")
    assert {r.props["label"] for r in refs} == {"ASV02", "Awo10"}
    # References are addressable (references stream) for the cites alignment.
    assert all(any(z.stream == "references" for z in r.realizations) for r in refs)

    enriched = B.load_bibtex_file(doc, _BIB)["attached"]
    assert enriched == 2
    asv = next(r for r in refs if r.props["label"] == "ASV02")
    assert asv.props["entry_type"] == "book"
    assert "Kitaev" in asv.props.get("author", "")
    assert asv.props.get("year") == "2002"

    # The garbled "ASVo2" citation links to the ASV02 reference.
    linked = B.link_citations_by_label(doc)
    assert linked == 1
    assert cit.props.get("cited_reference_id") == asv.id
    assert any(al.kind == "cites" for al in doc.alignments)


def test_cmd_bibsource_end_to_end(tmp_path=None):
    import json, tempfile
    from pdfdrill.sidecar import Sidecar
    from pdfdrill.commands import cmd_bibsource, MODEL_BUILT, BIBSOURCE_BUILT
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        pdf = d / "doc.pdf"; pdf.write_bytes(b"%PDF-1.4\n")
        (d / "doc.bbl").write_text(_BBL); (d / "doc.bib").write_text(_BIB)
        doc = Document()
        mp = doc.ensure_stream("mathpix_lines")
        a = mp.append(type="text", _page=1)
        cit = DocObject(type="Citation", props={"citekey": "Awo10", "page": 1})
        cit.add_realization(Realization(stream="mathpix_lines", start=a, end=a, role="surface"))
        doc.add(cit)
        sc = Sidecar(pdf); sc.blob_dir.mkdir(parents=True, exist_ok=True)
        (sc.blob_dir / "model.docmodel.json").write_text(json.dumps(doc.to_dict()))
        sc.add_fact(MODEL_BUILT); sc.save()

        out = cmd_bibsource(pdf)   # finds doc.bbl/doc.bib next to the PDF
        assert "2 Reference" in out and "1/1 in-text citations linked" in out
        assert Sidecar(pdf).has(BIBSOURCE_BUILT)


def test_detect_author_year_in_objects_square_brackets_and_folding():
    """MathPix renders natbib author-year as [Surname, year] (square brackets) in
    paragraph text of a markdown/source model (no mathpix_lines stream). The
    object-text detector finds both [..] and (..), folds diacritics into the
    citekey, and link_citations connects to the gold references."""
    doc = Document()
    s = doc.ensure_stream("markdown_source")
    a1 = s.append(type="text", text="x")
    p = DocObject(type="Paragraph", props={
        "text": "a conceptual space [Gärdenfors, 2000] and multilayer "
                "networks [Kivelä et al., 2014]; see also (Carlsson, 2009)."})
    p.add_realization(Realization(stream="markdown_source", start=a1, end=a1, role="surface"))
    doc.add(p)
    # gold references (bibtex keys, as bibsource ingests them)
    for ck in ("gardenfors2000", "kivela2014", "carlsson2009topology"):
        r = DocObject(type="Reference", props={"citekey": ck})
        ra = s.append(type="ref")
        r.add_realization(Realization(stream="markdown_source", start=ra, end=ra, role="surface"))
        doc.add(r)

    n = B.detect_author_year_in_objects(doc)
    assert n == 3                                   # 3 in-text citations detected
    keys = sorted(c.props["citekey"] for c in doc.objects.values() if c.type == "Citation")
    assert keys == ["carlsson2009", "gardenfors2000", "kivela2014"]  # diacritics folded
    linked = B.link_citations(doc)                  # stream-agnostic surface()
    assert linked == 3                              # all linked to the gold refs


def test_extract_citations_all_variants():
    from pdfdrill import latex_source as LS
    tex = (r"Intro \cite{alpha}. See \citep{beta, gamma} and "
           r"\citet[p.~5]{delta}. \textcite{eps}. \nocite{*}")
    assert LS.extract_citations(tex) == ["alpha", "beta", "gamma", "delta", "eps"]


def test_load_bibtex_file_restrict_to_cited():
    """A shared .bib has more entries than the paper cites — restrict builds only
    the paper's bibliography, and created refs get a `references` surface."""
    from docmodel.core import Document
    from pdfdrill import bibliography as B
    doc = Document()
    bib = ("@article{a, title={A}, year={2020}}\n"
           "@book{b, title={B}, year={2019}}\n"
           "@misc{c, title={C}}\n")
    B.load_bibtex_file(doc, bib, restrict={"a", "c"})
    refs = {r.props["citekey"] for r in doc.objects.values() if r.type == "Reference"}
    assert refs == {"a", "c"}                       # b not cited → excluded
    r = next(o for o in doc.objects.values() if o.type == "Reference")
    assert any(x.stream == "references" for x in r.realizations)   # linkable surface


def test_build_source_model_extracts_citations():
    from pdfdrill import latex_source as LS
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        tex = Path(d) / "main.tex"
        tex.write_text(
            "\\documentclass{article}\n\\begin{document}\n"
            "Hello \\cite{alpha}. See \\citep{beta,gamma}.\n"
            "\\bibliography{biblio}\n\\end{document}\n", encoding="utf-8")
        doc = LS.build_source_model(str(tex), bibkey="x")
        cks = sorted(c.props["citekey"] for c in doc.objects.values()
                     if c.type == "Citation")
        assert cks == ["alpha", "beta", "gamma"]
        c = next(o for o in doc.objects.values() if o.type == "Citation")
        assert any(x.start is not None for x in c.realizations)    # linkable surface


def _mkdir_with(tmp, files: dict):
    import tempfile
    d = Path(tempfile.mkdtemp(dir=tmp))
    for name, content in files.items():
        (d / name).write_text(content, encoding="utf-8")
    return d


def test_find_bib_resources_from_bibliography_cmd():
    """\\bibliography{biblio} → biblio.bib, resolved in the source dir."""
    from pdfdrill import latex_source as LS
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        d = _mkdir_with(tmp, {
            "main.tex": "\\documentclass{article}\n"
                        "\\bibliographystyle{colm2024_conference}\n"
                        "\\bibliography{biblio}  % the database\n",
            "biblio.bib": "@article{a2024, title={X}, year={2024}}\n",
        })
        res = LS.find_bib_resources(str(d))
        assert [Path(p).name for p in res["bib"]] == ["biblio.bib"]
        assert res["bbl"] == []


def test_find_bib_resources_addbibresource_and_bbl():
    """biblatex \\addbibresource{refs.bib} + a compiled .bbl are both found."""
    from pdfdrill import latex_source as LS
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        d = _mkdir_with(tmp, {
            "paper.tex": "\\addbibresource{refs.bib}\n",
            "refs.bib": "@book{b, year={2020}}\n",
            "paper.bbl": "\\begin{thebibliography}{1}\\end{thebibliography}\n",
        })
        res = LS.find_bib_resources(str(d))
        assert [Path(p).name for p in res["bib"]] == ["refs.bib"]
        assert [Path(p).name for p in res["bbl"]] == ["paper.bbl"]


def test_find_bib_resources_fallback_any_bib():
    """No \\bibliography command → fall back to any .bib in the dir."""
    from pdfdrill import latex_source as LS
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        d = _mkdir_with(tmp, {"x.tex": "\\documentclass{article}\n",
                              "whatever.bib": "@misc{m}\n"})
        res = LS.find_bib_resources(str(d))
        assert [Path(p).name for p in res["bib"]] == ["whatever.bib"]


if __name__ == "__main__":
    import tempfile
    for fn in [test_norm_label_ocr_tolerant, test_parse_bbl,
               test_ingest_bbl_and_enrich_and_link, test_cmd_bibsource_end_to_end,
               test_detect_author_year_in_objects_square_brackets_and_folding,
               test_find_bib_resources_from_bibliography_cmd,
               test_find_bib_resources_addbibresource_and_bbl,
               test_find_bib_resources_fallback_any_bib,
               test_extract_citations_all_variants,
               test_load_bibtex_file_restrict_to_cited,
               test_build_source_model_extracts_citations]:
        fn(); print(f"PASS {fn.__name__}")
    print("\nAll tests passed.")
