"""
LaTeX / sTeX projectors over the semantic graph.

The graph's named-concept layer already computed the hard part every author does
by hand: one entity per concept (identity) + the definition-vs-reference split
(occurrence layer). This module *renders* that as enriched LaTeX:

  * `project_latex(graph, …)` — a standard, compilable LaTeX document with all the
    "LaTeX lists": ACRONYMS (`\\newacronym`), a GLOSSARY (`\\newglossaryentry`), a
    TABLE OF SYMBOLS (the `symbols` glossary), and an INDEX (`\\index`/`\\printindex`)
    — driven entirely by the extracted concepts. Compiles with lualatex +
    makeglossaries + makeindex.
  * `project_stex(graph, …)` — the sTeX form: a `\\symdecl` per concept inside an
    `smodule`, an `sdefinition` at each definition site, `\\symref` at each
    reference site. The graph IS the OMDoc theory; this is the LaTeX interface
    into the sTeX/MMT ecosystem.

Both carry pdfdrill's unique add-on: a provenance back-link (PDF page) per concept
— metadata sTeX/glossaries don't produce themselves.
"""
from __future__ import annotations

import re

from .entity import EntityType
from .relation import RelationType
from .layers import ordering, occurrence

_KINDS = ("acronym", "term", "symbol")


def _esc(s: str) -> str:
    """Escape LaTeX specials in plain prose (names/descriptions)."""
    return (str(s).replace("\\", r"\textbackslash{}").replace("&", r"\&")
            .replace("%", r"\%").replace("$", r"\$").replace("#", r"\#")
            .replace("_", r"\_").replace("{", r"\{").replace("}", r"\}")
            .replace("~", r"\textasciitilde{}").replace("^", r"\textasciicircum{}"))


def _key(name: str) -> str:
    k = re.sub(r"[^A-Za-z0-9]", "", name).lower()
    return k or "sym" + str(abs(hash(name)) % 10000)


def _concepts(graph) -> list[dict]:
    out = []
    for e in graph.entities.values():
        if e.type != EntityType.CONCEPT or e.subtype not in _KINDS:
            continue
        p = e.properties()
        occ = occurrence.occurrences(graph, e.id)
        pages = sorted({(r.grounding.get("pdf") or {}).get("page")
                        for r in occ if (r.grounding.get("pdf") or {}).get("page")})
        out.append({"id": e.id, "name": p.get("name") or "", "kind": e.subtype,
                    "expansion": p.get("expansion") or "", "pages": pages,
                    "n_occ": len(occ)})
    # unique keys, stable order
    seen, res = set(), []
    for c in sorted(out, key=lambda c: c["name"].lower()):
        if not c["name"]:
            continue
        c["key"] = _key(c["name"])
        while c["key"] in seen:
            c["key"] += "x"
        seen.add(c["key"])
        res.append(c)
    return res


def _document(graph):
    return next((e for e in graph.entities.values() if e.type == EntityType.DOCUMENT), None)


def _ordered_sections(graph) -> list[tuple]:
    """(depth, section_entity) in reading order, walking the ordered CONTAINS tree."""
    root = _document(graph)
    if root is None:
        return []
    out: list[tuple] = []

    def walk(node_id, depth):
        for r in ordering.ordered_children(graph, node_id, RelationType.CONTAINS):
            child = graph.get(r.object_id)
            if child and child.type == EntityType.CONCEPT and child.subtype == "section":
                out.append((depth, child))
                walk(child.id, depth + 1)
    walk(root.id, 0)
    return out


def _title(graph) -> str:
    d = _document(graph)
    return (d.properties().get("title") if d else "") or "Document"


# ---------------------------------------------------------------------------
# Enhanced standard LaTeX: acronyms + glossary + symbols + index
# ---------------------------------------------------------------------------

def project_latex(graph, bibkey: str = "DOC") -> str:
    concepts = _concepts(graph)
    acr = [c for c in concepts if c["kind"] == "acronym"]
    terms = [c for c in concepts if c["kind"] == "term"]
    syms = [c for c in concepts if c["kind"] == "symbol"]

    L = [r"\documentclass[11pt]{article}",
         r"\usepackage{lmodern}", r"\usepackage[T1]{fontenc}",
         r"\usepackage{amsmath,amssymb}",
         r"\usepackage{imakeidx}",
         r"\usepackage[acronym,symbols,toc]{glossaries-extra}",
         r"\setabbreviationstyle[acronym]{long-short}",
         r"\makeindex[intoc]", r"\makeglossaries", ""]

    for c in acr:
        L.append(rf"\newacronym{{{c['key']}}}{{{_esc(c['name'])}}}{{{_esc(c['expansion'])}}}")
    for c in terms:
        desc = _esc(c["expansion"]) or _esc(c["name"])
        L.append(rf"\newglossaryentry{{{c['key']}}}{{name={{{_esc(c['name'])}}},"
                 rf"description={{{desc}}}}}")
    for c in syms:
        desc = _esc(c["expansion"]) or "symbol"
        L.append(rf"\newglossaryentry{{{c['key']}}}{{type=symbols,name={{{_esc(c['name'])}}},"
                 rf"description={{{desc}}},sort={{{c['key']}}}}}")

    L += ["", rf"\title{{{_esc(_title(graph))}}}",
          r"\author{Generated by pdfdrill from the semantic graph}", r"\date{}",
          r"\begin{document}", r"\maketitle", r"\tableofcontents", ""]

    # document structure (the ordered CONTAINS tree)
    for depth, s in _ordered_sections(graph):
        cmd = ("section", "subsection", "subsubsection")[min(depth, 2)]
        num = s.properties().get("section_number", "")
        cap = _esc(s.properties().get("caption", "") or "Section")
        L.append(rf"\{cmd}{{{(num + ' ') if num else ''}{cap}}}")

    # use each concept so the glossary/index/symbols populate, with the
    # pdfdrill-only provenance back-link (PDF pages).
    if concepts:
        L += ["", r"\section{Extracted concepts (provenance-linked)}"]
        for c in concepts:
            pages = ", ".join(str(p) for p in c["pages"]) or "n/a"
            L.append(rf"\Gls{{{c['key']}}}\index{{{_esc(c['name'])}}} "
                     rf"--- {c['n_occ']} occurrence(s), PDF page(s) {pages}.\par")

    L += ["", r"\printglossary[type=symbols,title={Table of Symbols}]",
          r"\printglossary[type=\acronymtype,title={Acronyms}]",
          r"\printglossary[title={Glossary}]",
          r"\printindex",
          r"\end{document}", ""]
    return "\n".join(L)


# ---------------------------------------------------------------------------
# sTeX: smodule / \symdecl / sdefinition / \symref
# ---------------------------------------------------------------------------

def project_stex(graph, bibkey: str = "DOC") -> str:
    concepts = _concepts(graph)
    mod = re.sub(r"[^A-Za-z0-9]", "", bibkey) or "Doc"

    # The module (declarations + definitions) and its uses live INSIDE the
    # document; \symref works directly within the enclosing smodule.
    L = [r"\documentclass{article}",
         r"\usepackage[T1]{fontenc}", r"\usepackage{amsmath,amssymb}",
         r"\usepackage{stex}", "",
         r"\begin{document}",
         rf"\begin{{smodule}}{{{mod}}}"]

    for c in concepts:                            # one \symdecl per concept
        L.append(rf"  \symdecl*{{{c['key']}}}")
    L.append("")

    for c in concepts:                            # an sdefinition at its def site
        notion = _esc(c["expansion"]) or _esc(c["name"])
        pages = ", ".join(str(p) for p in c["pages"]) or "n/a"
        L.append(rf"  \begin{{sdefinition}}[for={{{c['key']}}}]")
        L.append(rf"    \definiendum{{{c['key']}}}{{{_esc(c['name'])}}} is {notion}. "
                 rf"% provenance: PDF page(s) {pages}")
        L.append(r"  \end{sdefinition}")
    L.append("")

    for c in concepts:                            # the many uses -> \symref
        L.append(rf"  \symref{{{c['key']}}}{{{_esc(c['name'])}}} recurs throughout "
                 rf"({c['n_occ']} occurrences).\par")

    L += [r"\end{smodule}", r"\end{document}", ""]
    return "\n".join(L)
