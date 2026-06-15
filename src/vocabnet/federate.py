#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
federate.py -- query every vocabulary at once, and keep the misses.

Design rule (per Wulf): we ALWAYS retrieve from all sources. A source returning
nothing is not noise to be dropped -- the *coverage pattern* (which schemes fire
and which stay silent for a given string) is a feature. A term grounded in
MSC + PhySH but absent from ACM CCS and STW is math-physics, not CS, not
business; that contrast is exactly what we want to feed semdrill downstream.

    from federate import Federation
    fed = Federation.load_dir("compiled/")        # *.json -> one Vocabulary each
    res = fed.classify("nonlinear Schrödinger soliton")
    res.present                                   # {'msc', 'physh', ...}
    res.absent                                    # {'stw', 'gnd', 'acmccs', ...}  <- signal
    res.profile                                   # {'msc': 6.8, 'physh': 4.1, 'stw': 0.0, ...}
    res.top                                       # {scheme: best Hit}
    res.fingerprint()                             # blake2b over the coverage signature
    res.to_dict()                                 # JSON / tiddler-ready

Pure standard library.
"""

from __future__ import annotations

import glob
import hashlib
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Iterable

from .vocab import Vocabulary, Hit


@dataclass
class FederatedResult:
    query: str
    per_source: Dict[str, List[Hit]]              # EVERY scheme present, [] == explicit miss

    # ---- derived views over the always-complete per_source map ----------- #

    @property
    def present(self) -> set:
        return {s for s, hits in self.per_source.items() if hits}

    @property
    def absent(self) -> set:
        return {s for s, hits in self.per_source.items() if not hits}

    @property
    def profile(self) -> Dict[str, float]:
        """Best score per scheme; 0.0 for a miss. A dense vector over schemes."""
        return {s: (hits[0].score if hits else 0.0) for s, hits in self.per_source.items()}

    @property
    def top(self) -> Dict[str, Hit]:
        return {s: hits[0] for s, hits in self.per_source.items() if hits}

    def signature(self) -> List[tuple]:
        """Stable (scheme, top_code) list over the schemes that fired -- the
        cross-source identity of this string. Sorted for reproducibility."""
        return sorted((s, h.code) for s, h in self.top.items())

    def fingerprint(self) -> str:
        """blake2b of the coverage signature (matches our content-id convention)."""
        payload = "|".join(f"{s}:{c}" for s, c in self.signature())
        return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "present": sorted(self.present),
            "absent": sorted(self.absent),
            "fingerprint": self.fingerprint(),
            "profile": self.profile,
            "per_source": {s: [h.to_dict() for h in hits]
                           for s, hits in self.per_source.items()},
        }


class Federation:
    def __init__(self, vocabs: Optional[Iterable[Vocabulary]] = None):
        self.vocabs: Dict[str, Vocabulary] = {}
        for v in (vocabs or []):
            self.add(v)

    def add(self, vocab: Vocabulary) -> "Federation":
        self.vocabs[vocab.scheme] = vocab
        return self

    @classmethod
    def load_dir(cls, path: str) -> "Federation":
        fed = cls()
        for fn in sorted(glob.glob(os.path.join(path, "*.json"))):
            fed.add(Vocabulary.load(fn))
        return fed

    # ---- the always-all-sources queries ---------------------------------- #

    def classify(self, text: str, k: int = 5) -> FederatedResult:
        """Run classify() against every source. Schemes with no match are kept
        with an empty hit list -- never dropped."""
        per = {scheme: v.classify(text, k=k) for scheme, v in self.vocabs.items()}
        return FederatedResult(text, per)

    def match(self, surface: str, k: int = 5) -> FederatedResult:
        return self.classify(surface, k=k)

    def resolve(self, code: str) -> Dict[str, object]:
        """A bare code may belong to any scheme. Return every scheme in which it
        resolves (usually one, but cross-scheme code collisions are themselves
        worth seeing)."""
        return {scheme: v.lookup(code) for scheme, v in self.vocabs.items()
                if v.lookup(code) is not None}

    @property
    def schemes(self) -> List[str]:
        return list(self.vocabs.keys())

    def __repr__(self) -> str:
        inner = ", ".join(f"{s}({len(v)})" for s, v in self.vocabs.items())
        return f"<Federation [{inner}]>"


if __name__ == "__main__":
    # end-to-end demo across three hand-made schemes
    from .vocab import Concept

    msc = Vocabulary.compile("msc", [
        Concept("35Q55", pref="NLS-like (nonlinear Schrödinger) equations",
                labels={"en": ["nonlinear Schrödinger equation", "soliton"]}),
    ], meta={"lang": "en"})
    physh = Vocabulary.compile("physh", [
        Concept("nlin.solitons", pref="Solitons",
                labels={"en": ["soliton", "nonlinear waves"]}),
    ], meta={"lang": "en"})
    stw = Vocabulary.compile("stw", [
        Concept("10838-0", pref="Import", labels={"de": ["Einfuhr"]}),
    ], meta={"lang": "de"})

    fed = Federation([msc, physh, stw])
    print(fed)
    res = fed.classify("a soliton solution of the nonlinear Schrödinger equation")
    print("present :", sorted(res.present))
    print("absent  :", sorted(res.absent), " <- kept as signal")
    print("profile :", res.profile)
    print("top     :", {s: (h.code, h.score) for s, h in res.top.items()})
    print("finger  :", res.fingerprint())
