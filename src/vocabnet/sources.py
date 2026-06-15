#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sources.py -- the registry of index sources and how each one is ingested.

Every source becomes a Vocabulary with the same interface; only the front-end
adapter differs. This file is the single place that records, per source: the
scheme id, the preferred language, the native download format, the adapter that
handles it, the upstream URL, and any licence caveat.

    python3 -m vocabnet.sources list
    python3 -m vocabnet.sources build stw   vocab/sources/stw/stw.nt
    python3 -m vocabnet.sources build msc   vocab/sources/msc/msc2020.json
    python3 -m vocabnet.sources build dlmf  vocab/sources/dlmf/dlmf-front.md
    python3 -m vocabnet.sources build all                 # build every present source

Adapters:
  * skos.load_skos            -> PhySH, ACM CCS, STW, GND      [READY]
  * msc_from_json (below)     -> existing mscc.py msc2020.json [READY, shim]
  * dlmf.load_dlmf            -> MathPix Markdown (pdfdrill)   [READY]
  * ontomathpro.load_*        -> OWL 2 Manchester (.omn)       [READY]
  * germanet.load_germanet    -> GermaNet XML                  [READY]

The downloaded vocabularies are licence-bound and stay OUT of git; each lives
under vocab/sources/<scheme>/ (gitignored) with a committed STUB.md giving the
download link + build command. Compiled indexes land in vocab/compiled/
(gitignored, regenerable).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .vocab import Vocabulary, Concept
from .skos import load_skos
from .dlmf import load_dlmf
from .ontomathpro import load_ontomathpro
from .germanet import load_germanet
from .gnd import load_gnd

# repo-relative working area (src/vocabnet/sources.py -> repo root is two up)
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SOURCE_DIR = os.path.join(_REPO, "vocab", "sources")
COMPILED_DIR = os.path.join(_REPO, "vocab", "compiled")


# --------------------------------------------------------------------------- #
#  MSC shim: load the existing mscc.py msc2020.json into a Vocabulary
# --------------------------------------------------------------------------- #

def msc_from_json(path: str, scheme: str = "msc", lang: str = "en",
                  meta: Optional[dict] = None) -> Vocabulary:
    """Adapt the store written by mscc.py (`codes` -> Node{title,kind,parent,
    children,related}) into a Vocabulary, then recompile the index so scoring is
    consistent with the other sources.

    NB: if mscc.py used different key names, adjust the .get() lines below --
    that is the only coupling point."""
    import json
    with open(path, encoding="utf-8") as fh:
        blob = json.load(fh)
    nodes = blob.get("codes") or blob.get("concepts") or {}
    concepts: List[Concept] = []
    for code, node in nodes.items():
        title = node.get("title") or node.get("pref") or ""
        concepts.append(Concept(
            code=code,
            pref=title,
            labels={lang: [title]},
            kind=node.get("kind", ""),
            parent=node.get("parent"),
            children=list(node.get("children", [])),
            related=list(node.get("related", [])),
        ))
    m = {"lang": lang, "format": "msc-json"}
    m.update(meta or {})
    return Vocabulary.compile(scheme, concepts, meta=m)


def load_msc(path: str, scheme: str = "msc", lang: str = "en",
             meta: Optional[dict] = None) -> Vocabulary:
    """MSC dispatcher: a CRAN/AMS `.html` listing -> msc_html adapter, else the
    mscc.py `.json` shim. (zbMATH's clean JSON is behind Cloudflare/T&C; the CRAN
    MSC-2010 HTML is the openly-fetchable full listing — see msc/STUB.md.)"""
    if path.rsplit(".", 1)[-1].lower() in ("html", "htm"):
        from .msc_html import load_msc_html
        return load_msc_html(path, scheme=scheme, lang=lang, meta=meta)
    return msc_from_json(path, scheme=scheme, lang=lang, meta=meta)


# --------------------------------------------------------------------------- #
#  Registry
# --------------------------------------------------------------------------- #

@dataclass
class Source:
    scheme: str
    title: str
    lang: str
    fmt: str                      # native download format
    adapter: Callable            # (path, scheme, lang, meta) -> Vocabulary
    url: str
    note: str = ""
    filenames: tuple = ()         # candidate input filenames under vocab/sources/<scheme>/


SOURCES: Dict[str, Source] = {s.scheme: s for s in [
    Source("msc", "Mathematics Subject Classification (2020/2010)", "en", "HTML/JSON",
           load_msc, "https://cran.r-project.org/web/classifications/MSC-2010.html",
           "CRAN MSC-2010 HTML (full, CC-BY-NC-SA, fetchable) or mscc.py msc2020.json; "
           "zbMATH's clean JSON is behind Cloudflare/T&C",
           filenames=("MSC-2010.html", "msc2020.json", "msc.json", "msc.html")),
    Source("dlmf", "NIST Digital Library of Mathematical Functions", "en", "MathPix MD",
           load_dlmf, "https://dlmf.nist.gov/",
           "chapter/front-matter PDF -> pdfdrill md -> here; only PDF source in the set",
           filenames=("dlmf-front.md", "dlmf.md")),
    Source("ontomathpro", "OntoMathPRO ontology (E-numbers)", "en", "OWL 2 Manchester",
           load_ontomathpro, "https://github.com/CLLKazan/OntoMathPro",
           "E-number concept ids; already used as semdrill groundings",
           filenames=("ontomathpro.omn", "ontomath.omn")),
    Source("physh", "Physics Subject Headings (APS)", "en", "SKOS",
           load_skos, "https://github.com/physh-org/PhySH",
           "download physh.nt.gz from the physh-org/PhySH repo (gunzip -> physh.nt); "
           "~3900 concepts, DOI-UUID codes + readable prefLabels; APS copyright "
           "(CC-BY 4.0) — keep the data out of git",
           filenames=("physh.nt", "physh.rdf")),
    Source("acmccs", "ACM Computing Classification System 2012", "en", "SKOS",
           load_skos, "https://dl.acm.org/ccs",
           "poly-hierarchical; same shape as MSC",
           filenames=("acm-ccs.nt", "acmccs.rdf")),
    Source("stw", "Standard-Thesaurus Wirtschaft (ZBW)", "de", "SKOS",
           load_skos, "https://zbw.eu/stw/",
           "~6000 descriptors + 20000 synonyms; altLabels are the value",
           filenames=("stw.nt", "stw.rdf")),
    Source("gnd", "Gemeinsame Normdatei subjects (DNB)", "de", "GND RDF/XML",
           load_gnd, "https://data.dnb.de/opendata/authorities-gnd-sachbegriff_lds.rdf.gz",
           "~207000 subject terms; GND element set (gndo:), not SKOS — uses the "
           "gnd.py adapter. Download authorities-gnd-sachbegriff_lds.rdf.gz, gunzip",
           filenames=("gnd-sachbegriff.rdf", "gnd.rdf")),
    Source("germanet", "GermaNet (German WordNet)", "de", "GermaNet XML",
           load_germanet, "https://uni-tuebingen.de/en/142806",
           "academic licence required; pairs with VerbNet typing in semdrill",
           filenames=("GN_V_XML", "germanet")),
]}


def _input_path(src: Source) -> Optional[str]:
    """First existing input file/dir for a source under vocab/sources/<scheme>/."""
    base = os.path.join(SOURCE_DIR, src.scheme)
    for name in src.filenames:
        cand = os.path.join(base, name)
        if os.path.exists(cand):
            return cand
    return None


def build(scheme: str, path: Optional[str] = None,
          out_dir: str = COMPILED_DIR) -> str:
    src = SOURCES.get(scheme)
    if not src:
        raise SystemExit(f"unknown scheme {scheme!r}; known: {', '.join(SOURCES)}")
    if path is None:
        path = _input_path(src)
        if path is None:
            raise SystemExit(
                f"no input for {scheme!r} under {os.path.join(SOURCE_DIR, scheme)}/ "
                f"-- see its STUB.md (download from {src.url})")
    vocab = src.adapter(path, scheme=scheme, lang=src.lang, meta={"title": src.title})
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{scheme}.json")
    vocab.save(out)
    print(f"{scheme}: {vocab}  ->  {out}")
    return out


def build_all(out_dir: str = COMPILED_DIR) -> List[str]:
    """Build every source whose input file is present; skip (note) the rest."""
    built: List[str] = []
    for scheme, src in SOURCES.items():
        if _input_path(src) is None:
            print(f"{scheme}: no input present -- skipped (see vocab/sources/{scheme}/STUB.md)")
            continue
        built.append(build(scheme, out_dir=out_dir))
    return built


def _list() -> None:
    print(f"{'scheme':<12} {'lang':<4} {'format':<18} {'input':<8} title")
    print("-" * 90)
    for s in SOURCES.values():
        present = "present" if _input_path(s) else "missing"
        print(f"{s.scheme:<12} {s.lang:<4} {s.fmt:<18} {present:<8} {s.title}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "list":
        _list()
    elif len(sys.argv) >= 3 and sys.argv[1] == "build" and sys.argv[2] == "all":
        build_all()
    elif len(sys.argv) >= 3 and sys.argv[1] == "build":
        build(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    else:
        print(__doc__)
        print("\nQuick start:\n  python3 -m vocabnet.sources list")
