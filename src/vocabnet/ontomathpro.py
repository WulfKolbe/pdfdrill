#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ontomathpro.py -- ingest the OntoMathPRO ontology from its OWL 2 Manchester
syntax (`.omn`) into a Vocabulary.

OntoMathPRO concepts carry stable **E-number** ids (E1, E2, ...) used elsewhere
as semdrill groundings, and bilingual (en/ru) labels. The Manchester syntax is
frame-based and line-oriented, so a small line state machine is enough with the
standard library only:

    Class: ontomath:E2
        Annotations:
            rdfs:label "Differential equation"@en,
            skos:prefLabel "Дифференциальное уравнение"@ru
        SubClassOf:
            ontomath:E1

  * code            = the E-number tail of the Class IRI / prefixed name
  * pref            = skos:prefLabel (then rdfs:label) in the target lang, else any
  * labels[lang]    = every label literal, by its @lang tag (all kept)
  * parent          = the first named E-number in SubClassOf (anon restrictions skipped)

Ends in one Vocabulary.compile(...), same as skos.py.

Pure standard library.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from .vocab import Concept, Vocabulary

# frame keywords that OPEN a new top-level frame (anything not Class: ends the
# current class context)
_FRAME = re.compile(
    r"^(Class|ObjectProperty|DataProperty|AnnotationProperty|Individual|"
    r"Datatype|EquivalentClasses|DisjointClasses|Ontology|Prefix|Import|"
    r"Rule|HasKey):",
    re.IGNORECASE,
)
# sub-keywords inside a Class frame
_SUBKEY = re.compile(
    r"^(Annotations|SubClassOf|EquivalentTo|DisjointWith|Types|Facts|"
    r"DisjointUnionOf):\s*(.*)$",
    re.IGNORECASE,
)
# a label annotation: <prop> "literal"@lang  (prop = rdfs:label / skos:pref|altLabel)
_LABEL = re.compile(
    r"(rdfs:label|skos:prefLabel|skos:altLabel)\s+"
    r'"((?:[^"\\]|\\.)*)"(?:@(?P<lang>[\w-]+))?',
)
# an E-number reference, prefixed (ontomath:E12) or full-IRI (<...#E12>)
_ENUM = re.compile(r"\bE\d+\b")

_ESC = {'\\"': '"', "\\\\": "\\", "\\n": "\n", "\\t": "\t"}


def _unescape(s: str) -> str:
    for k, v in _ESC.items():
        s = s.replace(k, v)
    return s


def _enum(token: str) -> Optional[str]:
    m = _ENUM.search(token or "")
    return m.group(0) if m else None


class _Raw:
    __slots__ = ("pref", "alt", "parent_candidates")

    def __init__(self):
        self.pref: Dict[str, List[str]] = {}   # rdfs:label / skos:prefLabel
        self.alt: Dict[str, List[str]] = {}    # skos:altLabel
        self.parent_candidates: List[str] = []


def load_ontomathpro(path: str, scheme: str = "ontomathpro", lang: str = "en",
                     meta: Optional[dict] = None) -> Vocabulary:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return build_ontomathpro(text, scheme=scheme, lang=lang, meta=meta)


def build_ontomathpro(text: str, scheme: str = "ontomathpro", lang: str = "en",
                      meta: Optional[dict] = None) -> Vocabulary:
    raw: Dict[str, _Raw] = {}
    cur: Optional[str] = None          # current E-number
    section: Optional[str] = None      # 'annotations' | 'subclassof' | ...

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        fm = _FRAME.match(stripped)
        if fm:
            section = None
            if fm.group(1).lower() == "class":
                code = _enum(stripped[fm.end():])
                if code:
                    cur = code
                    raw.setdefault(cur, _Raw())
                else:
                    cur = None         # anonymous / non-E class
            else:
                cur = None             # left the class frame
            continue

        if cur is None:
            continue

        sk = _SUBKEY.match(stripped)
        if sk:
            section = sk.group(1).lower()
            rest = sk.group(2).strip()
            _consume(raw[cur], section, rest)
            continue

        # continuation line for the active sub-section
        if section:
            _consume(raw[cur], section, stripped)

    return _compile(raw, scheme, lang, meta)


def _consume(node: _Raw, section: str, frag: str) -> None:
    if not frag:
        return
    if section == "annotations":
        for m in _LABEL.finditer(frag):
            prop, lit, lg = m.group(1), _unescape(m.group(2)), m.group("lang") or ""
            bucket = node.alt if prop == "skos:altLabel" else node.pref
            bucket.setdefault(lg, [])
            if lit not in bucket[lg]:
                bucket[lg].append(lit)
    elif section == "subclassof":
        # only named E-number superclasses; skip anonymous restrictions
        for tok in re.split(r"[,\s]+", frag):
            e = _enum(tok)
            if e and e not in node.parent_candidates:
                node.parent_candidates.append(e)


def _compile(raw: Dict[str, _Raw], scheme: str, lang: str,
             meta: Optional[dict]) -> Vocabulary:
    concepts: Dict[str, Concept] = {}
    for code, r in raw.items():
        labels: Dict[str, List[str]] = {}
        for lg, labs in list(r.pref.items()) + list(r.alt.items()):
            labels.setdefault(lg or "und", [])
            for x in labs:
                if x not in labels[lg or "und"]:
                    labels[lg or "und"].append(x)
        pref = _pick_pref(r, lang)
        parent = next((p for p in r.parent_candidates if p in raw), None)
        if parent is None and r.parent_candidates:
            parent = r.parent_candidates[0]   # superclass declared but out of file
        concepts[code] = Concept(code=code, pref=pref, labels=labels, parent=parent)

    for code, c in concepts.items():
        if c.parent and c.parent in concepts:
            p = concepts[c.parent]
            if code not in p.children:
                p.children.append(code)
        elif c.parent and c.parent not in concepts:
            c.parent = None

    m = {"lang": lang, "format": "owl-manchester", "source": "ontomathpro"}
    m.update(meta or {})
    return Vocabulary.compile(scheme, concepts.values(), meta=m)


def _pick_pref(r: _Raw, lang: str) -> str:
    # prefer prefLabel/rdfs:label in the target lang, then any prefLabel, then alt
    if lang and r.pref.get(lang):
        return r.pref[lang][0]
    for labs in r.pref.values():
        if labs:
            return labs[0]
    if lang and r.alt.get(lang):
        return r.alt[lang][0]
    for labs in r.alt.values():
        if labs:
            return labs[0]
    return ""


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        print(load_ontomathpro(sys.argv[1]))
