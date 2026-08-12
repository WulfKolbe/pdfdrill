"""
Unit tests for bibliography parsing (pdfdrill.bibliography) + Reference tiddler.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document
from docops.base import OperatorConfig
from docops.projectors.tiddlywiki import TiddlyWikiProjector
from docops.projectors.llm_compact import LLMCompactProjector
from docmodel.core import DocObject, Realization
from pdfdrill.bibliography import (
    parse_bibliography, add_reference_objects, link_citations,
    detect_numeric_citations, detect_author_year_citations, _expand_numlist,
)


def _doc_with_references():
    doc = Document()
    doc.meta["bibkey"] = "DOC"
    mp = doc.ensure_stream("mathpix_lines")
    mp.append(text="References", _page=10, type="section_header")
    # entry 1 spans three lines, ends on a year.
    mp.append(text="Akari Asai, Zeqiu Wu, and Hannaneh Hajishirzi. Self-rag:", _page=10, type="text")
    mp.append(text="retrieve, generate, and critique. In ICLR,", _page=10, type="text")
    mp.append(text="2023.", _page=10, type="text")
    # entry 2 ends on a page range.
    mp.append(text="Aletras, N.; and Stevenson, M. 2013. Evaluating topic", _page=10, type="text")
    mp.append(text="coherence. In IWCS, 13-22.", _page=10, type="text")
    return doc


def _doc_latex_heading_per_line_refs():
    # the 0-references failure class: a \section*{}-wrapped heading and one
    # author-year reference per line with the year MID-line (no [N] marker, no
    # year at line-end) — the old scanner found 0.
    doc = Document(); doc.meta["bibkey"] = "DOC"
    mp = doc.ensure_stream("mathpix_lines")
    mp.append(text="\\section*{7 References}", _page=9, type="text")
    mp.append(text="Smith, J. 2019. A first paper. In ACL.", _page=9, type="text")
    mp.append(text="Doe, A.; and Roe, B. 2020. A second paper. In EMNLP.", _page=9, type="text")
    mp.append(text="Lee, K. 2021. A third paper. JMLR.", _page=9, type="text")
    return doc


def test_ref_source_tagged_per_creation_path():
    """Each Reference records WHERE its BibTeX came from, for `status`."""
    from pdfdrill.bibliography import ingest_bbl, load_bibtex_file, add_reference_objects
    # .bbl
    d1 = Document()
    ingest_bbl(d1, r"\begin{thebibliography}{1}\bibitem{a} A. 2020.\end{thebibliography}")
    assert all(r.props.get("ref_source") == "bbl"
               for r in d1.objects.values() if r.type == "Reference")
    # inline \bibitem
    d2 = Document()
    ingest_bbl(d2, r"\bibitem{b} B. 2021.", source="bibitem")
    assert [r.props["ref_source"] for r in d2.objects.values()
            if r.type == "Reference"] == ["bibitem"]
    # .bib
    d3 = Document()
    load_bibtex_file(d3, "@article{c, title={C}, year={2022}, author={Z}}")
    assert all(r.props.get("ref_source") == "bib"
               for r in d3.objects.values() if r.type == "Reference")
    # heuristic from printed text
    d4 = Document()
    add_reference_objects(d4, [{"citekey": "d2019", "raw_text": "D 2019",
                                "year": "2019", "author": "D", "number": 1}])
    assert [r.props["ref_source"] for r in d4.objects.values()
            if r.type == "Reference"] == ["text"]


def test_format_bibliography_state_lines():
    from pdfdrill.commands import _format_bibliography_state
    props = ([{"ref_source": "bbl", "year": "2020", "bibtex": "@x{}"}] * 3
             + [{"ref_source": "text", "year": "2019"}] * 2
             + [{"ref_source": "bib", "year": "2021", "bibtex": "@y{}",
                 "bibfetched": True}])
    lines = _format_bibliography_state(props, cites=4)
    head = lines[0]
    assert "6 entries" in head
    assert "3 from .bbl (compiled)" in head and "2 from text" in head
    assert "1 from .bib" in head
    assert "4 with full BibTeX" in lines[1] and "4 in-text citations linked" in lines[1]
    assert any("bibfetch" in l and "1" in l for l in lines)      # the warning line
    assert _format_bibliography_state([]) == []                  # empty → no lines


def _doc_numbered_section_heading_refs():
    # the real VLDB/IEEE failure (p1713-suchanek "5. REFERENCES",
    # p1521-yahya "7. REFERENCES"): an all-caps heading carrying its section
    # number — the old strict ^references$ rejected the "5. " prefix → 0 refs.
    # Entries are numbered ("N. ...") and span two OCR lines each.
    doc = Document(); doc.meta["bibkey"] = "DOC"
    mp = doc.ensure_stream("mathpix_lines")
    mp.append(text="5. REFERENCES", _page=12, type="text")
    mp.append(text="1. Gad-Elrab, M.H., Stepanova, D.: Excut: Explainable", _page=12, type="text")
    mp.append(text="clustering over knowledge graphs. In: ISWC (2020)", _page=12, type="text")
    mp.append(text="2. Henson, C., Schmid, S.: Using a knowledge graph of", _page=12, type="text")
    mp.append(text="scenes to enable search. In: ISWC (2019)", _page=12, type="text")
    return doc


def test_parse_numbered_section_reference_heading():
    entries = parse_bibliography(_doc_numbered_section_heading_refs())
    assert len(entries) == 2                           # was 0 (heading "5. REFERENCES")
    assert entries[0]["number"] == 1 and entries[1]["number"] == 2
    assert entries[0]["year"] == "2020" and entries[1]["year"] == "2019"
    assert entries[0]["citekey"].startswith("GadElrab")


def test_parse_latex_wrapped_heading_and_per_line_authoryear_entries():
    entries = parse_bibliography(_doc_latex_heading_per_line_refs())
    assert len(entries) == 3                          # was 0 (heading) / 1 (no split)
    assert {e["year"] for e in entries} == {"2019", "2020", "2021"}
    assert entries[0]["citekey"].startswith("Smith")


def test_parse_segments_entries_and_extracts_year_citekey():
    doc = _doc_with_references()
    entries = parse_bibliography(doc)
    assert len(entries) == 2
    assert entries[0]["year"] == "2023"
    assert entries[0]["citekey"] == "Asai2023"        # surname of first author + year
    assert entries[1]["year"] == "2013"
    assert entries[1]["citekey"] == "Aletras2013"     # "Last, F." form
    assert "Self-rag" in entries[0]["raw_text"]


def test_reference_tiddler_has_cit_prefix_and_fields():
    doc = _doc_with_references()
    add_reference_objects(doc, parse_bibliography(doc))
    proj = TiddlyWikiProjector(OperatorConfig(op="projector", classname="TiddlyWikiProjector"))
    tids = json.loads(proj.project(doc))
    refs = [t for t in tids if "reference" in t.get("tags", "")]
    assert len(refs) == 2
    r = refs[0]
    assert r["text"].startswith("{{||CIT}} ")          # self-reference in front
    assert r["kind"] == "reference"
    assert r["citekey"] and r["year"]
    assert "Self-rag" in r["text"]


def test_link_citations_to_references_by_surname_prefix():
    doc = Document()
    doc.meta["bibkey"] = "DOC"
    mp = doc.ensure_stream("mathpix_lines")
    # in-text citation [Aletras] and a reference Aletras2013
    ca = mp.append(text="as in [Aletras] we note", _page=1, type="text")
    cit = DocObject(type="Citation", props={"citekey": "Aletras"})
    cit.add_realization(Realization(stream="mathpix_lines", start=ca, end=ca, role="surface"))
    doc.add(cit)
    ra = mp.append(text="Aletras, N. 2013. Topic coherence.", _page=10, type="text")
    ref = DocObject(type="Reference", props={"citekey": "Aletras2013"})
    ref.add_realization(Realization(stream="mathpix_lines", start=ra, end=ra, role="surface"))
    doc.add(ref)

    n = link_citations(doc)
    assert n == 1
    assert any(a.kind == "cites" for a in doc.alignments)


def test_markdown_in_text_eq_refs_opt_in():
    doc = Document()
    doc.meta["bibkey"] = "DOC"
    para = DocObject(type="Paragraph", props={"text": "By (1) we conclude.", "flow_index": 0})
    doc.add(para)
    eq = DocObject(type="Equation", props={
        "latex": "x=1", "equation_number": "(1)", "flow_index": 1, "cdn_url": "u"})
    doc.add(eq)

    off = LLMCompactProjector(OperatorConfig(op="projector", classname="LLMCompactProjector"))
    assert "(1)" in off.project(doc)              # default: untouched

    on = LLMCompactProjector(OperatorConfig(op="projector", classname="LLMCompactProjector",
                                            params={"eq_refs": True}))
    md = on.project(doc)
    assert "By [E1] we conclude." in md           # (1) -> equation placeholder


def test_expand_numlist_handles_ranges_and_lists():
    assert _expand_numlist("1,3-5") == [1, 3, 4, 5]
    assert _expand_numlist("2") == [2]
    assert _expand_numlist("7-9; 11") == [7, 8, 9, 11]


def test_numeric_citation_detection_and_linking():
    doc = Document()
    doc.meta["bibkey"] = "DOC"
    mp = doc.ensure_stream("mathpix_lines")
    mp.append(text="prior work [1, 3-4] and an interval [0,9] here", _page=1, type="text")
    # 4 numbered references
    refs = []
    for i in range(1, 5):
        ra = mp.append(text=f"Ref {i} author. 20{10 + i}.", _page=10, type="text")
        from docmodel.core import DocObject, Realization
        r = DocObject(type="Reference", props={"citekey": f"k{i}", "number": i})
        r.add_realization(Realization(stream="mathpix_lines", start=ra, end=ra, role="surface"))
        doc.add(r)
        refs.append(r)

    n = detect_numeric_citations(doc, max_num=4, exclude_anchors={r.realizations[0].start for r in refs})
    # [1,3-4] -> 1,3,4 ; [0,9] filtered (0 and 9 out of 1..4)
    assert n == 3
    cites = [c for c in doc.objects.values() if c.type == "Citation"]
    assert sorted(c.props["number"] for c in cites) == [1, 3, 4]

    edges = link_citations(doc)
    assert edges == 3
    assert all(a.props.get("number") in (1, 3, 4) for a in doc.alignments if a.kind == "cites")


def test_author_year_citation_detection_and_linking():
    from docmodel.core import DocObject, Realization
    doc = Document()
    doc.meta["bibkey"] = "DOC"
    mp = doc.ensure_stream("mathpix_lines")
    mp.append(
        text="Building on (Asai et al., 2023; Wu and Lee, 2024) and see (the year 2020).",
        _page=1, type="text")
    for ck in ("Asai2023", "Wu2024"):
        ra = mp.append(text=f"{ck} entry.", _page=10, type="text")
        r = DocObject(type="Reference", props={"citekey": ck, "number": None})
        r.add_realization(Realization(stream="mathpix_lines", start=ra, end=ra, role="surface"))
        doc.add(r)

    refanch = {r.realizations[0].start for r in doc.objects.values() if r.type == "Reference"}
    n = detect_author_year_citations(doc, exclude_anchors=refanch)
    keys = sorted(c.props["citekey"] for c in doc.objects.values() if c.type == "Citation")
    assert keys == ["Asai2023", "Wu2024"]          # "(the year 2020)" -> "the" is a stopword
    assert n == 2
    assert link_citations(doc) == 2                 # both match references by citekey


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__)
            print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__)
            print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} failed out of {len(tests)}")
        sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")


# --------------------------------------------------- numbered "[N]." entries
def test_a_bracketed_marker_followed_by_a_period_starts_an_entry():
    """`[5]. Author, "Title"` is a common publisher style. _REF_START demanded
    whitespace immediately after `[N]`, so the period defeated it and every
    such entry was glued onto its predecessor — on a real 10-reference paper
    (10.53759/aist/978-9914-9946-1-2_12) entries 5-10 collapsed into one.
    """
    from pdfdrill.bibliography import _REF_START
    for line in ('[5]. R. Manmatha and J. Rothfeder, "A scale space approach"',
                 '[10]. J. Pradeep, "Diagonal based feature extraction"',
                 '[5] R. Manmatha, "A scale space approach"',       # no period
                 '[5]) R. Manmatha, "A scale space approach"',
                 '5. R. Manmatha, "A scale space approach"',
                 '5) R. Manmatha, "A scale space approach"'):
        assert _REF_START.match(line), line


def test_a_bracketed_number_that_is_not_a_marker_does_not_start_an_entry():
    """An in-text citation or a bare number must not be read as a new entry."""
    from pdfdrill.bibliography import _REF_START
    for line in ("as shown in [5] the method converges",
                 "[5]",                       # a marker with no entry after it
                 "[2005]. something",         # a year, not a reference number
                 "68"):
        assert not _REF_START.match(line), line


def _stream_doc(lines):
    """A Document with just the mathpix_lines stream these parsers read."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
    from docmodel.core import Document
    doc = Document(meta={})
    st = doc.ensure_stream("mathpix_lines")
    for typ, text in lines:
        st.append(type=typ, text=text)
    return doc


def test_every_numbered_entry_is_parsed_not_just_the_ones_ending_in_a_year():
    from pdfdrill.bibliography import parse_bibliography

    doc = _stream_doc([
        ("section_header", "References"),
        ("text", '[1]. Durai and Saro, "Image pressure", vol. 17, pp: 60-64, 2006.'),
        ("text", '[2]. Manmatha and Rothfeder, "A scale space approach for'),
        ("text", 'naturally sectioning words from documents."'),
        ("text", '[3]. Fuller, Farsaie and Dumoulin, "Handwritten Character'),
        ("text", 'Recognition," doi: 10.21236/ada238294.'),
        ("text", '[4]. Breuel, "Handwritten character recognition using neural nets"'),
    ])
    got = parse_bibliography(doc)
    assert [e["number"] for e in got] == [1, 2, 3, 4]
    assert "scale space" in got[1]["raw_text"]
    assert "ada238294" in got[2]["raw_text"]     # the continuation line stayed


def test_a_page_number_line_is_not_a_reference():
    """MathPix emits the printed page number as its own `page_info` line. It
    was landing in the bibliography as an entry whose whole text was "68"."""
    from pdfdrill.bibliography import parse_bibliography

    doc = _stream_doc([
        ("section_header", "References"),
        ("text", '[1]. Durai and Saro, "Image pressure", pp: 60-64, 2006.'),
        ("page_info", "68"),
    ])
    got = parse_bibliography(doc)
    assert [e["number"] for e in got] == [1]


def test_a_running_page_header_is_not_the_bibliography_heading():
    """A book prints the section title on every page of the section, and
    MathPix emits that as a `page_info` line. The heading scan kept the LAST
    match, so the running header on the SECOND page of the list always won and
    everything before it was discarded.

    Measured on a real 174-page scanned book (WDorg4, Literaturverzeichnis
    pp169-170): 21 entries printed, ONE parsed — the heading matched at the
    section_header on p169 AND at the running header on p170, and the second
    one took the start marker past entries [1]-[20]. A running header is later
    than the real heading BY CONSTRUCTION, so this is not bad luck.
    """
    from pdfdrill.bibliography import parse_bibliography

    doc = _stream_doc([
        ("section_header", "LITERATURVERZEICHNIS"),
        ("text", "[1] B. HEIM: Elementarstrukturen der Materie. Innsbruck: Resch, 1989"),
        ("text", "[2] D. KLAUA: Allgemeine Mengenlehre. Berlin: Akademie-Verlag, 1964"),
        ("page_info", "160"),
        ("page_info", "Literaturverzeichnis"),          # the running header
        ("text", "[3] A. D. KRISCH: Die Rolle des Spins. Spektrum; (1987) 10, 116-129"),
    ])
    got = parse_bibliography(doc)
    assert [e["number"] for e in got] == [1, 2, 3]


def test_a_table_of_contents_row_is_not_the_bibliography_heading():
    """The TOC names every section, so it matches too. It comes EARLIER than
    the real heading, so last-wins hid this one — until a document whose real
    heading is untyped puts the TOC row last."""
    from pdfdrill.bibliography import parse_bibliography

    doc = _stream_doc([
        ("table_of_contents_item", "Literaturverzeichnis"),
        ("text", "some body prose that is not a reference at all"),
        ("section_header", "LITERATURVERZEICHNIS"),
        ("text", "[1] B. HEIM: Elementarstrukturen der Materie. Innsbruck: Resch, 1989"),
    ])
    got = parse_bibliography(doc)
    assert [e["number"] for e in got] == [1]
    assert "some body prose" not in got[0]["raw_text"]


def test_an_untyped_heading_still_starts_the_bibliography():
    """Not every source types its headings — the fallback must survive."""
    from pdfdrill.bibliography import parse_bibliography

    doc = _stream_doc([
        ("text", "References"),
        ("text", "[1] B. HEIM: Elementarstrukturen der Materie. Innsbruck: Resch, 1989"),
    ])
    assert [e["number"] for e in parse_bibliography(doc)] == [1]


def test_a_running_header_loses_even_when_no_heading_is_typed():
    """The section_header preference alone is not enough: a source that types
    nothing (plain text lines, or tesseract output) still has running headers,
    and there the fallback is what picks the start. Skipping page_info and TOC
    rows has to hold on its own — without this the mutant that re-admits them
    passes every other test in this file."""
    from pdfdrill.bibliography import parse_bibliography

    doc = _stream_doc([
        ("text", "References"),                        # the real heading, untyped
        ("text", "[1] B. HEIM: Elementarstrukturen der Materie. Resch, 1989"),
        ("page_info", "160"),
        ("page_info", "References"),                   # running header, page 2
        ("text", "[2] D. KLAUA: Allgemeine Mengenlehre. Akademie-Verlag, 1964"),
    ])
    assert [e["number"] for e in parse_bibliography(doc)] == [1, 2]


def test_a_back_matter_toc_row_loses_to_the_real_heading():
    """Many German books print the Inhaltsverzeichnis at the BACK, so a TOC row
    naming the bibliography can come AFTER it — and then last-wins would start
    the list past its own end. The TOC row must also stay out of the entry body,
    or it becomes a reference in its own right."""
    from pdfdrill.bibliography import parse_bibliography

    doc = _stream_doc([
        ("text", "Literaturverzeichnis"),              # the real heading, untyped
        ("text", "[1] B. HEIM: Elementarstrukturen der Materie. Resch, 1989"),
        ("table_of_contents_container", ""),
        ("table_of_contents_item", "Literaturverzeichnis"),     # back-matter TOC
        ("table_of_contents_number", "169"),
    ])
    assert [e["number"] for e in parse_bibliography(doc)] == [1]
