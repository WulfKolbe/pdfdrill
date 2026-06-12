"""
Markdown ingestion (src/pdfdrill/markdown_source.py): the yt2tw route — a
Perplexity summary in Markdown (headings, \\(...\\)/\\[...\\] math, \\cite{}
in prose, numbered References, fenced ```bibtex appendix) becomes a docmodel
Document, the BibTeX appendix becoming gold-enriched Reference objects with
cites edges. Source-only (no PDF, no MathPix) — the latexbook pattern.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pdfdrill import markdown_source as ms

_MD = r"""# Lecture 3: Sheaf Neural Networks — Cristian Bodnar

## Abstract

This lecture introduces **sheaf neural networks** for graphs \cite{bodnar2022sheafnn}.

## Table of Contents

1. [Introduction](#introduction)
2. [References](#references)

## Introduction

Graphs are topological spaces. Standard diffusion \cite{kipf2017semi,bodnar2022sheafnn}
fails under heterophily. The map is written \(\rho_{UV}: F(U) \to F(V)\).

\[
\Delta_F = \delta^\top \delta,
\]

### Stalks

- vertex stalks are *private opinions*
- edge stalks are *public discourse*

## References

1. Bodnar, C., et al. (2022). *Sheaf Neural Networks on Graphs*. arXiv preprint.
2. Kipf, T. N., & Welling, M. (2017). *Semi-Supervised Classification with GCNs*. ICLR.

## BibTeX Entries

```bibtex
@article{bodnar2022sheafnn,
  author = {Bodnar, Cristian and others},
  title = {Sheaf Neural Networks on Graphs},
  year = {2022},
  % Inferred: exact identifiers were not provided in the transcript.
}

@inproceedings{kipf2017semi,
  author = {Kipf, Thomas N. and Welling, Max},
  title = {Semi-Supervised Classification with Graph Convolutional Networks},
  booktitle = {ICLR},
  year = {2017},
}
```
"""


def _doc():
    return ms.build_markdown_model(_MD, bibkey="sheaflecture")


def test_title_and_meta():
    doc = _doc()
    assert doc.meta["title"].startswith("Lecture 3: Sheaf Neural Networks")
    assert doc.meta["bibkey"] == "sheaflecture"
    assert doc.meta["source_format"] == "markdown"


def test_sections_and_abstract():
    doc = _doc()
    secs = {o.props.get("caption"): o for o in doc.objects_of_type("Section")}
    assert "Introduction" in secs and "Stalks" in secs
    assert secs["Stalks"].props.get("level", 0) > secs["Introduction"].props.get("level", 0)
    # Abstract becomes an Abstract object, NOT a Section
    abst = doc.objects_of_type("Abstract")
    assert len(abst) == 1 and "sheaf neural networks" in abst[0].props["text"]
    # TOC and BibTeX-appendix headings do not become content Sections
    assert "Table of Contents" not in secs and "BibTeX Entries" not in secs


def test_paragraphs_under_sections():
    doc = _doc()
    paras = doc.objects_of_type("Paragraph")
    intro = [p for p in paras if "topological spaces" in p.props.get("text", "")]
    assert intro and intro[0].props.get("parent_section")


def test_display_math_becomes_equation():
    doc = _doc()
    eqs = doc.objects_of_type("Equation")
    assert any("\\delta^\\top \\delta" in (e.props.get("latex") or "") for e in eqs)


def test_list_items():
    doc = _doc()
    items = doc.objects_of_type("ListItem")
    assert any("private opinions" in (i.props.get("content") or i.props.get("text") or "")
               for i in items)


def test_bibtex_appendix_becomes_gold_references():
    doc = _doc()
    refs = {r.props.get("citekey"): r for r in doc.objects_of_type("Reference")}
    assert set(refs) == {"bodnar2022sheafnn", "kipf2017semi"}
    kipf = refs["kipf2017semi"]
    assert kipf.props.get("year") == "2017"
    assert kipf.props.get("entry_type") == "inproceedings"
    assert "@inproceedings{kipf2017semi" in kipf.props.get("bibtex", "")
    assert "Welling" in kipf.props.get("author", "")


def test_cites_link_citations_to_references():
    doc = _doc()
    cits = doc.objects_of_type("Citation")
    # \cite{kipf2017semi,bodnar2022sheafnn} -> one Citation per key
    keys = sorted(c.props.get("citekey") for c in cits)
    assert keys.count("bodnar2022sheafnn") == 2 and keys.count("kipf2017semi") == 1
    refs = {r.id for r in doc.objects_of_type("Reference")}
    linked = [a for a in doc.alignments if a.kind == "cites"]
    assert len(linked) == 3
    assert all(a.props.get("reference_id") in refs for a in linked)
    assert all(a.props.get("citation_id") for a in linked)


def test_truncated_bibtex_appendix_is_salvaged():
    """Real Perplexity output gets cut off mid-entry: the fence never closes
    and the last entry's braces never balance. The closed entries AND the
    truncated one must survive (its parsed fields too)."""
    md = ("# T\n\n## Body\n\nUses \\cite{ok2020} and \\cite{cut1985}.\n\n"
          "## BibTeX Entries\n\n```bibtex\n"
          "@article{ok2020,\n  author = {Ok, A.},\n  title = {Fine},\n  year = {2020},\n}\n\n"
          "@phdthesis{cut1985,\n  author = {Cut, B.},\n  title = {Truncated Work},\n"
          "  year = {1985},\n  % Inferred: details were not")   # EOF mid-entry
    doc = ms.build_markdown_model(md, bibkey="t")
    refs = {r.props.get("citekey"): r for r in doc.objects_of_type("Reference")}
    assert set(refs) == {"ok2020", "cut1985"}
    assert refs["cut1985"].props.get("year") == "1985"
    assert refs["cut1985"].props.get("title") == "Truncated Work"
    assert len([a for a in doc.alignments if a.kind == "cites"]) == 2


def test_no_bibtex_falls_back_to_numbered_references():
    md = "# T\n\n## Body\n\nText.\n\n## References\n\n1. Foo, A. (2020). *Bar*. X.\n"
    doc = ms.build_markdown_model(md, bibkey="t")
    refs = doc.objects_of_type("Reference")
    assert len(refs) == 1 and refs[0].props.get("year") == "2020"


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
