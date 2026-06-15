#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dlmf.py -- ingest the NIST Digital Library of Mathematical Functions into a
Vocabulary from its **MathPix Markdown** rendering (the only PDF-route source in
the set: DLMF front-matter / chapter PDF -> pdfdrill -> MathPix MD).

DLMF is numbered hierarchically (Chapter 5, Section 5.2, subsection 5.2.1), and
MathPix preserves that numbering in ATX headings. So the concept code is the
**leading dotted section number** of each heading and the hierarchy follows the
dotted prefix (parent of `5.2.1` is `5.2`, of `5.2` is `5`) -- independent of
the markdown `#` depth, which OCR can get wrong. The prose under a heading,
until the next heading, is folded in as an alt label so `classify` finds a
section by the function names that appear in its body.

Ends in one Vocabulary.compile(...), same as skos.py.

    from vocabnet.dlmf import load_dlmf
    v = load_dlmf("dlmf-front.md", scheme="dlmf", lang="en")

Pure standard library.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from .vocab import Concept, Vocabulary

# ATX heading: 1..6 '#' then the title text.
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")

# Leading section number on a heading, with optional Chapter/Section/Part word:
#   "Chapter 1 Algebraic ..."  -> ("1", "Algebraic ...")
#   "5.2 Definitions"          -> ("5.2", "Definitions")
#   "1.2(i) Notation"          -> ("1.2", "(i) Notation")   [roman subpart kept in title]
_NUMBERED = re.compile(
    r"^(?:Chapter|Chap\.|Section|Sect\.|Part|§)?\s*"
    r"(\d+(?:\.\d+)*)\b[.:)]?\s*(.*)$",
    re.IGNORECASE,
)


def _parse_headings(text: str) -> List[tuple]:
    """Return [(code, title, body_text), ...] for every numbered ATX heading,
    in document order. Body = prose between this heading and the next heading."""
    lines = text.splitlines()
    heads: List[tuple] = []          # (line_index, code, title)
    for i, line in enumerate(lines):
        m = _HEADING.match(line)
        if not m:
            continue
        title_raw = m.group(2).strip()
        nm = _NUMBERED.match(title_raw)
        if not nm:
            continue                  # an unnumbered heading is prose, not a concept
        code = nm.group(1)
        title = nm.group(2).strip() or title_raw
        heads.append((i, code, title))

    out: List[tuple] = []
    for j, (li, code, title) in enumerate(heads):
        end = heads[j + 1][0] if j + 1 < len(heads) else len(lines)
        body_lines = [lines[k] for k in range(li + 1, end)
                      if not _HEADING.match(lines[k])]
        body = re.sub(r"\s+", " ", " ".join(body_lines)).strip()
        out.append((code, title, body))
    return out


def load_dlmf(path: str, scheme: str = "dlmf", lang: str = "en",
              meta: Optional[dict] = None) -> Vocabulary:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return build_dlmf(text, scheme=scheme, lang=lang, meta=meta)


def build_dlmf(text: str, scheme: str = "dlmf", lang: str = "en",
               meta: Optional[dict] = None) -> Vocabulary:
    """Pure: MathPix-Markdown string -> Vocabulary (unit-testable without a file)."""
    concepts: Dict[str, Concept] = {}
    for code, title, body in _parse_headings(text):
        labels: Dict[str, List[str]] = {lang: [title]}
        if body:
            # fold body prose in as an alt label so classify matches the function
            # names in a section (weight 0.7 in surface_forms, below the title).
            labels[lang].append(body)
        parent = code.rsplit(".", 1)[0] if "." in code else None
        c = concepts.get(code)
        if c is None:
            concepts[code] = Concept(code=code, pref=title, labels=labels,
                                     parent=parent, definition=body)
        else:                          # duplicate numbering (rare OCR artifact): merge
            for x in labels[lang]:
                if x not in c.labels.setdefault(lang, []):
                    c.labels[lang].append(x)
            if body and not c.definition:
                c.definition = body

    # wire children from the dotted-prefix parent links
    for code, c in concepts.items():
        if c.parent and c.parent in concepts:
            p = concepts[c.parent]
            if code not in p.children:
                p.children.append(code)
        elif c.parent and c.parent not in concepts:
            c.parent = None            # parent heading absent (partial extract)

    m = {"lang": lang, "format": "dlmf-md", "source": "mathpix-markdown"}
    m.update(meta or {})
    return Vocabulary.compile(scheme, concepts.values(), meta=m)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2:
        print(load_dlmf(sys.argv[1]))
