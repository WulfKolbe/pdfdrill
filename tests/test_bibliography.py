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
from pdfdrill.bibliography import parse_bibliography, add_reference_objects, link_citations


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
