"""
Bibliography parsing — segment the References section into entries and lift
each into a `Reference` DocObject.

The references in OCR output are unstructured multi-line text (no [key]), so
this is a heuristic first cut, not a full BibTeX parser: entries are segmented
on a line that ends with a year or a page range, and we extract the year, an
author block, and a generated citekey (surname+year). Full structured BibTeX
fields (title/journal/volume) await a real grammar (ANTLR/comby) — that
backend slots in by enriching the `Reference` props without changing callers.

Each Reference keeps its `raw_text` so the TiddlyWiki tiddler can show the
original entry with a `{{||CIT}}` self-reference in front.
"""
from __future__ import annotations

import re

_HEAD = re.compile(r"^(references?|bibliography)\s*$", re.I)
_YEAR = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b")
# An entry typically ends with "..., 2023." or a page range "13-22."
_ENTRY_END = re.compile(r"(?:(?:19|20)\d{2}[a-z]?|\d{1,4}\s*[-–]\s*\d{1,4})\.?\s*$")


def _author_block(text: str) -> str:
    m = _YEAR.search(text)
    head = text[:m.start()] if m else text[:80]
    return head.strip(" .,;")


def _citekey(author: str, year: str, idx: int) -> str:
    first = re.split(r";| and ", author)[0].strip() if author else ""
    if "," in first:                      # "Aletras, N." -> Aletras
        surname = first.split(",")[0].strip().split()[-1:] or [""]
        surname = surname[0]
    else:                                  # "Akari Asai" -> Asai
        words = [w for w in first.split() if w.isalpha()]
        surname = words[-1] if words else ""
    surname = re.sub(r"[^A-Za-z]", "", surname)
    if surname and year:
        return f"{surname}{year}"
    if surname:
        return f"{surname}{idx + 1}"
    return f"ref{idx + 1}"


def parse_bibliography(doc) -> list[dict]:
    """Return [{raw_text, year, author, citekey, anchors}] for each entry."""
    mp = doc.streams.get("mathpix_lines")
    if mp is None:
        return []
    anchors = mp.anchors

    start = None
    for i, a in enumerate(anchors):
        t = (mp.payload[a].get("text") or "").strip()
        if _HEAD.match(t):
            start = i + 1
            break
    if start is None:
        return []

    body = []
    for a in anchors[start:]:
        p = mp.payload[a]
        if p.get("type") == "section_header":
            break                          # next section ends the bibliography
        t = (p.get("text") or p.get("text_display") or "").strip()
        if t:
            body.append((a, t))

    entries: list[list] = []
    cur: list = []
    for a, t in body:
        cur.append((a, t))
        if _ENTRY_END.search(t):
            entries.append(cur)
            cur = []
    if cur:
        entries.append(cur)

    out = []
    seen: dict[str, int] = {}
    for idx, ent in enumerate(entries):
        text = " ".join(t for _, t in ent)
        ym = _YEAR.search(text)
        year = ym.group(0) if ym else ""
        author = _author_block(text)
        key = _citekey(author, year, idx)
        if key in seen:                    # disambiguate duplicate keys
            seen[key] += 1
            key = f"{key}{chr(ord('a') + seen[key])}"
        else:
            seen[key] = 0
        out.append({
            "raw_text": text,
            "year": year,
            "author": author,
            "citekey": key,
            "anchors": [a for a, _ in ent],
        })
    return out


def link_citations(doc) -> int:
    """Add `cites` Alignments from in-text Citations to their Reference.

    Matches a citation's key to a reference citekey exactly, or by surname
    prefix (in-text `[Asai]` -> reference `Asai2023`). Returns edges added.
    """
    from docmodel.core import Range, Alignment

    by_key = {}
    for r in doc.objects.values():
        if r.type == "Reference":
            ck = (r.props.get("citekey") or "").lower()
            if ck:
                by_key[ck] = r

    def find_ref(citekey: str):
        c = (citekey or "").lower().strip()
        if not c:
            return None
        if c in by_key:
            return by_key[c]
        for ck, r in by_key.items():
            if len(c) >= 3 and ck.startswith(c):
                return r
        return None

    def surface(o):
        rr = next((x for x in o.realizations
                   if x.stream == "mathpix_lines" and x.start is not None), None)
        return Range("mathpix_lines", rr.start, rr.end) if rr else None

    n = 0
    for c in doc.objects.values():
        if c.type != "Citation":
            continue
        r = find_ref(c.props.get("citekey") or "")
        if r is None:
            continue
        ls, rs = surface(c), surface(r)
        if ls and rs:
            doc.add_alignment(Alignment(kind="cites", left=ls, right=rs,
                                        props={"citekey": r.props.get("citekey")}))
            n += 1
    return n


def add_reference_objects(doc, entries: list[dict]) -> int:
    """Create a `Reference` DocObject per parsed entry. Returns the count."""
    from docmodel.core import DocObject, Realization

    n = 0
    for e in entries:
        obj = DocObject(type="Reference", props={
            "citekey": e["citekey"],
            "raw_text": e["raw_text"],
            "year": e["year"],
            "author": e["author"],
            "entry_type": "misc",          # heuristic; refined by a real grammar
        })
        anchors = e.get("anchors") or []
        if anchors:
            obj.add_realization(Realization(
                stream="mathpix_lines", start=anchors[0], end=anchors[-1],
                role="surface", provenance="bibliography"))
        doc.add(obj)
        n += 1
    return n
