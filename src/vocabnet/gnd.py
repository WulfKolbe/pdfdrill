#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gnd.py -- ingest the DNB Gemeinsame Normdatei SUBJECT file (authorities-gnd-
sachbegriff) into a Vocabulary.

GND is published as RDF/XML but with the **GND element set** (gndo:), not plain
SKOS — so skos.py can't read it. Each subject concept is an
`<rdf:Description rdf:about="https://d-nb.info/gnd/<id>">` carrying:

  * gndo:preferredNameForTheSubjectHeading  -> pref label (de)
  * gndo:variantNameForTheSubjectHeading    -> alt labels (de)
  * gndo:broaderTermGeneral / …Generic / …Instantial (rdf:resource) -> parent
  * gndo:relatedTerm                        (rdf:resource) -> related

The released file is large (~400 MB / ~207k subject terms), so we **stream** it
with iterparse + elem.clear() (bounded memory). Records without a subject-heading
label (the `/about` description nodes, non-subject entities) are skipped. Code =
the GND id (the tail of the d-nb.info URI). Ends in one Vocabulary.compile(...).

This is the German-side complement so a GERMAN ORIGINAL classifies directly
(no translation): pair it with the `text_source` field via `pdfdrill classify`.

Pure standard library.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

from .vocab import Concept, Vocabulary

_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_GNDO = "https://d-nb.info/standards/elementset/gnd#"

_ABOUT = "{%s}about" % _RDF
_RESOURCE = "{%s}resource" % _RDF
_DESC = "{%s}Description" % _RDF
_PREF = "{%s}preferredNameForTheSubjectHeading" % _GNDO
_VAR = "{%s}variantNameForTheSubjectHeading" % _GNDO
_BROADER = ("{%s}broaderTermGeneral" % _GNDO, "{%s}broaderTermGeneric" % _GNDO,
            "{%s}broaderTermInstantial" % _GNDO)
_RELATED = "{%s}relatedTerm" % _GNDO
_TYPE = "{%s}type" % _RDF

# Keep only true SUBJECT-heading records. The sachbegriff file also carries
# work titles, historic events, transport/product/brand names, software, etc.
# (e.g. "Sturm auf das Kapitol", the "Bo 105" helicopter) — long proper-name
# entries that match generic prose via common words and pollute classification.
_SUBJECT_TYPES = frozenset({
    _GNDO + "SubjectHeadingSensoStricto",
    _GNDO + "SubjectHeading",
    _GNDO + "NomenclatureInBiologyOrChemistry",
})


def _tail(uri: str) -> str:
    return uri.rstrip("/").rsplit("/", 1)[-1]


def load_gnd(path: str, scheme: str = "gnd", lang: str = "de",
             meta: Optional[dict] = None,
             keep_types: frozenset = _SUBJECT_TYPES,
             max_label_words: int = 4) -> Vocabulary:
    """`max_label_words` drops long catalog entries that GND types as subject
    headings but that are really work/event/award TITLES ("Einführung in die
    sozialistische Produktion", "Dekade Solidarität der Kirchen mit den Frauen")
    — they match generic German prose via shared common words. Real subject terms
    are short (Gravitation, Allgemeine Relativitätstheorie); ≤4 words keeps them
    while removing the long-title noise. Set 0 to disable."""
    concepts: Dict[str, Concept] = {}
    for _ev, elem in ET.iterparse(path, events=("end",)):
        if elem.tag != _DESC:
            continue
        about = elem.get(_ABOUT)
        if not about or "/gnd/" not in about:
            elem.clear()
            continue
        pref: Optional[str] = None
        alts: List[str] = []
        parent: Optional[str] = None
        related: List[str] = []
        types: List[str] = []
        for ch in elem:
            t = ch.tag
            if t == _PREF and ch.text:
                pref = ch.text.strip()
            elif t == _VAR and ch.text:
                alts.append(ch.text.strip())
            elif t in _BROADER:
                r = ch.get(_RESOURCE)
                if r and parent is None:
                    parent = _tail(r)
            elif t == _RELATED:
                r = ch.get(_RESOURCE)
                if r:
                    related.append(_tail(r))
            elif t == _TYPE:
                r = ch.get(_RESOURCE)
                if r:
                    types.append(r)
        keep = pref and (not keep_types or any(ty in keep_types for ty in types))
        if keep and max_label_words and len(pref.split()) > max_label_words:
            keep = False                           # long title, not a subject term
        if keep:                                   # only real subject concepts
            code = _tail(about)
            labels = [pref] + [a for a in alts if a and a != pref]
            concepts[code] = Concept(code=code, pref=pref, labels={lang: labels},
                                     parent=parent, related=related)
        elem.clear()

    for code, c in concepts.items():
        if c.parent and c.parent in concepts and code not in concepts[c.parent].children:
            concepts[c.parent].children.append(code)
        elif c.parent and c.parent not in concepts:
            c.parent = None                        # broader term outside this file

    m = {"lang": lang, "format": "gnd-rdf", "source": "dnb-gnd-sachbegriff"}
    m.update(meta or {})
    return Vocabulary.compile(scheme, concepts.values(), meta=m)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        print(load_gnd(sys.argv[1]))
