#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
msc_html.py -- build the MSC vocabulary from a CRAN/AMS-style MSC listing HTML.

The clean machine-readable MSC2020 is behind Cloudflare/T&C at zbMATH, but the
CRAN classification mirror publishes the full MSC-2010 listing as HTML, one
`CODE  Title [See also …]` per line. MSC-2010 is structurally compatible with
MSC2020 for classification (the section structure and the physics-relevant
branches — 35Q PDEs of mathematical physics, 81 Quantum theory, 82 Statistical
mechanics, 83 Relativity & gravitation — are stable), and it is CC-BY-NC-SA.

`parse_cran_msc(html)` returns the SAME `{ "codes": { code: {title, parent,
children} } }` shape that `mscc.py`/`sources.msc_from_json` consumes, deriving
the hierarchy from the code prefix:

    81T13  ->  parent 81Txx  ->  parent 81-XX  ->  root
    35Q55  ->  parent 35Qxx  ->  parent 35-XX  ->  root

So no explicit parent edges are needed in the source. `[See also …]` and other
bracketed cross-references are stripped from titles; UTF-8 mojibake (a
double-encoded "Schrödinger") is repaired.

Pure standard library.
"""

from __future__ import annotations

import html as _html
import re
from typing import Dict, Optional

from .vocab import Concept, Vocabulary

# a definitional MSC code at the start of a line:
#   NN-XX (section), NN-NN (e.g. 81-00), NNLxx (subsection), NNLNN (5-char)
_CODE = re.compile(r"^([0-9]{2}(?:-XX|-[0-9]{2}|[A-Za-z]xx|[A-Za-z][0-9]{2}))\b(.*)$")
_TAG = re.compile(r"<[^>]+>")
_BRACKET = re.compile(r"\[[^\[\]]*\]")          # [See also …] cross-references
_BRACE = re.compile(r"\{[^{}]*\}")              # {For …: see …} notes


def _fix_mojibake(s: str) -> str:
    if "Ã" in s or "â€" in s:
        try:
            return s.encode("latin-1", "ignore").decode("utf-8", "ignore")
        except Exception:
            return s
    return s


def _parent(code: str) -> Optional[str]:
    m = re.match(r"^([0-9]{2})([A-Za-z])[0-9]{2}$", code)      # 81P05 -> 81Pxx
    if m:
        return f"{m.group(1)}{m.group(2)}xx"
    m = re.match(r"^([0-9]{2})[A-Za-z]xx$", code)              # 81Pxx -> 81-XX
    if m:
        return f"{m.group(1)}-XX"
    m = re.match(r"^([0-9]{2})-[0-9]{2}$", code)               # 81-00 -> 81-XX
    if m:
        return f"{m.group(1)}-XX"
    return None                                                # NN-XX is a root


# MSC instructional boilerplate inside parentheses — noise for classification,
# but keep meaningful parentheticals like "(nonlinear Schrödinger)".
_BOILER = re.compile(
    r"\(\s*(?:should|must|may)\s+(?:also\s+)?be\s+assigned[^)]*\)?"
    r"|\(\s*(?:see|cf\.?|for)\b[^)]*\)",
    re.I)
# the SAME instruction also appears WITHOUT parentheses, after a period, e.g.
# "… electromagnetic theory. Must also be assigned at least one other
# classification number in this section" — cut it (and anything after) entirely.
_BOILER_TAIL = re.compile(
    r"[.;,]?\s*(?:should|must|may)\s+(?:also\s+)?be\s+assigned.*$", re.I | re.S)
# the applied-statistics 62Exx codes carry "… in connection with the topics on
# distributions in this section" — strip that tail (but keep meaningful
# "in connection with <topic>" like "PDEs in connection with quantum mechanics").
_BOILER_TOPICS = re.compile(
    r"\s*in connection with the topics on\b.*$|\s*in this section\b.*$", re.I | re.S)


def _clean_title(s: str) -> str:
    s = _html.unescape(s)
    s = _fix_mojibake(s)
    s = _BOILER.sub("", s)
    s = _BOILER_TAIL.sub("", s)
    s = _BOILER_TOPICS.sub("", s)
    prev = None
    while prev != s:                                           # nested brackets
        prev = s
        s = _BRACKET.sub("", s)
        s = _BRACE.sub("", s)
    # a line-wrapped cross-ref leaves an unclosed trailing bracket/brace
    s = re.sub(r"[\[{]\s*(?:See|For|Cf)\b.*$", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip(" .;:")


def parse_cran_msc(html: str) -> Dict[str, dict]:
    """CRAN/AMS MSC listing HTML -> {"codes": {code: {title, parent, children}}}."""
    text = _html.unescape(html)
    # turn tags into line breaks so each table cell/row becomes its own line
    text = _TAG.sub("\n", text)
    lines = [ln.strip() for ln in text.splitlines()]
    codes: Dict[str, dict] = {}
    for i, line in enumerate(lines):
        m = _CODE.match(line)
        if not m:
            continue
        code = m.group(1)
        title = _clean_title(m.group(2))
        if not title:
            # split-cell layout: the title sits on the next non-code line
            for nxt in lines[i + 1:i + 4]:
                if nxt and not _CODE.match(nxt):
                    title = _clean_title(nxt)
                    break
        if not title:
            continue
        # first definition wins (the listing defines each code once)
        codes.setdefault(code, {"title": title, "parent": _parent(code),
                                "children": []})
    # wire children from the derived parents
    for code, node in codes.items():
        p = node["parent"]
        if p and p in codes and code not in codes[p]["children"]:
            codes[p]["children"].append(code)
    return {"codes": codes}


def load_msc_html(path: str, scheme: str = "msc", lang: str = "en",
                  meta: Optional[dict] = None) -> Vocabulary:
    with open(path, "rb") as fh:
        raw = fh.read()
    html = raw.decode("utf-8", "replace")
    blob = parse_cran_msc(html)
    concepts = [Concept(code=c, pref=n["title"], labels={lang: [n["title"]]},
                        parent=n["parent"], children=list(n["children"]))
                for c, n in blob["codes"].items()]
    m = {"lang": lang, "format": "msc-html", "source": "cran-msc-2010"}
    m.update(meta or {})
    return Vocabulary.compile(scheme, concepts, meta=m)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        print(load_msc_html(sys.argv[1]))
