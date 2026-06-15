#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vocab.py -- one consistent interface over every controlled vocabulary, thesaurus
and classification index we feed pdfdrill (MSC, DLMF, OntoMathPRO, PhySH, ACM CCS,
STW, GND, GermaNet, ...).

Whatever the native format -- SKOS/RDF, OWL Manchester, GermaNet XML, MathPix
Markdown, the existing MSC JSON -- a source compiles to the SAME in-memory shape:

    Vocabulary
        scheme      : str                         short id, e.g. "msc", "physh", "stw"
        concepts    : code -> Concept             the hierarchy / nodes
        term_index  : term -> {code: weight}      IDF-scored inverted index
        idf         : term -> float
        meta        : {lang, source, version, ...}

and answers the same queries (this is the MSCStore surface, generalised):

        v.lookup(code)        -> Concept | None
        v.ancestors(code)     -> [code, ...]      root-ward
        v.siblings(code)      -> [code, ...]
        v.narrower(code)      -> [code, ...]
        v.match(surface)      -> [Hit, ...]       one surface form
        v.classify(text, k)   -> [Hit, ...]       ranked, with evidence

No if/else classification chain: lookup is O(len(code)) on the hierarchy,
classify is O(#grams) on the inverted index.

Adapters live elsewhere (skos.py, owl.py, germanet.py, ...) and all end by
calling Vocabulary.compile(scheme, concepts, meta). The federation layer
(federate.py) loads several Vocabularies and always queries all of them.

Pure standard library.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Iterable, Tuple


# --------------------------------------------------------------------------- #
#  Normalisation / tokenisation  (shared by every source so matching is fair)
# --------------------------------------------------------------------------- #

# Stray *spacing* diacritics that survive bad PDF extraction, e.g. "Schr¨odinger".
# NFKD only folds *combining* marks; these spacing ones must be dropped by hand.
_STRAY_DIACRITICS = dict.fromkeys(map(ord, "\u00a8\u00b4\u0060\u02c6\u02dc\u00af\u00b8"), None)

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)  # letters only, no digits/punct


def fold(s: str) -> str:
    """Lower-case, drop stray spacing diacritics, strip combining marks."""
    s = s.translate(_STRAY_DIACRITICS)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower().strip()


def tokens(s: str) -> List[str]:
    """Unigram word tokens (length >= 2) of a folded string."""
    return [t for t in _WORD_RE.findall(fold(s)) if len(t) >= 2]


def grams(s: str) -> List[str]:
    """Unigrams + adjacent bigrams, so multiword labels match as a unit.

    Bigrams are joined with a space and are how 'soliton equation' or
    'lineare Abbildung' beat the sum of their parts at classify time.
    """
    toks = tokens(s)
    out = list(toks)
    out += [f"{a} {b}" for a, b in zip(toks, toks[1:])]
    return out


# --------------------------------------------------------------------------- #
#  Data model
# --------------------------------------------------------------------------- #

@dataclass
class Concept:
    """One node in a vocabulary. `code` is the stable id within the scheme
    (MSC code, PhySH/STW/GND notation, OntoMathPRO E-number, GermaNet synset id).
    """
    code: str
    pref: str = ""                                   # preferred label (display)
    labels: Dict[str, List[str]] = field(default_factory=dict)  # lang -> [labels incl. synonyms]
    kind: str = ""                                   # scheme-specific facet/type, free text
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    related: List[str] = field(default_factory=list)
    definition: str = ""

    def surface_forms(self) -> List[Tuple[str, float]]:
        """(label, field-weight) pairs feeding the inverted index.
        Preferred labels weigh 1.0; alternates/synonyms weigh 0.7 so a synonym
        match still counts but never outranks a prefLabel match.
        """
        out: List[Tuple[str, float]] = []
        seen = set()
        if self.pref:
            out.append((self.pref, 1.0))
            seen.add(fold(self.pref))
        for _lang, labs in self.labels.items():
            for lab in labs:
                if fold(lab) not in seen:
                    out.append((lab, 0.7))
                    seen.add(fold(lab))
        return out


@dataclass
class Hit:
    """A ranked match, with the grams that produced it (the evidence)."""
    scheme: str
    code: str
    pref: str
    score: float
    evidence: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------- #
#  Vocabulary
# --------------------------------------------------------------------------- #

class Vocabulary:
    SCHEMA = 1

    def __init__(self, scheme: str, concepts: Dict[str, Concept],
                 term_index: Dict[str, Dict[str, float]], idf: Dict[str, float],
                 meta: Optional[dict] = None):
        self.scheme = scheme
        self.concepts = concepts
        self.term_index = term_index
        self.idf = idf
        self.meta = meta or {}

    # ---- construction ----------------------------------------------------- #

    @classmethod
    def compile(cls, scheme: str, concepts: Iterable[Concept],
                meta: Optional[dict] = None) -> "Vocabulary":
        """Build the inverted index + IDF from a set of Concepts. This is the
        single entry point every adapter calls."""
        cmap: Dict[str, Concept] = {c.code: c for c in concepts}

        # document frequency per gram, with field weights
        postings: Dict[str, Dict[str, float]] = {}
        for code, c in cmap.items():
            best_w: Dict[str, float] = {}
            for label, w in c.surface_forms():
                for g in grams(label):
                    # bigrams count a touch more than unigrams within a label
                    gw = w * (1.3 if " " in g else 1.0)
                    if gw > best_w.get(g, 0.0):
                        best_w[g] = gw
            for g, gw in best_w.items():
                postings.setdefault(g, {})[code] = gw

        n = max(1, len(cmap))
        idf = {g: math.log(1.0 + n / len(codes)) for g, codes in postings.items()}
        return cls(scheme, cmap, postings, idf, meta)

    # ---- persistence ------------------------------------------------------ #

    def save(self, path: str) -> None:
        blob = {
            "_schema": self.SCHEMA,
            "scheme": self.scheme,
            "meta": self.meta,
            "concepts": {k: asdict(v) for k, v in self.concepts.items()},
            "term_index": self.term_index,
            "idf": self.idf,
        }
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(blob, fh, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "Vocabulary":
        with open(path, encoding="utf-8") as fh:
            blob = json.load(fh)
        concepts = {k: Concept(**v) for k, v in blob["concepts"].items()}
        return cls(blob["scheme"], concepts, blob["term_index"], blob["idf"],
                   blob.get("meta", {}))

    # ---- hierarchy queries ------------------------------------------------ #

    def lookup(self, code: str) -> Optional[Concept]:
        return self.concepts.get(code)

    def ancestors(self, code: str) -> List[str]:
        out, seen = [], set()
        cur = self.concepts.get(code)
        while cur and cur.parent and cur.parent not in seen:
            out.append(cur.parent)
            seen.add(cur.parent)
            cur = self.concepts.get(cur.parent)
        return out

    def siblings(self, code: str) -> List[str]:
        c = self.concepts.get(code)
        if not c or not c.parent:
            return []
        parent = self.concepts.get(c.parent)
        if not parent:
            return []
        return [k for k in parent.children if k != code]

    def narrower(self, code: str) -> List[str]:
        c = self.concepts.get(code)
        return list(c.children) if c else []

    # ---- text -> concepts ------------------------------------------------- #

    def _score(self, query_grams: Iterable[str]) -> Dict[str, Tuple[float, List[str]]]:
        acc: Dict[str, Tuple[float, List[str]]] = {}
        for g in set(query_grams):
            posting = self.term_index.get(g)
            if not posting:
                continue
            w = self.idf.get(g, 0.0)
            for code, fw in posting.items():
                s, ev = acc.get(code, (0.0, []))
                acc[code] = (s + w * fw, ev + [g])
        return acc

    def match(self, surface: str, k: int = 10) -> List[Hit]:
        """Rank concepts for a single surface form (a term, not a document)."""
        return self.classify(surface, k=k)

    def classify(self, text: str, k: int = 10) -> List[Hit]:
        """Rank concepts for arbitrary text. Returns top-k Hits with evidence."""
        acc = self._score(grams(text))
        hits = [
            Hit(self.scheme, code, self.concepts[code].pref, round(s, 6),
                sorted(set(ev), key=lambda g: (-len(g), g)))
            for code, (s, ev) in acc.items()
        ]
        hits.sort(key=lambda h: (-h.score, h.code))
        return hits[:k]

    # ---- misc ------------------------------------------------------------- #

    def __len__(self) -> int:
        return len(self.concepts)

    def __repr__(self) -> str:
        return (f"<Vocabulary {self.scheme!r} concepts={len(self.concepts)} "
                f"grams={len(self.term_index)} lang={self.meta.get('lang','?')}>")


if __name__ == "__main__":
    # tiny smoke test with hand-made concepts
    cs = [
        Concept("35Q55", pref="NLS-like (nonlinear Schrödinger) equations",
                labels={"en": ["NLS equations", "nonlinear Schrödinger equation"]},
                parent="35Qxx"),
        Concept("35Qxx", pref="Partial differential equations of mathematical physics",
                children=["35Q55"]),
        Concept("11A41", pref="Primes", labels={"en": ["prime numbers"]}),
    ]
    v = Vocabulary.compile("msc", cs, meta={"lang": "en", "source": "smoke"})
    print(v)
    print("lookup:", v.lookup("35Q55").pref)
    print("ancestors:", v.ancestors("35Q55"))
    for h in v.classify("a soliton of the nonlinear Schrödinger equation"):
        print("  ", h.code, h.score, h.evidence)
