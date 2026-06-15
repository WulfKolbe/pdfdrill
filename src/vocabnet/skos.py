#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skos.py -- ingest any SKOS thesaurus into a Vocabulary.

One adapter, four sources: PhySH, ACM CCS 2012, STW (Standard-Thesaurus
Wirtschaft) and GND all publish SKOS. Two input syntaxes are supported with
the standard library only:

    * N-Triples (.nt)   -- the robust default; every line is `<s> <p> <o> .`
    * RDF/XML (.rdf)    -- via xml.etree

Both compile through Vocabulary.compile, so the result is byte-identical in
shape to the MSC store and plugs straight into the federation.

    from skos import load_skos
    stw = load_skos("stw.nt", scheme="stw", lang="de")
    physh = load_skos("physh.rdf", scheme="physh", lang="en")

SKOS predicates honoured: prefLabel, altLabel, hiddenLabel (-> synonyms),
broader (-> parent), narrower (-> children), related, notation (-> code),
definition / scopeNote. Concept code = skos:notation if present, else the
compact tail of the concept URI.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import Dict, List, Optional

from .vocab import Concept, Vocabulary

SKOS = "http://www.w3.org/2004/02/skos/core#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

_PRED = {
    SKOS + "prefLabel": "pref",
    SKOS + "altLabel": "alt",
    SKOS + "hiddenLabel": "alt",
    SKOS + "broader": "broader",
    SKOS + "narrower": "narrower",
    SKOS + "related": "related",
    SKOS + "notation": "notation",
    SKOS + "definition": "definition",
    SKOS + "scopeNote": "definition",
}


class _Raw:
    __slots__ = ("pref", "alt", "broader", "narrower", "related",
                 "notation", "definition", "is_concept")

    def __init__(self):
        self.pref: Dict[str, List[str]] = defaultdict(list)
        self.alt: Dict[str, List[str]] = defaultdict(list)
        self.broader: List[str] = []
        self.narrower: List[str] = []
        self.related: List[str] = []
        self.notation: Optional[str] = None
        self.definition: str = ""
        self.is_concept: bool = False


# --------------------------------------------------------------------------- #
#  URI -> compact code
# --------------------------------------------------------------------------- #

def _tail(uri: str) -> str:
    if "#" in uri:
        return uri.rsplit("#", 1)[1]
    return uri.rstrip("/").rsplit("/", 1)[-1]


# --------------------------------------------------------------------------- #
#  N-Triples
# --------------------------------------------------------------------------- #

_NT_LINE = re.compile(
    r"""^\s*
        (?:<(?P<s_uri>[^>]*)>|_:(?P<s_bnode>\S+))\s+
        <(?P<p>[^>]*)>\s+
        (?:<(?P<o_uri>[^>]*)>
          |_:(?P<o_bnode>\S+)
          |"(?P<o_lit>(?:[^"\\]|\\.)*)"(?:@(?P<o_lang>[\w-]+)|\^\^<[^>]*>)?)
        \s*\.\s*$""",
    re.VERBOSE,
)

_ESC = {"\\n": "\n", "\\t": "\t", "\\r": "\r", '\\"': '"', "\\\\": "\\"}


def _unescape(lit: str) -> str:
    out = re.sub(r"\\u([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), lit)
    out = re.sub(r"\\U([0-9A-Fa-f]{8})", lambda m: chr(int(m.group(1), 16)), out)
    for k, v in _ESC.items():
        out = out.replace(k, v)
    return out


def _parse_ntriples(path: str) -> Dict[str, _Raw]:
    raw: Dict[str, _Raw] = defaultdict(_Raw)
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            m = _NT_LINE.match(line)
            if not m:
                continue
            s = m.group("s_uri")
            if s is None:
                continue  # ignore blank-node subjects (e.g. GND compound mappings)
            p = m.group("p")
            node = raw[s]
            if p == RDF + "type" and m.group("o_uri") == SKOS + "Concept":
                node.is_concept = True
                continue
            field = _PRED.get(p)
            if field is None:
                continue
            if field in ("broader", "narrower", "related"):
                if m.group("o_uri"):
                    getattr(node, field).append(m.group("o_uri"))
            elif field == "notation":
                if m.group("o_lit") is not None:
                    node.notation = _unescape(m.group("o_lit"))
            elif field == "definition":
                if m.group("o_lit") is not None and not node.definition:
                    node.definition = _unescape(m.group("o_lit"))
            else:  # pref / alt
                if m.group("o_lit") is not None:
                    lang = m.group("o_lang") or ""
                    getattr(node, field)[lang].append(_unescape(m.group("o_lit")))
    return raw


# --------------------------------------------------------------------------- #
#  RDF/XML
# --------------------------------------------------------------------------- #

def _q(ns: str, local: str) -> str:
    return "{%s}%s" % (ns, local)


def _parse_rdfxml(path: str) -> Dict[str, _Raw]:
    raw: Dict[str, _Raw] = defaultdict(_Raw)
    about = _q(RDF, "about")
    resource = _q(RDF, "resource")
    lang_attr = "{http://www.w3.org/XML/1998/namespace}lang"

    for _evt, elem in ET.iterparse(path, events=("end",)):
        if elem.tag != _q(SKOS, "Concept") and elem.tag != _q(RDF, "Description"):
            continue
        subj = elem.get(about)
        if not subj:
            continue
        node = raw[subj]
        if elem.tag == _q(SKOS, "Concept"):
            node.is_concept = True
        for child in elem:
            tag = child.tag
            field = _PRED.get(tag.replace("{" + SKOS + "}", SKOS))
            # ET tags are already {ns}local; rebuild full predicate uri:
            if "}" in tag:
                ns, local = tag[1:].split("}", 1)
                field = _PRED.get(ns + local)
                if tag == _q(RDF, "type"):
                    if child.get(resource) == SKOS + "Concept":
                        node.is_concept = True
                    continue
            if field is None:
                continue
            if field in ("broader", "narrower", "related"):
                ref = child.get(resource)
                if ref:
                    getattr(node, field).append(ref)
            elif field == "notation":
                if child.text:
                    node.notation = child.text.strip()
            elif field == "definition":
                if child.text and not node.definition:
                    node.definition = child.text.strip()
            else:
                if child.text:
                    lang = child.get(lang_attr, "")
                    getattr(node, field)[lang].append(child.text.strip())
        elem.clear()
    return raw


# --------------------------------------------------------------------------- #
#  Raw -> Vocabulary
# --------------------------------------------------------------------------- #

def _build(raw: Dict[str, _Raw], scheme: str, lang: str,
           meta: Optional[dict]) -> Vocabulary:
    # keep concepts: anything typed skos:Concept, or (lenient) anything with a prefLabel
    uris = [u for u, r in raw.items() if r.is_concept or r.pref]
    code_of: Dict[str, str] = {}
    for u in uris:
        r = raw[u]
        code_of[u] = r.notation.strip() if r.notation else _tail(u)

    def pref_label(r: _Raw) -> str:
        if lang and r.pref.get(lang):
            return r.pref[lang][0]
        for labs in r.pref.values():
            if labs:
                return labs[0]
        if lang and r.alt.get(lang):
            return r.alt[lang][0]
        return ""

    concepts: Dict[str, Concept] = {}
    for u in uris:
        r = raw[u]
        code = code_of[u]
        labels: Dict[str, List[str]] = {}
        for lg, labs in list(r.pref.items()) + list(r.alt.items()):
            labels.setdefault(lg or "und", [])
            for x in labs:
                if x not in labels[lg or "und"]:
                    labels[lg or "und"].append(x)
        parent = None
        if r.broader:
            parent = code_of.get(r.broader[0], _tail(r.broader[0]))
        children = [code_of.get(c, _tail(c)) for c in r.narrower]
        related = [code_of.get(c, _tail(c)) for c in r.related]
        concepts[code] = Concept(
            code=code, pref=pref_label(r), labels=labels,
            parent=parent, children=children, related=related,
            definition=r.definition,
        )

    # reconcile hierarchy: broader implies the parent should list us as child
    for code, c in concepts.items():
        if c.parent and c.parent in concepts:
            p = concepts[c.parent]
            if code not in p.children:
                p.children.append(code)
    # and narrower implies those children point back to us as parent
    for code, c in concepts.items():
        for ch in c.children:
            if ch in concepts and concepts[ch].parent is None:
                concepts[ch].parent = code

    m = {"lang": lang, "format": "skos"}
    m.update(meta or {})
    return Vocabulary.compile(scheme, concepts.values(), meta=m)


def load_skos(path: str, scheme: str, lang: str = "en",
              fmt: Optional[str] = None, meta: Optional[dict] = None) -> Vocabulary:
    """Load a SKOS file into a Vocabulary.

    fmt: "nt" | "rdf" | None (auto from extension).
    lang: preferred language for the display prefLabel (labels of all langs kept).
    """
    if fmt is None:
        fmt = "rdf" if path.rsplit(".", 1)[-1].lower() in ("rdf", "xml", "owl") else "nt"
    raw = _parse_rdfxml(path) if fmt == "rdf" else _parse_ntriples(path)
    return _build(raw, scheme, lang, meta)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        v = load_skos(sys.argv[1], scheme=sys.argv[2],
                      lang=sys.argv[3] if len(sys.argv) > 3 else "en")
        print(v)
