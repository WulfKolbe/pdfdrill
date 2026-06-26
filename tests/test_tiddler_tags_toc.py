"""
Tiddler tagging completeness + the structured fractal-index TOC (tiddlywiki
projector). Every tiddler must carry a structural tag for filter performance:
the document-header + bibliographic tiddlers get `bibtex`, TikZ diagrams get
`tikz`. The TOC tiddler is rebuilt as a structured xref index: each section's
fractal index (1 / 2.3 / 2.3.1) + page + a link to its tiddler.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from docops.base import OperatorConfig
from docops.projectors.tiddlywiki import TiddlyWikiProjector, fractal_index


def _proj(doc):
    import json
    p = TiddlyWikiProjector(OperatorConfig(op="projector", classname="TiddlyWikiProjector"))
    return {t["title"]: t for t in json.loads(p.project(doc))}


def _doc():
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Section", id="s1", props={
        "caption": "Introduction", "level": 1, "page": 1, "flow_index": 1}))
    doc.add(DocObject(type="Section", id="s2", props={
        "caption": "Sheaves", "level": 1, "page": 7, "flow_index": 2}))
    doc.add(DocObject(type="Section", id="s3", props={
        "caption": "Stalks", "level": 2, "page": 8, "flow_index": 3,
        "parent_section": "s2"}))
    doc.add(DocObject(type="Reference", id="r1", props={
        "citekey": "kipf2017", "year": "2017", "raw_text": "Kipf & Welling 2017"}))
    doc.add(DocObject(type="Diagram", id="d1", props={
        "latex_code": "\\begin{tikzpicture}\\draw(0,0)--(1,1);\\end{tikzpicture}",
        "page": 5, "flow_index": 4}))
    doc.add(DocObject(type="Diagram", id="d2", props={
        "latex_code": "", "cdn_url": "https://cdn/x.png", "page": 6, "flow_index": 5}))
    doc.add(DocObject(type="Toc", id="toc1", props={"entries": ["junk ... 5"]}))
    return doc


def test_fractal_index_from_tree():
    doc = _doc()
    fi = fractal_index(doc)
    # s1 -> "1", s2 -> "2", s3 (child of s2, level 2) -> "2.1"
    assert fi["s1"] == "1" and fi["s2"] == "2" and fi["s3"] == "2.1"


def test_fractal_index_letters_appendix_sections():
    """\\appendix → TOC connection: appendix top-level sections are lettered
    A, B, ... (real LaTeX appendix numbering); their subsections become A.1."""
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Section", id="s1", props={"caption": "Intro", "level": 1, "flow_index": 1}))
    doc.add(DocObject(type="Section", id="s2", props={"caption": "Method", "level": 1, "flow_index": 2}))
    doc.add(DocObject(type="Section", id="a1", props={"caption": "Proofs", "level": 1, "flow_index": 3, "is_appendix": True}))
    doc.add(DocObject(type="Section", id="a11", props={"caption": "Lemmas", "level": 2, "flow_index": 4, "is_appendix": True}))
    doc.add(DocObject(type="Section", id="a2", props={"caption": "More", "level": 1, "flow_index": 5, "is_appendix": True}))
    fi = fractal_index(doc)
    assert fi["s1"] == "1" and fi["s2"] == "2"
    assert fi["a1"] == "A" and fi["a11"] == "A.1" and fi["a2"] == "B"


def test_fractal_index_top_level_for_section_only_paper():
    """A paper with only \\section (level 2 in our map) numbers its top sections
    1, 2, 3 — not 1.1, 1.2 — by anchoring the index to the minimum level."""
    doc = Document(); doc.meta["bibkey"] = "P"
    for i, lvl in enumerate([2, 2, 3, 2], 1):
        doc.add(DocObject(type="Section", id=f"x{i}",
                          props={"caption": f"S{i}", "level": lvl, "flow_index": i}))
    fi = fractal_index(doc)
    assert fi["x1"] == "1" and fi["x2"] == "2" and fi["x3"] == "2.1" and fi["x4"] == "3"


def test_caption_to_wikitext_resolves_refs():
    from docops.projectors.tiddlywiki import caption_to_wikitext
    lt = {"eq:DNN": "DOC_EQ0003"}
    # unresolved theorem label → readable (label), font unwrapped, ~ → space
    assert caption_to_wikitext(r"\texttt{Scaling}: Proof of Lemma~\ref{thm:scaling}",
                               lt) == "Scaling: Proof of Lemma (thm:scaling)"
    # known equation label → a <$link> to its tiddler
    out = caption_to_wikitext(r"see \eqref{eq:DNN}", lt)
    assert '<$link to="DOC_EQ0003">eq:DNN</$link>' in out


def test_section_tiddler_caption_field_and_latex():
    doc = Document(); doc.meta["bibkey"] = "T"
    doc.add(DocObject(type="Equation", id="e1", props={
        "latex": "x", "label": "eq:DNN", "flow_index": 1}))
    doc.add(DocObject(type="Section", id="s1", props={
        "caption": r"Proof of Lemma~\ref{thm:scaling}", "level": 1, "flow_index": 2}))
    t = _proj(doc)
    h = next(v for k, v in t.items() if v.get("kind") == "section" or "_H" in k)
    assert h["text"].startswith("# {{!!caption}}")          # markdown heading transcludes caption
    assert h["type"] == "text/markdown"
    assert h["caption"] == "Proof of Lemma (thm:scaling)"   # \ref resolved/cleaned
    assert h["caption_latex"] == r"Proof of Lemma~\ref{thm:scaling}"   # raw kept


def test_bibtex_tag_on_header_and_references():
    t = _proj(_doc())
    assert "bibtex" in t["T"]["tags"].split()                # document header
    ref = t["T_REF_kipf2017"]
    assert "bibtex" in ref["tags"].split()                   # bib entry
    assert "reference" in ref["tags"].split()                # original tags kept


def test_tikz_tag_only_on_tikz_diagrams():
    t = _proj(_doc())
    dia = {k: v for k, v in t.items() if "_DIA_" in k}
    tikz = [v for v in dia.values() if "tikz" in v["tags"].split()]
    plain = [v for v in dia.values() if "tikz" not in v["tags"].split()]
    assert len(tikz) == 1 and len(plain) == 1                # d1 tikz, d2 not
    assert all("diagram" in v["tags"].split() for v in dia.values())


def test_toc_is_structured_fractal_index():
    t = _proj(_doc())
    toc = next(v for k, v in t.items() if "_TOC" in k or v["tags"].split()[0] == "toc")
    body = toc["text"]
    assert "2.1" in body and "Stalks" in body                # fractal idx + name
    assert "p. 8" in body or "p.8" in body                   # page
    assert "T_H" in body                                     # link to section tiddler
    assert "junk" not in body                                # old entry-string dropped


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = []
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except AssertionError as e:
            failed.append(t.__name__); print(f"FAIL {t.__name__}: {e}")
        except Exception as e:
            failed.append(t.__name__); print(f"ERROR {t.__name__}: {e!r}")
    if failed:
        print(f"\n{len(failed)} of {len(tests)} failed"); sys.exit(1)
    print(f"\nAll {len(tests)} tests passed.")
