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


def drop_dangling_cites(doc) -> None:
    """010 — remove `cites` Alignments that no longer connect two live objects.

    A `cites` edge is dropped when EITHER side dangles (010 fix round 5).
    Pruning by the RIGHT side alone left an edge whose CITATION had just been
    retracted -- `cmd_bibliography --force` drops every `added_by ==
    "bibliography"` Citation before re-detecting, and Ranges are not wired to
    object ids, so removing the object leaves its edges behind. The model then
    carried an edge from nothing to a Reference and the edge count outran the
    Citation count.

    An edge that still connects two live objects survives untouched -- most
    often to a citation-stub Reference (010), which keeps its id and anchor
    when a creator below fills it, so its Citation stays linked across the
    rebuild instead of losing the edge and waiting for a relink pass that may
    not run.

    Two edge shapes share the kind name and both are honoured: the model-build
    Citation -> Reference edge, and `annotations.link_xref_alignments`' Link ->
    Citation edge (left on the `links` stream). Deciding by range alone cannot
    tell them apart -- a stub Reference is anchored at its citation's own line,
    so the two sides of a Citation -> Reference edge can be the SAME range.
    """
    def ranges(t):
        return {(r.stream, r.start, r.end)
                for o in doc.objects.values() if o.type == t
                for r in o.realizations}

    refs, cits, links = ranges("Reference"), ranges("Citation"), ranges("Link")

    def alive(a):
        left = (a.left.stream, a.left.start, a.left.end)
        right = (a.right.stream, a.right.start, a.right.end)
        if a.left.stream == "links":            # annotate's Link -> Citation
            return left in links and right in cits
        return left in cits and right in refs   # model-build Citation -> Reference

    doc.alignments = [a for a in doc.alignments
                      if a.kind != "cites" or alive(a)]


def drop_ownerless_stubs(doc) -> int:
    """639 — one-time upgrade rule for the OPEN caveat in tasks/010.report.md:
    a stub Reference built between db66ff0 and daf1657 (010 fix round 3,
    which is what started stamping `added_by` onto a NEW stub from its
    creating citation) carries no `added_by` of its own. `cmd_bibliography
    --force`'s provenance-based cleanup (retract `added_by == "bibliography"`)
    never touches such a stub, even after every Citation that cited it is
    gone — and left behind, its anchor (a citation's own PROSE line, not a
    bibliography-section line) permanently excludes that line from
    `ref_anchors`, so `--force` can never re-detect the citation that used to
    live there again. Measured on penev_A's round-2 snapshot: stable at 26
    Citations/52 References forever instead of climbing back to 81/52.

    A stub with no `added_by` AND no `cites` Alignment whose CITING (left)
    side still resolves to a LIVE Citation object is exactly such a leftover
    -- it is retracted here too, freeing its line for re-detection. Checking
    the alignment's own existence is not enough: `drop_dangling_cites` above
    only prunes by the Alignment's RIGHT (Reference) side, so a `cites` edge
    whose Reference still exists (this stub) survives even after its
    Citation is popped from `doc.objects` -- Ranges aren't wired to object
    ids, so removing an object doesn't retract its alignments. A document
    built entirely under the current code never matches this rule (every
    stub it makes carries `added_by` from the moment of creation), so it
    only ever fires on legacy, pre-migration data.

    Returns the number of stubs dropped."""
    live_citations = {
        (r.stream, r.start, r.end)
        for o in doc.objects.values() if o.type == "Citation"
        for r in o.realizations
    }
    still_cited = {
        (a.right.stream, a.right.start, a.right.end)
        for a in doc.alignments
        if a.kind == "cites"
        and (a.left.stream, a.left.start, a.left.end) in live_citations
    }
    to_drop = [
        o.id for o in doc.objects.values()
        if o.type == "Reference" and o.props.get("stub") and not o.props.get("added_by")
        and not any((r.stream, r.start, r.end) in still_cited for r in o.realizations)
    ]
    for oid in to_drop:
        doc.objects.pop(oid, None)
    return len(to_drop)


def has_filled_references(doc) -> bool:
    """010 fix round 4 — "are there References yet?" must mean FILLED ones.

    Since 010 every cited key gets a stub Reference at model-build time, so
    `any(o.type == "Reference")` is permanently TRUE and three gates that used
    it stopped firing: `_auto_bibliography` (a projection that needs References
    never built them), the same gate in `cmd_tiddlers`, and `CitationPass`
    (which then never discovered the source bib). A stub is a placeholder for
    a Reference, not one; only a non-stub Reference means the bibliography has
    actually been built.
    """
    return any(o.type == "Reference" and not o.props.get("stub")
               for o in doc.objects.values())


def filled_cites_edges(doc) -> int:
    """`cites` Alignments whose target is a FILLED (non-stub) Reference.

    `CitationPass`'s "already linked, nothing to do" short-circuit counted
    every `cites` edge, and after 010 a stub-only document has one per
    Citation -- so it reported "already linked" on a document with no
    bibliography at all."""
    live = {(r.stream, r.start, r.end)
            for o in doc.objects.values()
            if o.type == "Reference" and not o.props.get("stub")
            for r in o.realizations if r.start is not None}
    return sum(1 for a in doc.alignments if a.kind == "cites"
               and (a.right.stream, a.right.start, a.right.end) in live)


def bibliography_section_anchors(doc) -> set:
    """The `mathpix_lines` anchors where the References SECTION itself lives.

    010 fix round 5. `cmd_bibliography` excludes these from citation
    re-detection so a bibliography entry is not read as an in-text citation.
    It used to take EVERY Reference realization on `mathpix_lines` -- but
    since 010 a Reference may be a stub anchored at a citation's own PROSE
    line, and round 4 (correctly) keeps such a Reference once bibsource or
    bibfetch has filled it. Excluding that line meant the Citation retracted
    by `--force` was never re-detected: force#1 found [Asai2023, Wu2024],
    force#2 found [Wu2024]. Only a realization the References-section parser
    placed (role/provenance "bibliography") counts.
    """
    return {r.start for o in doc.objects.values() if o.type == "Reference"
            for r in o.realizations
            if r.stream == "mathpix_lines" and r.start
            and (r.role == "bibliography" or r.provenance == "bibliography")}


def stub_for(doc, citekey: str):
    """The citation-stub Reference for `citekey`, if one is still around."""
    ck = (citekey or "").strip()
    if not ck:
        return None
    return next((r for r in doc.objects.values()
                 if r.type == "Reference" and r.props.get("stub")
                 and (r.props.get("citekey") or "") == ck), None)


# The bibliography-section heading WORD (matched on a normalized line, so a
# \section*{}/markdown/numbered wrapper is stripped first — see _is_ref_heading).
_HEAD = re.compile(
    r"^(references?|bibliography|references?\s+and\s+notes|literature\s+cited|"
    r"works?\s+cited|reference\s+list|"
    r"bibliographie|literatur(?:verzeichnis)?|quellenverzeichnis)$", re.I)


def _norm_heading(t: str) -> str:
    """Strip LaTeX/markdown/section-number wrappers so a heading like
    `\\section*{7 References}` or `**References**` or `REFERENCES:` normalizes to
    the bare word — the 0-references failure was MathPix headings the bare
    `^references$` regex never matched."""
    t = re.sub(r"\\(?:sub){0,2}section\*?\s*\{([^}]*)\}", r"\1", t)  # \section*{X}
    t = re.sub(r"\\[A-Za-z]+\*?\s*", " ", t)        # any other leading \cmd
    t = t.replace("{", " ").replace("}", " ")
    t = re.sub(r"^[#>*_\s]+", "", t)                # markdown #, >, **, _
    t = re.sub(r"[*_\s]+$", "", t)
    t = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", t)      # leading "7 " / "7.2. "
    return t.strip().strip(":.").strip()


def _is_ref_heading(t: str) -> bool:
    return bool(_HEAD.match(_norm_heading(t)))


_YEAR = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b")
# An entry typically ends with "..., 2023." or a page range "13-22."
_ENTRY_END = re.compile(r"(?:(?:19|20)\d{2}[a-z]?|\d{1,4}\s*[-–]\s*\d{1,4})\.?\s*$")
# A numbered-bibliography entry starts with "[N] " or "N. " / "N) ".
# A printed entry marker: [5] / [5]. / [5]) / 5. / 5) followed by the entry.
# The period after a bracketed number is the point: `[5]. Author` is a common
# publisher style, and demanding whitespace straight after `[N]` made every
# such entry invisible as a START — so it was glued onto its predecessor and
# only entries that happened to END in a year were ever separated. Measured on
# a real 10-reference paper: 5 entries recovered, 5 swallowed.
# `\d{1,3}` (not more) keeps a bracketed YEAR from reading as a marker.
_REF_START = re.compile(r"^\s*(?:\[\d{1,3}\][.)]?|\d{1,3}[.)])\s+\S")


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

    # Prefer the LAST matching heading (a paper may say "References" in its text
    # body before the actual section; the real list is the final one) — but only
    # among lines that CAN be a heading.
    #
    # A book prints the section title on every page of the section and MathPix
    # emits that as `page_info`. Such a running header is later than the real
    # heading BY CONSTRUCTION, so last-wins picked it every time and discarded
    # every entry before it: on a 174-page scanned book with 21 printed
    # references, exactly one survived. The table-of-contents rows name the
    # section too. Neither is where a bibliography begins.
    #
    # A real `section_header` wins outright when there is one; otherwise fall
    # back to any other line, because not every source types its headings.
    typed = None
    untyped = None
    for i, a in enumerate(anchors):
        p = mp.payload[a]
        typ = p.get("type") or ""
        if typ == "page_info" or typ.startswith("table_of_contents"):
            continue
        if not _is_ref_heading((p.get("text") or "").strip()):
            continue
        if typ == "section_header":
            typed = i + 1
        else:
            untyped = i + 1
    start = typed if typed is not None else untyped
    if start is None:
        return []

    body = []
    for a in anchors[start:]:
        p = mp.payload[a]
        if p.get("type") == "section_header":
            break                          # next section ends the bibliography
        typ = p.get("type") or ""
        if typ == "page_info" or typ.startswith("table_of_contents"):
            continue                       # a printed page number / running
                                           # header / TOC row is not a reference
                                           # (one became an entry whose whole
                                           # text was "68")
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

    # Fallback for unnumbered author-year bibliographies where the year sits
    # MID-line (no [N] marker, no trailing year/page-range) — the marker/end
    # logic above collapses them to a single blob. If most body lines carry a
    # year, MathPix rendered one reference per line: split per line.
    if len(entries) <= 1 and len(body) >= 3:
        yr = sum(1 for _, t in body if _YEAR.search(t))
        if yr >= 0.5 * len(body):
            entries = [[bt] for bt in body]

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

# Inline/display math spans — a `[1,2]`/`(…)` inside one is math, not a cite.
_MATH_SPAN = re.compile(
    r"\\\[[\s\S]*?\\\]|\$\$[\s\S]*?\$\$|\\\([\s\S]*?\\\)|\$(?:[^$\n]|\\\$)*?\$")


def _math_ranges(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _MATH_SPAN.finditer(text)]


def _in_math(pos: int, ranges: list[tuple[int, int]]) -> bool:
    return any(a <= pos < b for a, b in ranges)


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


def _numlist_spans(s: str, base: int) -> list[tuple[int, int, int]]:
    """`_expand_numlist` WITH POSITIONS: `(number, offset, length)`.

    645 fix round 1. Every key in `[1,3-5]` used to be given the span of the
    whole bracket, so the projector could not tell where one citation ended
    and the next began and had to replace the lot — deleting any text in
    between. Same split, same range guard, same `isdigit` test as
    `_expand_numlist`; the offsets are of the PART, so the numbers expanded
    out of a range share the range token's own span (which is the truth: `4`
    in `3-5` has no text of its own).
    """
    out: list[tuple[int, int, int]] = []
    for pm in re.finditer(r"[^,;]+", s):
        raw = pm.group(0)
        part = raw.strip()
        if not part:
            continue
        off = base + pm.start() + (len(raw) - len(raw.lstrip()))
        m = re.match(r"(\d+)\s*[-–]\s*(\d+)$", part)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            if hi - lo <= 50:              # guard against absurd ranges
                out.extend((n, off, len(part)) for n in range(lo, hi + 1))
        elif part.isdigit():
            out.append((int(part), off, len(part)))
    return out


def detect_numeric_citations(doc, max_num: int, exclude_anchors=()) -> int:
    """Detect in-text numeric citations [N], [N,M], [N-M] and add Citations.

    Only brackets whose numbers all fall in 1..max_num are accepted (filters
    intervals like [0,1] and out-of-range brackets). `exclude_anchors` skips
    the bibliography's own lines. Returns the number of Citations added.
    """
    from docmodel.core import DocObject, Realization
    from docmodel.modules.citation import ensure_reference_stub

    mp = doc.streams.get("mathpix_lines")
    if mp is None or max_num <= 0:
        return 0
    bibkey = doc.meta.get("bibkey") or ""
    exclude = set(exclude_anchors)
    added = 0
    for anchor in mp.anchors:
        if anchor in exclude:
            continue
        p = mp.payload[anchor]
        if p.get("type") not in ("text", "title"):
            continue
        text = p.get("text_display") or p.get("text") or ""
        math = _math_ranges(text)
        for m in _NUMCITE.finditer(text):
            if _in_math(m.start(), math):       # `[1,2]` inside math is not a cite
                continue
            # 645 — each key gets ITS OWN span inside the bracket, not the
            # span of the whole bracket. A shared span forces the projector to
            # replace the group as one blob and delete whatever sits between
            # the keys.
            nums = [(x, o, l) for x, o, l in _numlist_spans(m.group(1),
                                                            m.start() + 1)
                    if 1 <= x <= max_num]
            if not nums:
                continue
            for num, off, length in nums:
                obj = DocObject(type="Citation", props={
                    "citekey": str(num), "number": num, "numeric": True,
                    "added_by": "bibliography", "page": p.get("_page")})
                obj.add_realization(Realization(
                    stream="mathpix_lines", start=anchor, end=anchor,
                    role="surface",
                    props={"offset": off, "length": length}))
                doc.add(obj)
                ensure_reference_stub(doc, obj, bibkey)   # 010
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
    from docmodel.modules.citation import ensure_reference_stub

    mp = doc.streams.get("mathpix_lines")
    if mp is None:
        return 0
    bibkey = doc.meta.get("bibkey") or ""
    exclude = set(exclude_anchors)
    added = 0
    for anchor in mp.anchors:
        if anchor in exclude:
            continue
        p = mp.payload[anchor]
        if p.get("type") not in ("text", "title"):
            continue
        text = p.get("text_display") or p.get("text") or ""
        math = _math_ranges(text)
        for m in _PAREN.finditer(text):
            if _in_math(m.start(), math):       # `(…)` inside math is not a cite
                continue
            content = m.group(1)
            if not _YEAR.search(content):
                continue
            # 645 — the span is the PART's own `Surname … year` extent, not the
            # whole parenthetical. `(Linsker 1988; Oja 1989; Földiák 1990)` is
            # three positions, and a shared span made the projector replace the
            # lot — deleting `Földiák 1990`, which no detector recognises.
            base, cursor = m.start() + 1, 0
            for part in content.split(";"):
                part_base, cursor = base + cursor, cursor + len(part) + 1
                ym = _YEAR.search(part)
                if not ym:
                    continue
                sm = re.search(r"\b([A-Z][A-Za-z\-']{1,})", part)
                if not sm:
                    continue
                surname = sm.group(1)
                if surname.lower() in _AY_STOP:
                    continue
                lo = min(sm.start(), ym.start())
                hi = max(sm.end(), ym.end())
                obj = DocObject(type="Citation", props={
                    "citekey": f"{surname}{ym.group(0)}", "author": surname,
                    "year": ym.group(0), "style": "author-year",
                    "added_by": "bibliography", "page": p.get("_page")})
                obj.add_realization(Realization(
                    stream="mathpix_lines", start=anchor, end=anchor,
                    role="surface",
                    props={"offset": part_base + lo, "length": hi - lo}))
                doc.add(obj)
                ensure_reference_stub(doc, obj, bibkey)   # 010
                added += 1
    return added


import unicodedata as _ud

# author-year inside ROUND or SQUARE brackets — MathPix renders natbib
# author-year as [Surname, year]; LaTeX/prose may use (Surname, year). A pure
# numeric `[12]` has no year+surname so it's ignored here (numeric detector owns it).
_AY_GROUP = re.compile(r"[\(\[]([^()\[\]]{1,250})[\)\]]")
_AY_SURNAME = re.compile(r"([A-ZÀ-Þ][A-Za-zÀ-ſ\-']{1,})")


def _fold_key(s: str) -> str:
    """Diacritic-fold a surname for citekey matching (Gärdenfors -> gardenfors)."""
    s = _ud.normalize("NFKD", s)
    return "".join(c for c in s if not _ud.combining(c)).lower()


def spans_unrecorded(doc) -> int:
    """645 — how many Citation objects carry NO sub-anchor span.

    A citation without an `offset`/`length` on a `surface` Realization cannot
    be put back into the prose: the TiddlyWiki projector substitutes inline
    elements by per-line offset+length, so such a citation reaches no page and
    the Reference behind it is linked from nothing. The number is MEASURED
    rather than assumed — a span is never invented to make it zero (rule 5).
    """
    n = 0
    for o in doc.objects.values():
        if o.type != "Citation":
            continue
        if not any(r.role == "surface"
                   and isinstance(r.props.get("offset"), int)
                   and isinstance(r.props.get("length"), int)
                   for r in o.realizations):
            n += 1
    return n


def _span_on_its_own_line(doc, rr, needle: str, cursors: dict):
    """645 — locate `needle` on the LINE it actually sits on.

    `detect_author_year_in_objects` reads an OBJECT's joined text and had been
    recording `m.start()` — a position in THAT text — against the object's own
    Realization, whose `start` is the object's FIRST line. On any paragraph
    longer than one line the offset then names a character position that does
    not exist on that line, and the projector either substitutes the wrong
    stretch of prose or (once the offset runs past the line) nothing at all.

    Returns `(anchor, offset, length)` by LOOKING the group up in the lines the
    realization spans — not a guess — or None when no line reproduces it (a
    mutator rewrote the object's text), in which case the caller records no
    span at all and `spans_unrecorded` counts it.

    `cursors` carries a per-anchor search position so a group that occurs twice
    on one line gets two distinct spans instead of two copies of the first.
    """
    st = doc.streams.get(rr.stream)
    if st is None:
        return None
    try:
        anchors = st.slice_anchors(rr.start,
                                   rr.end if rr.end is not None else rr.start)
    except KeyError:
        anchors = [rr.start]
    for a in anchors:
        pay = st.payload.get(a) or {}
        text = pay.get("text_display") or pay.get("text") or ""
        i = text.find(needle, cursors.get(a, 0))
        if i >= 0:
            cursors[a] = i + len(needle)
            return a, i, len(needle)
    return None


def detect_author_year_in_objects(doc, exclude_anchors=()) -> int:
    """Stream-agnostic author-year citation detector over the prose OBJECTS'
    text (Paragraph/Section/Abstract/ListItem/Footnote `text`/`caption`/
    `content`) — works on markdown/source models that have no `mathpix_lines`
    stream. Matches `[Surname, year]` AND `(Surname, year)` (the natbib forms
    MathPix produces), splits multi-cites on `;`, and mints a diacritic-folded
    `surname+year` citekey so `link_citations` connects to the gold references.
    The Citation reuses the source object's realization as its surface.
    Idempotent caller should drop prior `added_by="bibliography"` Citations."""
    from docmodel.core import DocObject, Realization
    from docmodel.modules.citation import ensure_reference_stub

    bibkey = doc.meta.get("bibkey") or ""
    added = 0
    prose = ("Paragraph", "Section", "Abstract", "ListItem", "Footnote", "Toc")
    for o in list(doc.objects.values()):
        if o.type not in prose:
            continue
        text = o.props.get("text") or o.props.get("caption") or o.props.get("content") or ""
        if not text or not _YEAR.search(text):
            continue
        math = _math_ranges(text)
        rr = next((x for x in o.realizations if x.start is not None), None)
        cursors: dict = {}
        for m in _AY_GROUP.finditer(text):
            if _in_math(m.start(), math):
                continue
            content = m.group(1)
            if not _YEAR.search(content):
                continue                       # not a year-bearing group → skip
            # 645 — the span is the group's position on ITS OWN LINE, found by
            # lookup. `m.start()` is a position in the object's joined text and
            # is meaningless against a line anchor; see `_span_on_its_own_line`.
            span = _span_on_its_own_line(doc, rr, m.group(0), cursors) \
                if rr is not None else None
            # The located span is of the WHOLE group (`m.group(0)`, brackets
            # included), so a part's own offset inside `content` maps straight
            # onto the line: content starts one character past the bracket.
            base, cursor = ((span[1] + 1) if span else 0), 0
            for part in content.split(";"):
                part_base, cursor = base + cursor, cursor + len(part) + 1
                ym = _YEAR.search(part)
                if not ym:
                    continue
                sm = _AY_SURNAME.search(part)
                if not sm or sm.group(1).lower() in _AY_STOP:
                    continue
                obj = DocObject(type="Citation", props={
                    "citekey": _fold_key(sm.group(1)) + ym.group(0),
                    "author": sm.group(1), "year": ym.group(0),
                    "style": "author-year", "added_by": "bibliography",
                    "page": o.props.get("page")})
                if span is not None:
                    lo = min(sm.start(), ym.start())
                    hi = max(sm.end(), ym.end())
                    obj.add_realization(Realization(
                        stream=rr.stream, start=span[0], end=span[0],
                        role="surface",
                        props={"offset": part_base + lo, "length": hi - lo}))
                # 645 fix round 1 — when no line reproduces the group the
                # Citation gets NO realization at all. Anchoring it at the
                # object's own range would be a `surface` Realization with no
                # sub-anchor, i.e. a CLAIM on every line the paragraph covers
                # — and `ensure_reference_stub` would copy that claim onto the
                # stub, undoing 646-g on the very path this task created. The
                # Citation stands unanchored and `spans_unrecorded` counts it;
                # `cmd_bibliography` prints the count.
                doc.add(obj)
                ensure_reference_stub(doc, obj, bibkey)   # 010
                added += 1
    return added


def link_citations(doc) -> dict:
    """Add `cites` Alignments from in-text Citations to their Reference.

    Matches a citation's key to a reference citekey exactly, or by surname
    prefix (in-text `[Asai]` -> reference `Asai2023`). Idempotent: a Citation
    `ensure_reference_stub` (010) already linked at creation time is skipped
    rather than re-linked with a second, identical edge. Surface is taken from
    the citation's/reference's realization in ANY stream (so markdown/source
    models link, not just mathpix_lines).

    Returns `{"linked": …, "added": …}` (010 fix round 4). `linked` is the
    TOTAL number of Citations that resolve to a FILLED (non-stub) Reference --
    what a caller asking "is this document's bibliography wired up?" means;
    `added` is how many edges this call actually created. Returning only
    `added` (rounds 2-3) read as 0 on a correctly linked document and sent
    `cmd_bibsource` into its destructive wipe-and-redetect branch.

    A Citation linked only to its own STUB counts as UNRESOLVED here (010 fix
    round 4, item 4): the exact-citekey stub match otherwise pre-empted the
    fuzzy surname+year prefix match, which is the whole point of this pass.
    When the fuzzy match (or the reference NUMBER) lands on a real Reference,
    the stub is MERGED into it (`absorb_stub`) rather than left behind as a
    permanent duplicate.
    """
    from docmodel.core import Range
    from docmodel.modules.citation import add_cites_alignment, absorb_stub

    by_key = {}
    by_number = {}
    for r in doc.objects.values():
        if r.type == "Reference":
            ck = (r.props.get("citekey") or "").lower()
            if ck:
                by_key[ck] = r
            num = r.props.get("number")
            if num is not None and not r.props.get("stub"):
                by_number[num] = r

    def find_ref(citekey: str):
        c = (citekey or "").lower().strip()
        if not c:
            return None
        exact = by_key.get(c)
        if exact is not None and not exact.props.get("stub"):
            return exact
        # A stub is not an answer while a FILLED Reference may still prefix-match.
        if len(c) >= 3:
            for ck, r in by_key.items():
                if ck.startswith(c) and not r.props.get("stub"):
                    return r
        if exact is not None:
            return exact                          # the citation's own stub
        for ck, r in by_key.items():
            if len(c) >= 3 and ck.startswith(c):
                return r
        return None

    def surface(o):
        rr = next((x for x in o.realizations
                   if x.stream == "mathpix_lines" and x.start is not None), None)
        if rr is None:                           # markdown/source model: any stream
            rr = next((x for x in o.realizations if x.start is not None), None)
        return Range(rr.stream, rr.start, rr.end) if rr else None

    added = linked = 0
    for c in list(doc.objects.values()):
        if c.type != "Citation":
            continue
        num = c.props.get("number")
        key = c.props.get("citekey") or ""
        r = by_number.get(num) if num is not None else None
        if r is None:
            r = find_ref(key)
        if r is None:
            continue
        if not r.props.get("stub"):
            linked += 1
            stub = stub_for(doc, key)
            if stub is not None and stub is not r:
                absorb_stub(doc, stub, r)
                # the stub is gone; the key now resolves to what absorbed it,
                # so a LATER citation of the same key links there directly.
                by_key[(key or "").lower()] = r
        ls, rs = surface(c), surface(r)
        if ls and rs:
            if add_cites_alignment(doc, ls, rs, {
                    "citekey": r.props.get("citekey"), "number": num}) is not None:
                added += 1
    return {"linked": linked, "added": added}


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


def load_bibtex_file(doc, bibtext: str, restrict=None) -> dict:
    """Attach BibTeX from a .bib file to References (by citekey), creating a
    Reference for any entry not already present (with a `references` surface so
    it links). When `restrict` (a set of citekeys) is given, only those entries
    are ingested — so a larger SHARED .bib yields just THIS paper's bibliography
    (the cited subset). A citekey already present as a citation-stub Reference
    (010) is FILLED in place -- its id and anchor are kept, `stub` is dropped --
    rather than a second Reference being created for the same key. Returns
    {attached, created}."""
    from docmodel.core import DocObject, Realization
    from .perplexity_client import parse_bibtex_fields

    refs = {(r.props.get("citekey") or ""): r
            for r in doc.objects.values() if r.type == "Reference"}
    rstream = None
    attached = created = 0
    for key, raw in _split_bib_entries(bibtext):
        if restrict is not None and key not in restrict:
            continue                             # entry the paper doesn't cite
        f = parse_bibtex_fields(raw)
        r = refs.get(key)
        if r is None:
            if rstream is None:
                rstream = doc.ensure_stream("references")
            anchor = rstream.append(citekey=key)
            r = DocObject(type="Reference", props={
                "citekey": key, "raw_text": f.get("title") or "",
                "year": f.get("year") or "", "author": f.get("author") or "",
                "entry_type": f.get("entry_type") or "misc",
                "ref_source": "bib"})       # from a .bib file (gold BibTeX)
            r.add_realization(Realization(stream="references", start=anchor,
                                          end=anchor, role="surface",
                                          provenance="bib"))
            doc.add(r)
            refs[key] = r
            created += 1
        elif r.props.get("stub"):
            r.props.pop("stub", None)
            r.props["ref_source"] = "bib"      # was a citation-stub -> now gold
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


def build_bibliography_from_source(doc, source_dir) -> dict:
    """Discover the bib the LaTeX source NAMES (\\bibliography{}/\\addbibresource{})
    in `source_dir`, ingest THIS paper's bibliography (the CITED subset of a
    possibly-larger shared .bib — a compiled .bbl is already the cited set), and
    link the in-text Citations. Idempotent caller should only invoke this when no
    non-stub References exist yet (a citation-stub Reference, 010, is filled in
    place by `ingest_bbl`/`load_bibtex_file` rather than duplicated). Returns
    {created, filled, linked, added} -- `filled` counts stubs turned into gold
    (a fill leaves `created` at 0), `linked` is the TOTAL citations resolved to
    a filled Reference, `added` the edges this call created."""
    from pathlib import Path
    from . import latex_source

    res = latex_source.find_bib_resources(source_dir)
    cited = {(c.props.get("citekey") or "").strip()
             for c in doc.objects.values() if c.type == "Citation"}
    cited.discard("")
    # 010 fix round 4 -- `created` alone under-reports: `load_bibtex_file`
    # FILLS a citation stub in place (created 0) rather than making a second
    # Reference for the same key, so a run that turned every stub into gold
    # looked like it had done nothing. Count the stub->filled transition too.
    def _filled():
        return sum(1 for o in doc.objects.values()
                   if o.type == "Reference" and not o.props.get("stub"))
    filled_before = _filled()
    created = 0
    if res["bbl"]:
        created += ingest_bbl(doc, Path(res["bbl"][0]).read_text(errors="replace"))
    if res["bib"]:
        created += load_bibtex_file(
            doc, Path(res["bib"][0]).read_text(errors="replace"),
            restrict=(cited or None))["created"]
    if created == 0:
        # No .bbl/.bib file — references may be INLINE in the .tex as a
        # \begin{thebibliography} block (e.g. arXiv 2104.08926). Parse it.
        for tex in sorted(Path(source_dir).glob("*.tex")):
            try:
                txt = tex.read_text(errors="replace")
            except Exception:
                continue
            m = re.search(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}",
                          txt, re.S)
            if m:
                created += ingest_bbl(doc, m.group(0), source="bibitem")
                if created:
                    break
    res = link_citations(doc)
    return {"created": created, "filled": _filled() - filled_before,
            "linked": res["linked"], "added": res["added"]}


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


def _bbl_author_year(text: str) -> tuple[str, str]:
    """Heuristic author + year from a cleaned .bbl entry. Year = the last 19xx/20xx;
    author = the leading block up to the first sentence-ending period (one whose
    preceding token is NOT an initial like `Y.` or `al`)."""
    yrs = re.findall(r"\b(?:19|20)\d{2}\b", text)
    year = yrs[-1] if yrs else ""
    author = ""
    for m in re.finditer(r"\.\s+", text):
        prev = text[:m.start()].rstrip()
        toks = prev.split()
        last = toks[-1].strip(".").lower() if toks else ""
        if len(last) <= 1 or last in ("al", "et", "jr", "ed", "eds"):
            continue                         # an initial / "et al." — not terminal
        author = prev
        break
    if not author:                            # no terminal period → first clause
        author = text.split(".")[0].strip()
    return author[:300], year


def parse_bbl(text: str) -> list[dict]:
    """Parse a compiled `.bbl` into
    [{label, citekey, text, number, author, year}]."""
    # Strip TeX %-comments FIRST: ACM/IEEE-Reference-Format writes the label and
    # key on separate lines with a trailing comment — `\bibitem[...]%\n  {key}` —
    # so the `]…{key}` match fails on every entry unless the % line is removed.
    text = re.sub(r"(?<!\\)%.*", "", text)
    out = []
    for i, m in enumerate(_BIBITEM.finditer(text)):
        body = _clean_bbl(m.group("body"))
        author, year = _bbl_author_year(body)
        out.append({
            "label": (m.group("label") or "").strip(),
            "citekey": m.group("key").strip(),
            "text": body,
            "number": i + 1,
            "author": author,
            "year": year,
        })
    return out


def ingest_bbl(doc, bbltext: str, source: str = "bbl") -> int:
    """Create a `Reference` per `\\bibitem` (citekey + alpha label + printed
    text), each addressable via a `references` stream anchor. Returns count.

    `source` records WHERE the \\bibitem block came from: a compiled `.bbl`
    file (default) or an inline `\\begin{thebibliography}` in the `.tex`
    (`source="bibitem"`) — surfaced by `status`. A citekey already present as
    a citation-stub Reference (010) is FILLED in place -- its id and anchor
    (the citation's own, not a fresh `references` anchor) are kept, `stub` is
    dropped -- rather than a second Reference being created for the same key.
    """
    from docmodel.core import DocObject, Realization

    stream = doc.ensure_stream("references")
    stubs = {(r.props.get("citekey") or ""): r
             for r in doc.objects.values() if r.type == "Reference" and r.props.get("stub")}
    n = 0
    for e in parse_bbl(bbltext):
        r = stubs.get(e["citekey"])
        if r is not None:
            r.props.pop("stub", None)
            r.props.update({
                "label": e["label"], "number": e["number"], "raw_text": e["text"],
                "author": e.get("author", ""), "year": e.get("year", ""),
                "entry_type": "misc", "ref_source": source,
            })
        else:
            anchor = stream.append(citekey=e["citekey"], label=e["label"],
                                   number=e["number"])
            obj = DocObject(type="Reference", props={
                "citekey": e["citekey"], "label": e["label"], "number": e["number"],
                "raw_text": e["text"], "author": e.get("author", ""),
                "year": e.get("year", ""), "entry_type": "misc",
                "ref_source": source})
            obj.add_realization(Realization(stream="references", start=anchor,
                                            end=anchor, role="surface",
                                            provenance=source))
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


def link_citations_by_label(doc) -> dict:
    """Link in-text Citations to References by alpha LABEL (OCR-tolerant).

    The thesis's printed citations are alpha labels (`[ASV02]`); MathPix OCRs
    them as the Citation citekey. Match each to the `.bbl` Reference whose label
    normalizes equally, adding a `cites` Alignment.

    Returns `{"linked": …, "added": …}` (010 fix round 4) — `linked` counts the
    Citations resolved to a filled Reference in TOTAL, `added` the edges this
    call created. Edges go through `add_cites_alignment` (never
    `doc.add_alignment` directly), and the Citation's own citation-stub
    Reference is MERGED into the gold one it resolves to (`absorb_stub`): a
    Citation `[ASV02]` used to end this pass with two edges to two References
    (its stub `ASV02` and the gold `smith2002` labelled ASV02), the stub
    permanent.
    """
    from docmodel.modules.citation import add_cites_alignment, absorb_stub

    by_label = {}
    for r in doc.objects.values():
        if r.type == "Reference" and not r.props.get("stub"):
            lab = _norm_label(r.props.get("label") or "")
            if lab:
                by_label[lab] = r

    added = linked = 0
    for c in list(doc.objects.values()):
        if c.type != "Citation":
            continue
        key = c.props.get("citekey") or ""
        r = by_label.get(_norm_label(key))
        if r is None:
            continue
        linked += 1
        stub = stub_for(doc, key)
        if stub is not None and stub is not r:
            absorb_stub(doc, stub, r, {"label": r.props.get("label")})
        ls, rs = _ref_range(c), _ref_range(r)
        if ls and rs:
            if add_cites_alignment(doc, ls, rs, {
                    "citekey": r.props.get("citekey"),
                    "label": r.props.get("label")}) is not None:
                added += 1
            c.props["cited_reference_id"] = r.id
    return {"linked": linked, "added": added}


def add_reference_objects(doc, entries: list[dict]) -> int:
    """Create a `Reference` DocObject per parsed entry. Returns the count.

    A citekey already present as a citation-stub Reference (010) is FILLED in
    place -- its id and anchor (the citation's own) are kept, `stub` is
    dropped, and its `added_by` is left UNTOUCHED (010 fix round 3): a stub
    whose citation came from CitationProcessor (model build, no `added_by`
    of its own -- the stub's is the literal marker "citation") must survive
    a `cmd_bibliography --force` cleanup even after this fills it, so that
    cleanup decides purely by `added_by`, never by fill status. A FRESH
    Reference (no matching stub) IS marked `added_by: "bibliography"` --
    this command made it from nothing, so a `--force` rerun should retract
    and re-derive it, same as the Citations `detect_*` creates.
    """
    from docmodel.core import DocObject, Realization

    stubs = {(r.props.get("citekey") or ""): r
             for r in doc.objects.values() if r.type == "Reference" and r.props.get("stub")}
    n = 0
    for e in entries:
        r = stubs.get(e["citekey"])
        if r is not None:
            r.props.pop("stub", None)
            r.props.update({
                "raw_text": e["raw_text"], "year": e["year"], "author": e["author"],
                "number": e.get("number"), "entry_type": "misc", "ref_source": "text",
            })
            # 010 fix round 5 -- record WHERE in the document this entry was
            # parsed from, as a SECOND realization with role "bibliography".
            # The stub's own (role "surface") realization is a citation PROSE
            # line, and `cmd_bibliography`'s `ref_anchors` must exclude the
            # bibliography section from re-detection without excluding the
            # citation lines. The surface realization is left first and
            # untouched, so every existing `cites` edge keeps resolving.
            anchors = e.get("anchors") or []
            if anchors and not any(z.role == "bibliography" for z in r.realizations):
                r.add_realization(Realization(
                    stream="mathpix_lines", start=anchors[0], end=anchors[-1],
                    role="bibliography", provenance="bibliography"))
        else:
            obj = DocObject(type="Reference", props={
                "citekey": e["citekey"],
                "raw_text": e["raw_text"],
                "year": e["year"],
                "author": e["author"],
                "number": e.get("number"),
                "entry_type": "misc",          # heuristic; refined by a real grammar
                "ref_source": "text",          # parsed from the printed/OCR'd refs
                "added_by": "bibliography",    # 010 fix round 3: this command made it
            })
            anchors = e.get("anchors") or []
            if anchors:
                obj.add_realization(Realization(
                    stream="mathpix_lines", start=anchors[0], end=anchors[-1],
                    role="surface", provenance="bibliography"))
                # 010 fix round 5 -- the same marker the FILL branch above
                # stamps, so `ref_anchors` has ONE criterion for "this
                # Reference is anchored in the bibliography SECTION".
                obj.add_realization(Realization(
                    stream="mathpix_lines", start=anchors[0], end=anchors[-1],
                    role="bibliography", provenance="bibliography"))
            doc.add(obj)
        n += 1
    return n
