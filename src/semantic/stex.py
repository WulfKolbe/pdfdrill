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
        name = p.get("name") or ""
        # aliases (S5.1): (a) an acronym's expansion IS its long-form synonym
        # (the Schwartz-Hearst pair); (b) >1 distinct name/alias Evidence values
        # on one resolved entity mean those surface forms are synonyms.
        aliases: set[str] = set()
        if e.subtype == "acronym" and p.get("expansion"):
            aliases.add(p["expansion"])
        for ev in e.evidence:
            if ev.prop in ("name", "alias") and ev.value and ev.value != name:
                aliases.add(ev.value)
        out.append({"id": e.id, "name": name, "kind": e.subtype,
                    "expansion": p.get("expansion") or "", "pages": pages,
                    "n_occ": len(occ), "aliases": sorted(aliases)})
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


def _measured_quantities(graph) -> list[dict]:
    """One record per MEASURES edge (S5.2): the measured concept, the measure
    verb + conditions (edge grounding), the QUANTITY's value/unit/page, and its
    arith verification state (verifies/refutes Evidence rows)."""
    out = []
    for r in graph.relations:
        if r.predicate != RelationType.MEASURES:
            continue
        subj, q = graph.get(r.subject_id), graph.get(r.object_id)
        if q is None:
            continue
        p = q.properties()
        page = next(((ev.grounding or {}).get("page") for ev in q.evidence
                     if (ev.grounding or {}).get("page") is not None), None)
        g = r.grounding or {}
        out.append({
            "concept": (subj.properties().get("name") or subj.value or ""
                        ) if subj is not None else "",
            "measure": g.get("measure", ""),
            "conditions": g.get("conditions") or {},
            "value": p.get("value", ""), "unit": p.get("unit", ""),
            "page": page,
            "verified": any(ev.produced_by == "arith" and ev.prop == "verifies"
                            for ev in q.evidence),
            "refuted": any(ev.produced_by == "arith" and ev.prop == "refutes"
                           for ev in q.evidence),
            "hash": (p.get("content_hash") or "")[:8] or _key(str(p.get("value"))),
        })
    return out


# ---------------------------------------------------------------------------
# Enhanced standard LaTeX: acronyms + glossary + symbols + index
# ---------------------------------------------------------------------------

def project_latex(graph, bibkey: str = "DOC", verify_marks: bool = True) -> str:
    concepts = _concepts(graph)
    acr = [c for c in concepts if c["kind"] == "acronym"]
    terms = [c for c in concepts if c["kind"] == "term"]
    syms = [c for c in concepts if c["kind"] == "symbol"]
    quantities = _measured_quantities(graph)

    L = [r"\documentclass[11pt]{article}",
         r"\usepackage{lmodern}", r"\usepackage[T1]{fontenc}",
         r"\usepackage{amsmath,amssymb}",
         r"\usepackage{imakeidx}",
         r"\usepackage[acronym,symbols,toc]{glossaries-extra}",
         r"\setabbreviationstyle[acronym]{long-short}",
         r"\newglossary*{synonyms}{Synonyms}",
         r"\newglossary*{quantities}{Table of Quantities}",
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

    # TABLE OF QUANTITIES (S5.2): one entry per MEASURES edge — the graph's
    # quantitative layer as a LaTeX list. The verified-status suffix (\,\checkmark
    # verified / \,! refuted) is a projector param so the marks can be disabled.
    seen_qkeys: set = set()
    for q in quantities:
        qk = "q" + (q["hash"] or "x")
        while qk in seen_qkeys:
            qk += "x"
        seen_qkeys.add(qk)
        cond = ", ".join(f"{k}={v}" for k, v in sorted(q["conditions"].items()))
        desc = f"{_esc(q['measure']) or 'measures'}: {_esc(str(q['value']))}"
        if q["unit"]:
            desc += f" {_esc(q['unit'])}"
        if cond:
            desc += f" ({_esc(cond)})"
        if q["page"] is not None:
            desc += rf", p.~{q['page']}"
        if verify_marks and q["refuted"]:
            desc += r"\,!"
        elif verify_marks and q["verified"]:
            desc += r"\,\checkmark"
        L.append(rf"\newglossaryentry{{{qk}}}{{type=quantities,"
                 rf"name={{{_esc(q['concept']) or 'quantity'}}},"
                 rf"description={{{desc}}}}}")

    # SYNONYMS (S5.1): each alias is a glossaries-native cross-reference entry
    # (`see=` is the package's synonym mechanism) pointing at its main key, with
    # the page back-link comment convention kept.
    seen_alias_keys = {c["key"] for c in concepts}
    for c in concepts:
        for alias in c.get("aliases", []):
            ak = _key(alias)
            while ak in seen_alias_keys:
                ak += "x"
            seen_alias_keys.add(ak)
            pages = ", ".join(str(p) for p in c["pages"]) or "n/a"
            L.append(rf"\newglossaryentry{{{ak}}}{{type=synonyms,"
                     rf"name={{{_esc(alias)}}},description={{synonym}},"
                     rf"see={{{c['key']}}}}}"
                     rf"  % synonym of {_esc(c['name'])}, PDF page(s) {pages}")

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

    L += ["", r"\glsaddall[types={synonyms,quantities}]",   # list-only entries print
          r"\printglossary[type=symbols,title={Table of Symbols}]",
          r"\printglossary[type=\acronymtype,title={Acronyms}]",
          r"\printglossary[title={Glossary}]",
          r"\printglossary[type=synonyms,title={Synonyms}]",
          r"\printglossary[type=quantities,title={Table of Quantities}]",
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
        # S5.1: an alias is a \symref VARIANT NOTE on the SAME \symdecl — one
        # symbol, many surface forms (the (theory, name) discipline).
        for alias in c.get("aliases", []):
            L.append(rf"  Also written \symref{{{c['key']}}}{{{_esc(alias)}}}.\par")

    L += [r"\end{smodule}", r"\end{document}", ""]
    return "\n".join(L)
