"""638 — resolve a printed footnote MARKER in running text to its Footnote body.

A drilled document holds the two halves of a footnote in two places and joins
them nowhere:

  * the BODY is a `Footnote` DocObject — `refnum` (the PRINTED number),
    `anchor_marker` (`"{ }^{3}"`, *synthesised from* `refnum`, not looked up),
    `content` and `page`;
  * the MARKER is raw inline maths inside the paragraph's own text, exactly as
    MathPix writes an empty-base superscript: `\\({ }^{3}\\)`.

`FootnoteProcessor` never records where the marker is — it reads `refnum` off
the BODY line — so the marker's position is not in the model and cannot be
looked up there. It is, however, recoverable exactly: the marker is IN the
paragraph's own lines, and the line carries `_page`. That is what `resolve`
does; nothing here invents a page or a pairing.

THE DISAMBIGUATION, in one sentence: a marker `{ }^{n}` on page P takes the
Footnote with refnum n whose body page is P (marker order on the page against
body order on the page when there is more than one); failing that, the nearest
LATER page (a body spills forward, never backward); failing that the marker is
left exactly as it is and counted.

`refnum` is NOT a key — it restarts per chapter. On penev_A 16 refnums name
more than one Footnote (9 six times, 3 five times), which is why the
document-wide `first-with-that-refnum-wins` map the TiddlyWiki projector still
uses (644-a / 646-a) is not enough here.

641 — THE SAME MARKER MAY BE A CITATION. A numeric superscript citation and a
footnote reference are the SAME inline maths: MathPix writes both as an
empty-base `{ }^{n}`, so nothing in the maths tells them apart. The DOCUMENT
does, and the ordered rule is:

  a. a Footnote with refnum n whose body page is the marker's page (or +1
     within `MAX_SPILL_PAGES`)                   ->  `\\footnotemark[n]`   (638)
  b. else, when the reference list is NUMBERED at all, a Reference with
     `props["number"] == n`                      ->  `\\cite{<citekey>}`   (641)
  c. else the marker stands, byte-for-byte, and is counted.

THE DISAMBIGUATION IN ONE SENTENCE: a footnote marker has a BODY on its own
page; a citation superscript has a NUMBERED BIBITEM and no such body — and when
a marker matches both (a numbered reference list and footnotes on the same page
both exist) the footnote wins, because the body being physically on that page is
the stronger evidence, and that collision is counted (`marker_both`) rather than
silently decided.

Rule (b) is GATED on the document: it fires only where at least one Reference
carries a printed `number`. penev_A is author-year — 52 References, 0 numbered —
so it never fires there, which is the designed outcome and not a failure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from docmodel.core import Document, DocObject


#: The object types whose text is RUNNING TEXT. A marker inside a `Footnote`
#: body is NOT a reference — it is the printed label of a second body MathPix
#: merged into the first (29 of penev_A's 53 footnote bodies carry one), so
#: footnote and sidenote bodies are deliberately excluded.
RUNNING_TEXT_TYPES = ("Paragraph", "Abstract", "ListItem")

#: How far forward a body may sit from its marker. A footnote body spills to
#: the NEXT page and no further; anything beyond that is the per-chapter
#: renumbering pretending to be a match. Measured on penev_A: of the 11 markers
#: an uncapped forward search resolved, ONE was a genuine +1 spill and the other
#: ten sat 4 to 12 pages away — a different chapter's footnote n. Ten wrong
#: bodies attached to ten markers is exactly the "content mixed up" half of the
#: conservation claim (646), so the search is capped and the ten are counted as
#: unresolved instead.
MAX_SPILL_PAGES = 1

#: Inline-math spans, longest delimiter first (same shape as
#: `docmodel.modules.formula._MATH_RE`).
_MATH_SPAN = re.compile(
    r"\\\[[\s\S]*?\\\]"
    r"|\$\$[\s\S]*?\$\$"
    r"|\\\([\s\S]*?\\\)"
    r"|\$(?:[^$\n]|\\\$)*?\$"
)

#: The marker BODY: an empty (or absent, or purely spacing) base carrying
#: nothing but a number. `\sigma_{r}{ }^{2}` is σ_r² and must NOT match — 74 of
#: penev_A's 220 `{ }^{n}` occurrences are a real exponent of that shape.
_MARKER_BODY = re.compile(
    r"^\s*(?:\{\s*\}|\\[,!;: ])?\s*\^\s*\{\s*(\d+)\s*\}\s*$"
    r"|^\s*(?:\{\s*\}|\\[,!;: ])?\s*\^\s*(\d)\s*$"
)


def _strip_delims(span: str) -> Optional[str]:
    """The maths inside an inline span, or None when `span` is not one."""
    for open_, close in (("\\[", "\\]"), ("$$", "$$"), ("\\(", "\\)"), ("$", "$")):
        if span.startswith(open_) and span.endswith(close) and \
                len(span) >= len(open_) + len(close):
            return span[len(open_):-len(close)]
    return None


def marker_refnum(span: str) -> Optional[str]:
    """The printed number when `span` is a whole inline-math span holding
    nothing but a footnote marker; None otherwise (a real exponent, a formula,
    plain prose)."""
    body = _strip_delims(span.strip())
    if body is None:
        return None
    m = _MARKER_BODY.match(body)
    if not m:
        return None
    return m.group(1) or m.group(2)


def find_markers(text: str) -> list[tuple[int, int, str]]:
    """Every footnote marker in `text` as `(start, end, refnum)`, in order."""
    out: list[tuple[int, int, str]] = []
    for m in _MATH_SPAN.finditer(text):
        rn = marker_refnum(m.group(0))
        if rn is not None:
            out.append((m.start(), m.end(), rn))
    return out


def object_text(obj: DocObject) -> str:
    """The running text of an object, whichever prop carries it."""
    for key in ("text", "content"):
        v = obj.props.get(key)
        if isinstance(v, str) and v:
            return v
    return ""


@dataclass
class Mark:
    """One marker occurrence in one object's running text."""
    obj_id: str
    index: int                       # occurrence index within that object
    refnum: str
    page: Optional[int]
    footnote_id: Optional[str] = None
    later_page: bool = False
    ambiguous: bool = False
    citekey: Optional[str] = None    # 641 — rule (b): a numbered bibitem
    both: bool = False               # matched a footnote AND a bibitem number

    @property
    def outcome(self) -> str:
        """`footnote` | `cite` | `unresolved` — one word per marker."""
        if self.footnote_id:
            return "footnote"
        if self.citekey:
            return "cite"
        return "unresolved"


@dataclass
class Resolution:
    marks: dict[str, list[Mark]] = field(default_factory=dict)
    used: set[str] = field(default_factory=set)
    refnum_of: dict[str, str] = field(default_factory=dict)   # footnote id → refnum
    page_of: dict[str, object] = field(default_factory=dict)  # footnote id → page
    counts: dict[str, int] = field(default_factory=dict)

    def marks_for(self, obj_id: str) -> list[Mark]:
        return self.marks.get(obj_id, [])

    def table(self) -> dict:
        """The inspectable resolution table (the `03-footnotes` stage dump)."""
        rows = []
        for marks in self.marks.values():
            for mk in marks:
                rows.append({
                    "object": mk.obj_id,
                    "index": mk.index,
                    "refnum": mk.refnum,
                    "marker_page": mk.page,
                    "footnote": mk.footnote_id,
                    "footnote_page": self.page_of.get(mk.footnote_id),
                    "later_page": mk.later_page,
                    "ambiguous": mk.ambiguous,
                    "citekey": mk.citekey,
                    "both": mk.both,
                    "outcome": mk.outcome,
                })
        rows.sort(key=lambda r: (r["marker_page"] if r["marker_page"] is not None
                                 else 10 ** 9, r["object"], r["index"]))
        return {"counts": dict(self.counts), "marks": rows}


def _flow(obj: DocObject) -> tuple:
    fi = obj.props.get("flow_index")
    if isinstance(fi, int):
        return (0, fi, 0)
    return (1, int(obj.props.get("page") or 0), 0)


def _marker_pages(doc: Document, obj: DocObject,
                  refnums: list[str]) -> list[Optional[int]]:
    """The page each marker of `obj` sits on, LOOKED UP in the lines the object
    is anchored at. Returns `[None, …]` when the lookup cannot be made exact —
    the position is never guessed (HANDOVER-RULES rule 5)."""
    stream = doc.streams.get("mathpix_lines")
    if stream is None:
        page = obj.props.get("page")
        return [page] * len(refnums) if isinstance(page, int) else [None] * len(refnums)
    surface = next(
        (r for r in obj.realizations
         if r.stream == "mathpix_lines" and r.role == "surface"
         and r.start is not None),
        None,
    )
    if surface is None:
        return [None] * len(refnums)
    on_lines: list[tuple[str, Optional[int]]] = []
    pages_seen: set = set()
    for anchor in stream.slice_anchors(surface.start, surface.end):
        payload = stream.payload[anchor]
        pages_seen.add(payload.get("_page"))
        raw = payload.get("text_display") or payload.get("text") or ""
        for _s, _e, rn in find_markers(raw):
            on_lines.append((rn, payload.get("_page")))
    if [rn for rn, _ in on_lines] == refnums:
        return [pg for _, pg in on_lines]
    # The materialised text and the lines disagree (a mutator rewrote it). The
    # object's page is still exact when every line it covers is on ONE page.
    if len(pages_seen) == 1:
        only = next(iter(pages_seen))
        if isinstance(only, int):
            return [only] * len(refnums)
    return [None] * len(refnums)


def _numbered_references(doc: Document) -> dict[int, str]:
    """`{printed number: citekey}` for the References that carry BOTH — 641's
    rule (b) lookup, and the same map `latex_pipeline.reference_map` builds for
    numeric `[N]` brackets. Imported locally: `latex_pipeline` imports this
    module's siblings and a top-level import would close the cycle."""
    from .latex_pipeline import reference_map
    return reference_map(doc)


def resolve(doc: Document) -> Resolution:
    """Pair every running-text footnote marker with its Footnote body, and —
    641 — every marker no body claimed with the numbered bibitem it names."""
    res = Resolution()
    res.counts = {
        "footnotes": 0,
        "footnotes_without_a_refnum": 0,
        "footnotes_without_an_anchor_marker": 0,
        "footnotes_lacking_a_field": 0,
        "footnotes_marked": 0,
        "footnotes_unmarked": 0,
        "markers_total": 0,
        "markers_resolved": 0,
        "markers_resolved_on_a_later_page": 0,
        "markers_unresolved": 0,
        "markers_ambiguous": 0,
        "markers_without_a_page": 0,
        # 641 — the citation half of the same marker population.
        "references_numbered": 0,
        "markers_cited": 0,
        "marker_both": 0,
    }

    footnotes = sorted(
        (o for o in doc.objects.values() if o.type == "Footnote"), key=_flow)
    by_refnum: dict[str, list[DocObject]] = {}
    for fn in footnotes:
        res.counts["footnotes"] += 1
        rn = str(fn.props.get("refnum") or "").strip()
        am = str(fn.props.get("anchor_marker") or "").strip()
        if not rn:
            res.counts["footnotes_without_a_refnum"] += 1
        if not am:
            res.counts["footnotes_without_an_anchor_marker"] += 1
        if not (rn and am):
            res.counts["footnotes_lacking_a_field"] += 1
            continue
        res.refnum_of[fn.id] = rn
        res.page_of[fn.id] = fn.props.get("page")
        by_refnum.setdefault(rn, []).append(fn)

    ordered = sorted(
        (o for o in doc.objects.values() if o.type in RUNNING_TEXT_TYPES),
        key=_flow)
    all_marks: list[Mark] = []
    for obj in ordered:
        found = find_markers(object_text(obj))
        if not found:
            continue
        refnums = [rn for _s, _e, rn in found]
        pages = _marker_pages(doc, obj, refnums)
        marks = [Mark(obj_id=obj.id, index=i, refnum=rn, page=pg)
                 for i, (rn, pg) in enumerate(zip(refnums, pages))]
        res.marks[obj.id] = marks
        all_marks += marks

    res.counts["markers_total"] = len(all_marks)
    res.counts["markers_without_a_page"] = sum(
        1 for mk in all_marks if mk.page is None)

    # PASS 1 — the same page. Marker order on the page against body order on
    # the page; more than one candidate makes every pairing in that bucket
    # AMBIGUOUS and it is reported, not smoothed over (646-a).
    buckets: dict[tuple, list[Mark]] = {}
    for mk in all_marks:
        if mk.page is not None:
            buckets.setdefault((mk.page, mk.refnum), []).append(mk)
    for (page, refnum), bucket in buckets.items():
        cands = [f for f in by_refnum.get(refnum, [])
                 if f.props.get("page") == page and f.id not in res.used]
        for mk, fn in zip(bucket, cands):
            mk.footnote_id = fn.id
            mk.ambiguous = len(cands) > 1
            res.used.add(fn.id)

    # PASS 2 — the body spilled forward. Nearest LATER page, never earlier.
    for mk in all_marks:
        if mk.footnote_id or mk.page is None:
            continue
        cands = [f for f in by_refnum.get(mk.refnum, [])
                 if f.id not in res.used
                 and isinstance(f.props.get("page"), int)
                 and mk.page < f.props["page"] <= mk.page + MAX_SPILL_PAGES]
        if not cands:
            continue
        cands.sort(key=lambda f: (f.props["page"], _flow(f)))
        mk.footnote_id = cands[0].id
        mk.later_page = True
        res.used.add(cands[0].id)

    # PASS 3 — 641, rule (b). A marker no Footnote body claimed, whose number
    # names a NUMBERED bibitem, is a citation superscript. Gated on the document
    # having a numbered reference list at all: on an author-year document
    # (penev_A: 52 References, 0 with a `number`) `numbered` is empty and this
    # pass cannot fire, which is the designed outcome.
    numbered = _numbered_references(doc)
    res.counts["references_numbered"] = len(numbered)
    for mk in all_marks:
        try:
            n = int(mk.refnum)
        except (TypeError, ValueError):
            continue
        key = numbered.get(n)
        if key is None:
            continue
        if mk.footnote_id:
            # BOTH. The footnote keeps it — the body is physically on the page,
            # a bibitem number is only a number — and the collision is counted
            # rather than decided in silence.
            mk.both = True
            res.counts["marker_both"] += 1
            continue
        mk.citekey = key

    for mk in all_marks:
        if mk.footnote_id:
            res.counts["markers_resolved"] += 1
            if mk.later_page:
                res.counts["markers_resolved_on_a_later_page"] += 1
            if mk.ambiguous:
                res.counts["markers_ambiguous"] += 1
        elif mk.citekey:
            res.counts["markers_cited"] += 1
        else:
            res.counts["markers_unresolved"] += 1
    res.counts["footnotes_marked"] = len(res.used)
    res.counts["footnotes_unmarked"] = res.counts["footnotes"] - len(res.used)
    return res
