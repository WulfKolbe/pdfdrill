"""
LaTeX / sTeX projectors over the semantic graph (src/semantic/stex.py):
  * project_latex  — enhanced LaTeX: acronyms + glossary + Table of Symbols + index
  * project_stex   — sTeX: smodule / \\symdecl / sdefinition / \\symref
The compile test is gated on lualatex + glossaries being installed.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject
from semantic.graph import SemanticGraph
from semantic.identity import IdentityResolver
from semantic.build import ingest_docmodel
from semantic import stex


def _demo_graph():
    doc = Document(); doc.meta["bibkey"] = "demo"; doc.meta["title"] = "A Demo Paper"
    doc.add(DocObject(type="Section", id="s1", props={
        "caption": "Method", "section_number": "2", "level": 1, "flow_index": 1}))
    doc.add(DocObject(type="Section", id="s2", props={
        "caption": "Notation", "section_number": "", "level": 1, "flow_index": 2}))
    doc.add(DocObject(type="Paragraph", id="p1", props={
        "text": "We use a Convolutional Neural Network (CNN).",
        "page": 3, "parent_section": "s1", "flow_index": 3}))
    doc.add(DocObject(type="Paragraph", id="p2", props={
        "text": "The CNN is robust; the CNN scales.",
        "page": 5, "parent_section": "s1", "flow_index": 4}))
    doc.add(DocObject(type="ListItem", id="i1", props={
        "content": "psi — the wave function", "page": 2,
        "parent_section": "s2", "flow_index": 5}))
    g = SemanticGraph(); ingest_docmodel(g, IdentityResolver(g), doc, "demo")
    return g


def test_project_latex_emits_all_lists():
    tex = stex.project_latex(_demo_graph(), "demo")
    assert r"\newacronym{cnn}{CNN}{Convolutional Neural Network}" in tex   # acronym
    assert "type=symbols" in tex and r"name={psi}" in tex                 # Table of Symbols
    assert r"\printglossary[type=symbols,title={Table of Symbols}]" in tex
    assert r"\printglossary[type=\acronymtype" in tex                     # acronyms list
    assert r"\printindex" in tex and r"\index{CNN}" in tex   # indexed by its name
    assert r"\Gls{cnn}" in tex                                            # uses the concept
    assert r"\section{2 Method}" in tex                                   # structure


def test_project_stex_emits_module_decls_defs_refs():
    tex = stex.project_stex(_demo_graph(), "demo")
    assert r"\usepackage{stex}" in tex
    assert r"\begin{smodule}{demo}" in tex
    assert r"\symdecl*{cnn}" in tex
    assert r"\begin{sdefinition}[for={cnn}]" in tex and r"\definiendum{cnn}{CNN}" in tex
    assert r"\symref{cnn}{CNN}" in tex                                    # the use side


def test_synonyms_list_from_aliases():
    """S5.1: (a) an acronym's expansion is its alias (Schwartz-Hearst pair);
    (b) >1 distinct name/alias Evidence values on one CONCEPT = synonyms. Each
    alias emits ONE glossaries-native `see=` entry pointing at the main key."""
    from semantic.evidence import Evidence
    from semantic.entity import EntityType
    g = _demo_graph()
    # route (b): attach a second name to the psi symbol concept
    psi = next(e for e in g.entities.values()
               if e.type == EntityType.CONCEPT and e.properties().get("name") == "psi")
    psi.evidence.append(Evidence("demo", "alias", "wavefunction symbol", "concepts"))

    tex = stex.project_latex(g, "demo")
    # route (a): the CNN expansion becomes a see= synonym entry, exactly once
    assert tex.count("see={cnn}") == 1
    assert r"description={synonym}" in tex
    assert "Convolutional Neural Network" in tex
    # route (b): the psi alias points at the psi key, exactly once
    assert tex.count("see={psi}") == 1
    assert "wavefunction symbol" in tex
    # the synonyms print as their own list
    assert "title={Synonyms}" in tex


def test_stex_alias_becomes_symref_variant_note():
    """In the sTeX form an alias is a \\symref variant note on the SAME
    \\symdecl — one symbol, many surface forms."""
    from semantic.evidence import Evidence
    from semantic.entity import EntityType
    g = _demo_graph()
    psi = next(e for e in g.entities.values()
               if e.type == EntityType.CONCEPT and e.properties().get("name") == "psi")
    psi.evidence.append(Evidence("demo", "alias", "wavefunction symbol", "concepts"))
    tex = stex.project_stex(g, "demo")
    assert tex.count(r"\symdecl*{psi}") == 1            # ONE symbol
    assert r"\symref{psi}{wavefunction symbol}" in tex  # the variant surface form


def _have(*tools):
    return all(shutil.which(t) for t in tools)


def test_project_latex_compiles_with_lualatex():
    if not (_have("lualatex", "makeglossaries", "makeindex")
            and subprocess.run(["kpsewhich", "glossaries-extra.sty"],
                               capture_output=True).stdout.strip()):
        print("SKIP (lualatex/glossaries not installed)"); return
    tex = stex.project_latex(_demo_graph(), "demo")
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "doc.tex").write_text(tex)
        run = lambda *c: subprocess.run(c, cwd=d, capture_output=True, timeout=120)
        run("lualatex", "-interaction=nonstopmode", "-halt-on-error", "doc.tex")
        run("makeglossaries", "doc"); run("makeindex", "doc.idx")
        run("lualatex", "-interaction=nonstopmode", "doc.tex")
        run("lualatex", "-interaction=nonstopmode", "doc.tex")
        assert (Path(d) / "doc.pdf").exists(), "lualatex did not produce doc.pdf"


def test_project_stex_compiles_with_lualatex():
    if not (_have("lualatex")
            and subprocess.run(["kpsewhich", "stex.sty"], capture_output=True).stdout.strip()):
        print("SKIP (lualatex/stex not installed)"); return
    tex = stex.project_stex(_demo_graph(), "demo")
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "doc.tex").write_text(tex)
        for _ in range(2):
            subprocess.run(["lualatex", "-interaction=nonstopmode", "doc.tex"],
                           cwd=d, capture_output=True, timeout=180)
        assert (Path(d) / "doc.pdf").exists(), "lualatex did not produce the sTeX PDF"


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
