"""
SciKGTeXProjector (src/docops/projectors/scikgtex.py): project the docmodel to
SciKGTeX-annotated LaTeX whose compiled PDF carries ORKG contribution metadata as
XMP/RDF. The compile+XMP test is gated on lualatex + the vendored scikgtex
(tests/fixtures/scikgtex/, from the v3.0.0 release).
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from docops.base import OperatorConfig
from docops.projectors.scikgtex import SciKGTeXProjector

_FIX = Path(__file__).resolve().parent / "fixtures" / "scikgtex"


def _demo_doc():
    doc = Document()
    doc.meta.update({"bibkey": "demo", "title": "A Demo of SciKGTeX",
                     "authors": ["Ada Lovelace", "Alan Turing"], "primary_category": "cs.LG"})
    doc.add(DocObject(type="Abstract", id="ab", props={
        "text": "We address the problem of metadata extraction. We propose a method.",
        "flow_index": 1}))
    doc.add(DocObject(type="Section", id="s1", props={"caption": "Method", "flow_index": 2}))
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "Our method uses a transformer over the graph.",
        "parent_section": "s1", "flow_index": 3}))
    doc.add(DocObject(type="Section", id="s2", props={"caption": "Results", "flow_index": 4}))
    doc.add(DocObject(type="Paragraph", id="p2", props={
        "text": "We achieve an accuracy of 95.3% on the benchmark with n = 1200 samples.",
        "parent_section": "s2", "flow_index": 5}))
    doc.add(DocObject(type="Reference", id="r1", props={
        "citekey": "lovelace1843", "bibtex": "@article{x, doi={10.1000/abc123}}"}))
    return doc


def _project(doc):
    return SciKGTeXProjector(OperatorConfig(op="projector", classname="SciKGTeXProjector")).project(doc)


def test_scikgtex_emits_metadata_roles_facts_and_uri():
    tex = _project(_demo_doc())
    assert r"\usepackage[compatibility]{scikgtex}" in tex
    assert r"\metatitle*{A Demo of SciKGTeX}" in tex
    assert tex.count(r"\metaauthor*") == 2                 # both authors
    assert r"\researchfield*{Machine Learning}" in tex     # cs.LG -> field label
    assert r"\researchproblem*[1]" in tex                  # abstract -> P32
    assert r"\method*[" in tex and r"\result*[" in tex     # Method/Results sections
    assert r"\contribution*{accuracy}{95.3\%}" in tex      # numeric fact (-> ORKG P-id at compile)
    assert r"\uri{https://doi.org/10.1000/abc123}" in tex  # bib DOI entity link


def test_numeric_facts_reject_citation_numbers():
    # A survey citing "[159]" near the word "accuracy" must NOT mint accuracy=159.
    # Real metrics carry a % or a decimal; bare integers next to a metric word are
    # almost always citation/reference numbers.
    doc = Document()
    doc.meta.update({"bibkey": "survey", "title": "A Survey"})
    doc.add(DocObject(type="Paragraph", id="p", props={
        "text": ("Prior accuracy results [159] and the precision of methods [10] "
                 "are reviewed across 230 papers."),
        "flow_index": 1}))
    tex = _project(doc)
    assert r"\contribution*{accuracy}" not in tex
    assert r"\contribution*{precision}" not in tex
    assert r"\contribution*{sample size}" not in tex


def test_numeric_facts_keep_real_metrics():
    doc = Document()
    doc.meta.update({"bibkey": "exp", "title": "Experiments"})
    doc.add(DocObject(type="Paragraph", id="p", props={
        "text": "We reach an accuracy of 95.3% and an F1 of 0.88 on the test set.",
        "flow_index": 1}))
    tex = _project(doc)
    assert r"\contribution*{accuracy}{95.3\%}" in tex
    assert r"\contribution*{F1 score}{0.88}" in tex


def test_scikgtex_emits_rights_disclaimer():
    tex = _project(_demo_doc())
    # pdfdrill-namespace property commands are declared + given values
    assert r"\newpropertycommand[pdfdrill, http://pdfdrill.org/property/]{disclaimer}" in tex
    assert r"\newpropertycommand[pdfdrill, http://pdfdrill.org/property/]{liability}" in tex
    assert r"\disclaimer*{" in tex and r"\liability*{" in tex
    assert "readability" in tex
    assert "no liability" in tex.lower()
    assert "PDFDRILL" in tex and "trademark" in tex.lower()


def test_scikgtex_disclaimer_overridable():
    doc = _demo_doc()
    cfg = OperatorConfig(op="projector", classname="SciKGTeXProjector",
                         params={"liability": "Custom liability clause."})
    tex = SciKGTeXProjector(cfg).project(doc)
    assert r"\liability*{Custom liability clause.}" in tex


def _have_scikgtex():
    return (shutil.which("lualatex") and (_FIX / "scikgtex.sty").exists()
            and (_FIX / "scikgtex.lua").exists())


def test_scikgtex_compiles_and_embeds_orkg_xmp():
    if not _have_scikgtex():
        print("SKIP (lualatex or vendored scikgtex missing)"); return
    tex = _project(_demo_doc())
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "doc.tex").write_text(tex)
        for f in ("scikgtex.sty", "scikgtex.lua"):
            shutil.copy(_FIX / f, d / f)
        r = subprocess.run(["lualatex", "-interaction=nonstopmode", "-halt-on-error", "doc.tex"],
                           cwd=d, capture_output=True, text=True, timeout=180,
                           env={"TEXINPUTS": ".:", "PATH": __import__("os").environ["PATH"],
                                "HOME": str(d)})
        assert (d / "doc.pdf").exists(), f"lualatex failed:\n{r.stdout[-1500:]}"
        xmp = (d / "doc.xmp_metadata.xml").read_text()

        assert "http://orkg.org/core#Paper" in xmp                 # orkg:Paper
        assert "<orkg:hasTitle>A Demo of SciKGTeX</orkg:hasTitle>" in xmp
        assert xmp.count("<orkg:hasAuthor>") >= 1                  # >=1 author
        assert "<orkg:hasResearchField>Machine Learning" in xmp
        assert "orkg:ResearchContribution" in xmp
        assert any(p in xmp for p in ("P32", "P1005", "P1006"))    # role property IDs
        import re
        assert re.search(r"orkg_property:P\d+>95\.3%", xmp), "accuracy did not resolve to a P-id"
        assert "https://doi.org/10.1000/abc123" in xmp and "<rdfs:label>" in xmp  # DOI uri
        # the rights/disclaimer properties land in the pdfdrill XMP namespace
        assert "pdfdrill" in xmp and "readability" in xmp
        assert "liability" in xmp.lower()


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
