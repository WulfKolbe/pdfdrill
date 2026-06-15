#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
germanet.py -- ingest GermaNet (the German WordNet) from its XML release into a
Vocabulary.

GermaNet ships per-category synset files (`nomen.*.xml`, `verben.*.xml`,
`adj.*.xml`), each `<synset>` carrying one or more `<lexUnit><orthForm>` lemmas
and an optional `<paraphrase>`; the conceptual relations (hypernymy etc.) live
in a separate `gn_relations.xml` as `<con_rel name="has_hyponym" from=… to=…/>`.

So `load_germanet` accepts EITHER a directory (all `*.xml` parsed; synsets from
the category files, hierarchy from the relations file) OR a single XML file
(synsets only, no hierarchy). The result compiles to the same Vocabulary shape.

  * code         = synset id (e.g. "s123")
  * pref         = first orthForm
  * labels[de]   = every orthForm of the synset (synonyms -- the WordNet value)
  * definition   = the synset paraphrase, if present
  * parent       = hypernym synset (has_hyponym from=parent to=child, or
                   has_hypernym from=child to=parent)

GermaNet needs a signed academic licence -- the release files stay out of git
(see vocab/sources/germanet/STUB.md). Ends in one Vocabulary.compile(...).

Pure standard library.
"""

from __future__ import annotations

import glob
import os
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from .vocab import Concept, Vocabulary


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _iter(elem, name: str):
    for e in elem.iter():
        if _local(e.tag) == name:
            yield e


def _parse_file(path: str, synsets: Dict[str, dict],
                rels: List[Tuple[str, str, str]]) -> None:
    """Accumulate synsets + con_rel triples from one XML file (layout-agnostic:
    a file may hold synsets, relations, or both)."""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return
    for syn in _iter(root, "synset"):
        sid = syn.get("id")
        if not sid:
            continue
        rec = synsets.setdefault(sid, {"labels": [], "definition": "",
                                       "category": syn.get("category", "")})
        for lu in _iter(syn, "lexUnit"):
            for of in _iter(lu, "orthForm"):
                w = (of.text or "").strip()
                if w and w not in rec["labels"]:
                    rec["labels"].append(w)
        if not rec["definition"]:
            for tag in ("paraphrase", "wiktionaryParaphrase"):
                for p in _iter(syn, tag):
                    txt = (p.text or "").strip()
                    if txt:
                        rec["definition"] = txt
                        break
                if rec["definition"]:
                    break
    for cr in _iter(root, "con_rel"):
        name = (cr.get("name") or "").strip()
        frm, to = cr.get("from"), cr.get("to")
        if name and frm and to:
            rels.append((name, frm, to))


def load_germanet(path: str, scheme: str = "germanet", lang: str = "de",
                  meta: Optional[dict] = None) -> Vocabulary:
    if os.path.isdir(path):
        files = sorted(glob.glob(os.path.join(path, "*.xml")))
    else:
        files = [path]

    synsets: Dict[str, dict] = {}
    rels: List[Tuple[str, str, str]] = []
    for f in files:
        _parse_file(f, synsets, rels)

    concepts: Dict[str, Concept] = {}
    for sid, rec in synsets.items():
        labs = rec["labels"]
        concepts[sid] = Concept(
            code=sid,
            pref=labs[0] if labs else "",
            labels={lang: list(labs)} if labs else {},
            kind=rec["category"],
            definition=rec["definition"],
        )

    # apply hypernymy: normalise every relation to (parent, child)
    for name, frm, to in rels:
        if name in ("has_hyponym", "is_hypernym_of"):
            parent, child = frm, to
        elif name in ("has_hypernym", "is_hyponym_of"):
            parent, child = to, frm
        else:
            continue
        if parent in concepts and child in concepts:
            if concepts[child].parent is None:
                concepts[child].parent = parent
            if child not in concepts[parent].children:
                concepts[parent].children.append(child)

    m = {"lang": lang, "format": "germanet-xml", "source": "germanet"}
    m.update(meta or {})
    return Vocabulary.compile(scheme, concepts.values(), meta=m)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        print(load_germanet(sys.argv[1]))
