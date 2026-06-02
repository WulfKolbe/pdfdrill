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
# A numbered-bibliography entry starts with "[N] " or "N. " / "N) ".
_REF_START = re.compile(r"^\s*(?:\[\d{1,3}\]|\d{1,3}[.)])\s+\S")


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
        # A line starting with a reference marker ([N]/N.) begins a new entry
        # (numbered bibliographies, where the year sits mid-line).
        if cur and _REF_START.match(t):
            entries.append(cur)
            cur = []
        cur.append((a, t))
        # A line ending with a year/page range closes an entry (author-year
        # bibliographies with a hanging last line).
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
        # The reference number: a leading [N]/N. if printed, else sequential
        # position (numeric in-text citations [N] resolve against this).
        lead = re.match(r"\s*\[?(\d{1,3})\]?[.\)]?\s", text)
        number = int(lead.group(1)) if lead else idx + 1
        out.append({
            "raw_text": text,
            "year": year,
            "author": author,
            "citekey": key,
            "number": number,
            "anchors": [a for a, _ in ent],
        })
    return out


_NUMCITE = re.compile(r"\[(\d[\d,\s\-–]*)\]")


def _expand_numlist(s: str) -> list[int]:
    """`1,3-5` -> [1,3,4,5]."""
    nums: list[int] = []
    for part in re.split(r"[,;]", s):
        part = part.strip()
        m = re.match(r"(\d+)\s*[-–]\s*(\d+)$", part)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if hi - lo <= 50:              # guard against absurd ranges
                nums.extend(range(lo, hi + 1))
        elif part.isdigit():
            nums.append(int(part))
    return nums


def detect_numeric_citations(doc, max_num: int, exclude_anchors=()) -> int:
    """Detect in-text numeric citations [N], [N,M], [N-M] and add Citations.

    Only brackets whose numbers all fall in 1..max_num are accepted (filters
    intervals like [0,1] and out-of-range brackets). `exclude_anchors` skips
    the bibliography's own lines. Returns the number of Citations added.
    """
    from docmodel.core import DocObject, Realization

    mp = doc.streams.get("mathpix_lines")
    if mp is None or max_num <= 0:
        return 0
    exclude = set(exclude_anchors)
    added = 0
    for anchor in mp.anchors:
        if anchor in exclude:
            continue
        p = mp.payload[anchor]
        if p.get("type") not in ("text", "title"):
            continue
        text = p.get("text_display") or p.get("text") or ""
        for m in _NUMCITE.finditer(text):
            nums = [x for x in _expand_numlist(m.group(1)) if 1 <= x <= max_num]
            if not nums:
                continue
            for num in nums:
                obj = DocObject(type="Citation", props={
                    "citekey": str(num), "number": num, "numeric": True,
                    "added_by": "bibliography", "page": p.get("_page")})
                obj.add_realization(Realization(
                    stream="mathpix_lines", start=anchor, end=anchor,
                    role="surface",
                    props={"offset": m.start(), "length": m.end() - m.start()}))
                doc.add(obj)
                added += 1
    return added


_PAREN = re.compile(r"\(([^()]{1,250})\)")
_AY_STOP = {
    "in", "the", "see", "eq", "fig", "figure", "table", "section", "appendix",
    "no", "yes", "note", "cf", "via", "and", "or", "of", "from", "with",
    "left", "right", "top", "bottom", "where", "for", "all", "e", "i",
}


def detect_author_year_citations(doc, exclude_anchors=()) -> int:
    """Detect parenthetical author-year citations and add Citations.

    Matches `(Author ..., YEAR)` groups (split on `;` for multi-cites),
    extracting the leading surname + year into a `surname+year` citekey — the
    same shape `parse_bibliography` generates for references, so
    `link_citations` matches them. Returns the number of Citations added.
    """
    from docmodel.core import DocObject, Realization

    mp = doc.streams.get("mathpix_lines")
    if mp is None:
        return 0
    exclude = set(exclude_anchors)
    added = 0
    for anchor in mp.anchors:
        if anchor in exclude:
            continue
        p = mp.payload[anchor]
        if p.get("type") not in ("text", "title"):
            continue
        text = p.get("text_display") or p.get("text") or ""
        for m in _PAREN.finditer(text):
            content = m.group(1)
            if not _YEAR.search(content):
                continue
            off, length = m.start(), m.end() - m.start()
            for part in content.split(";"):
                ym = _YEAR.search(part)
                if not ym:
                    continue
                sm = re.search(r"\b([A-Z][A-Za-z\-']{1,})", part)
                if not sm:
                    continue
                surname = sm.group(1)
                if surname.lower() in _AY_STOP:
                    continue
                obj = DocObject(type="Citation", props={
                    "citekey": f"{surname}{ym.group(0)}", "author": surname,
                    "year": ym.group(0), "style": "author-year",
                    "added_by": "bibliography", "page": p.get("_page")})
                obj.add_realization(Realization(
                    stream="mathpix_lines", start=anchor, end=anchor,
                    role="surface", props={"offset": off, "length": length}))
                doc.add(obj)
                added += 1
    return added


def link_citations(doc) -> int:
    """Add `cites` Alignments from in-text Citations to their Reference.

    Matches a citation's key to a reference citekey exactly, or by surname
    prefix (in-text `[Asai]` -> reference `Asai2023`). Returns edges added.
    """
    from docmodel.core import Range, Alignment

    by_key = {}
    by_number = {}
    for r in doc.objects.values():
        if r.type == "Reference":
            ck = (r.props.get("citekey") or "").lower()
            if ck:
                by_key[ck] = r
            num = r.props.get("number")
            if num is not None:
                by_number[num] = r

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
        num = c.props.get("number")
        r = by_number.get(num) if num is not None else find_ref(c.props.get("citekey") or "")
        if r is None:
            continue
        ls, rs = surface(c), surface(r)
        if ls and rs:
            doc.add_alignment(Alignment(kind="cites", left=ls, right=rs,
                                        props={"citekey": r.props.get("citekey"),
                                               "number": num}))
            n += 1
    return n


def _split_bib_entries(text: str) -> list[tuple[str, str]]:
    """Brace-aware split of a .bib file into (citekey, raw_entry) pairs."""
    entries: list[tuple[str, str]] = []
    i, n = 0, len(text)
    while True:
        at = text.find("@", i)
        if at < 0:
            break
        km = re.match(r"@\w+\s*\{\s*([^,\s]+)", text[at:])
        brace = text.find("{", at)
        if brace < 0 or km is None:
            i = at + 1
            continue
        depth, j = 0, brace
        while j < n:
            c = text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        entries.append((km.group(1).strip(), text[at:j + 1]))
        i = j + 1
    return entries


def load_bibtex_file(doc, bibtext: str) -> dict:
    """Attach BibTeX from a .bib file to References (by citekey), creating a
    Reference for any entry not already present. Returns {attached, created}."""
    from docmodel.core import DocObject
    from .perplexity_client import parse_bibtex_fields

    refs = {(r.props.get("citekey") or ""): r
            for r in doc.objects.values() if r.type == "Reference"}
    attached = created = 0
    for key, raw in _split_bib_entries(bibtext):
        f = parse_bibtex_fields(raw)
        r = refs.get(key)
        if r is None:
            r = DocObject(type="Reference", props={
                "citekey": key, "raw_text": f.get("title") or "",
                "year": f.get("year") or "", "author": f.get("author") or "",
                "entry_type": f.get("entry_type") or "misc"})
            doc.add(r)
            refs[key] = r
            created += 1
        r.props["bibtex"] = raw
        for k in ("author", "year", "title", "entry_type"):
            if f.get(k):
                r.props[k] = f[k]
        attached += 1
    return {"attached": attached, "created": created}


# ---------------------------------------------------------------------------
# Gold bibliography ingest from the author's compiled .bbl (+ .bib)
# ---------------------------------------------------------------------------

_BIBITEM = re.compile(
    r"\\bibitem(?:\[(?P<label>[^\]]*)\])?\s*\{(?P<key>[^}]+)\}"
    r"(?P<body>.*?)(?=\\bibitem|\\end\{thebibliography\}|\Z)",
    re.DOTALL)
_NEWBLOCK = re.compile(r"\\newblock\s*")
_URL = re.compile(r"\\url\s*\{([^}]*)\}")
_EM = re.compile(r"\{\\(?:em|it|bf)\s+([^{}]*)\}")
_TEXCMD = re.compile(r"\\[a-zA-Z]+\b")


def _clean_bbl(body: str) -> str:
    """Light-clean a \\bibitem body to readable prose."""
    t = _NEWBLOCK.sub(" ", body)
    t = _URL.sub(r"\1", t)
    t = _EM.sub(r"\1", t)
    t = t.replace("~", " ")
    t = _TEXCMD.sub("", t)
    t = t.replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", t).strip()


def _norm_label(s: str) -> str:
    """Normalize an alpha citation label for OCR-tolerant matching.

    MathPix reads `ASV02` as `ASVo2`, `NC00` as `NCoo`; map the confusable
    glyphs (o->0, l->1) after lowercasing + stripping non-alphanumerics.
    """
    s = re.sub(r"[^A-Za-z0-9]", "", (s or "").lower())
    return s.replace("o", "0").replace("l", "1")


def parse_bbl(text: str) -> list[dict]:
    """Parse a compiled `.bbl` into [{label, citekey, text, number}]."""
    out = []
    for i, m in enumerate(_BIBITEM.finditer(text)):
        out.append({
            "label": (m.group("label") or "").strip(),
            "citekey": m.group("key").strip(),
            "text": _clean_bbl(m.group("body")),
            "number": i + 1,
        })
    return out


def ingest_bbl(doc, bbltext: str) -> int:
    """Create a `Reference` per `\\bibitem` (citekey + alpha label + printed
    text), each addressable via a `references` stream anchor. Returns count."""
    from docmodel.core import DocObject, Realization

    stream = doc.ensure_stream("references")
    n = 0
    for e in parse_bbl(bbltext):
        anchor = stream.append(citekey=e["citekey"], label=e["label"],
                               number=e["number"])
        obj = DocObject(type="Reference", props={
            "citekey": e["citekey"], "label": e["label"], "number": e["number"],
            "raw_text": e["text"], "entry_type": "misc"})
        obj.add_realization(Realization(stream="references", start=anchor,
                                        end=anchor, role="surface",
                                        provenance="bbl"))
        doc.add(obj)
        n += 1
    return n


def _ref_range(o):
    from docmodel.core import Range
    for st in ("references", "mathpix_lines"):
        r = next((x for x in o.realizations
                  if x.stream == st and x.start is not None), None)
        if r:
            return Range(st, r.start, r.end)
    return None


def link_citations_by_label(doc) -> int:
    """Link in-text Citations to References by alpha LABEL (OCR-tolerant).

    The thesis's printed citations are alpha labels (`[ASV02]`); MathPix OCRs
    them as the Citation citekey. Match each to the `.bbl` Reference whose label
    normalizes equally, adding a `cites` Alignment. Returns edges added.
    """
    from docmodel.core import Alignment

    by_label = {}
    for r in doc.objects.values():
        if r.type == "Reference":
            lab = _norm_label(r.props.get("label") or "")
            if lab:
                by_label[lab] = r

    n = 0
    for c in doc.objects.values():
        if c.type != "Citation":
            continue
        r = by_label.get(_norm_label(c.props.get("citekey") or ""))
        if r is None:
            continue
        ls, rs = _ref_range(c), _ref_range(r)
        if ls and rs:
            doc.add_alignment(Alignment(kind="cites", left=ls, right=rs, props={
                "citekey": r.props.get("citekey"), "label": r.props.get("label")}))
            c.props["cited_reference_id"] = r.id
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
            "number": e.get("number"),
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
