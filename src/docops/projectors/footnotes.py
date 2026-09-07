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
     `props["number"] == n` AND no body with that refnum on the marker's page
     at all                                      ->  `\\cite{<citekey>}`   (641)
  c. else the marker stands, byte-for-byte, and is counted — including the
     638-e back-reference, a second `{ }^{n}` whose page's only body an earlier
     marker already took.

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


#: `decide(rule_a=…)`: WHO decided rule (a). The two callers mean different
#: things by "no footnote id", and fix round 2 makes them say which.
#: `BY_CALLER` — the caller ran rule (a) itself and `footnote_id` is its whole
#: answer; None there means "tried, found none", NOT "look it up".
#: `BY_LOOKUP` — the caller has no pairing and `decide` runs rule (a) from
#: `look`, which must therefore already exclude bodies another marker consumed.
BY_CALLER = "by_caller"
BY_LOOKUP = "by_lookup"


@dataclass(frozen=True)
class MarkerLookups:
    """The two document-level lookups THE RULE needs, built once per document.

    `by_page_refnum` answers rule (a) — "is there a Footnote body with this
    refnum on this page?" — and `numbered` answers rule (b) — "does this number
    name a bibitem?". Nothing else about the document is consulted.
    """
    by_page_refnum: dict = field(default_factory=dict)   # (page, refnum) → [id]
    numbered: dict = field(default_factory=dict)         # number → citekey


@dataclass(frozen=True)
class Decision:
    """What ONE marker is, whichever spelling it arrived in."""
    outcome: str                     # "footnote" | "cite" | "unresolved"
    refnum: str
    footnote_id: Optional[str] = None
    citekey: Optional[str] = None
    both: bool = False               # matched a footnote AND a bibitem number


def marker_lookups(doc: Document) -> MarkerLookups:
    """Build the two lookups once. `numbered` is `latex_pipeline.reference_map`
    — the same map the numeric `[N]` brackets resolve through, not a second
    implementation of it (imported locally: a top-level import closes a cycle).
    """
    from .latex_pipeline import reference_map
    by_page: dict = {}
    for o in doc.objects.values():
        if o.type != "Footnote":
            continue
        rn = str(o.props.get("refnum") or "").strip()
        pg = o.props.get("page")
        if rn and pg is not None:
            by_page.setdefault((pg, rn), []).append(o.id)
    return MarkerLookups(by_page_refnum=by_page, numbered=reference_map(doc))


def decide(refnum: str, page, look: MarkerLookups, *, rule_a: str,
           footnote_id: Optional[str] = None, used=()) -> Decision:
    """THE ORDERED RULE — one implementation, called from BOTH spellings of the
    same marker (the bare `\\({ }^{n}\\)` walk below, and the materialised
    `<sup>n</sup>` the LaTeX projector meets after `clean`).

      a. a Footnote body with this refnum on this page  ->  footnote
      b. else, a Reference whose printed number is n, AND no body with this
         refnum on this page at all                     ->  cite
      c. else                                           ->  unresolved

    RULE (b)'s SECOND CONDITION IS FIX ROUND 2's, and it is what 638-e costs: a
    body belongs to ONE marker, so a second `{ }^{7}` on a page whose only
    footnote 7 an earlier marker already took gets no body — but it is a
    back-reference to that footnote, not a citation. The presence of a body
    with that refnum ON THAT PAGE is evidence about what the marker IS;
    consumption is bookkeeping about which body PRINTS. So an unresolved marker
    beside a taken body stands (c) instead of becoming `\\cite`.

    BOTH is a footnote, and the Decision says so (`both=True`) so the caller can
    count it: the body being physically on the page is stronger evidence than a
    bibliography entry that merely carries the same integer.

    `rule_a` says WHO decided rule (a), and it is required because the two
    callers mean different things by "no footnote id" (fix round 2 — the bug it
    fixes counted `marker_both` 2 where it must be 1):

      BY_CALLER  the caller ran rule (a) itself and `footnote_id` is its WHOLE
                 answer — None means "tried, none", and rule (a) is NOT
                 re-derived here. The bare walk pairs by marker-order-against-
                 body-order on the page, allows a one-page spill and consumes a
                 body once; none of that is expressible as a lookup, and a mark
                 it correctly left unresolved must not be handed the body an
                 earlier mark already took (638-e's back-reference).
      BY_LOOKUP  the caller has no pairing, so rule (a) is decided here from
                 `look`, skipping every body in `used` — that branch has no
                 consumption bookkeeping of its own and would otherwise hand a
                 second marker a body the first already took.

    THE CROSS-FILE INVARIANT the `<sup>n</sup>` caller relies on, named here so
    a change over there is caught here: `tiddlywiki._substitute_footnotes`
    emits `<sup>n</sup>` ONLY when `fn_by_refnum` — a DOCUMENT-WIDE map — has no
    Footnote with that refnum, so rule (a) can never fire for that lane today.
    If that map is ever scoped to a page, this branch starts resolving
    footnotes and `latex._sup_page` (the rendered OBJECT's page, not the
    marker's line — 641-c) becomes load-bearing.
    `test_a_sup_marker_is_only_emitted_when_no_footnote_has_that_refnum` pins
    the invariant.
    """
    if rule_a not in (BY_CALLER, BY_LOOKUP):
        raise ValueError(f"decide(): rule_a must be BY_CALLER or BY_LOOKUP, "
                         f"got {rule_a!r}")
    on_page = list(look.by_page_refnum.get((page, str(refnum)), ()))
    fid = footnote_id
    if fid is None and rule_a == BY_LOOKUP:
        free = [i for i in on_page if i not in set(used or ())]
        if free:
            fid = free[0]
    try:
        key = look.numbered.get(int(refnum))
    except (TypeError, ValueError):
        key = None
    if fid:
        return Decision("footnote", str(refnum), footnote_id=fid,
                        both=key is not None)
    if key and not on_page:
        return Decision("cite", str(refnum), citekey=key)
    return Decision("unresolved", str(refnum))


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
    #: the two lookups THE RULE reads — kept so the projector's `<sup>n</sup>`
    #: lane decides through the SAME `decide()` on the SAME document state.
    lookups: MarkerLookups = field(default_factory=MarkerLookups)

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
        # 641 — the citation half of the same marker population. `markers_*`
        # and `marker_both` count BOTH spellings: the bare walk fills them here,
        # the projector's `<sup>n</sup>` lane adds to them as it renders (fix
        # round 1), and the `sup_*` rows are that lane's own breakdown.
        "references_numbered": 0,
        "markers_cited": 0,
        "marker_both": 0,
        "sup_markers": 0,
        "sup_marker_footnote": 0,
        "sup_marker_cited": 0,
        "sup_marker_both": 0,
        "sup_marker_default": 0,
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
    look = marker_lookups(doc)
    res.lookups = look
    res.counts["references_numbered"] = len(look.numbered)
    for mk in all_marks:
        # Passes 1 and 2 already did rule (a) — with the order tie-break, the
        # one-page spill and the one-body-per-marker consumption a lookup cannot
        # express — so their answer is handed IN rather than re-derived.
        d = decide(mk.refnum, mk.page, look, rule_a=BY_CALLER,
                   footnote_id=mk.footnote_id)
        mk.citekey = d.citekey
        mk.both = d.both
        if d.both:
            res.counts["marker_both"] += 1

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
