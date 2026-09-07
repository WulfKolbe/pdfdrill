r"""642 — put every in-text Citation back into the LaTeX running text as `\\cite`.

639 prints one `\\bibitem` per Reference, so no key CAN dangle — as long as the
body emits `\\cite` at all, and it did not. penev_A's projected `.tex` held 81
Citation objects, 52 `\\bibitem`s and **zero** `\\cite`: the citations existed in
the model, carried exact spans, and reached the page in the TiddlyWiki
projection (645) and nowhere else.

WHERE A CITATION IS. Its span is recorded per LINE — a `mathpix_lines` anchor
plus `offset`/`length` — while the LaTeX projector renders an object's
MATERIALISED text. This module bridges the two the way 638 bridged the footnote
markers: it reads the groups off the lines the object is anchored at (through
the shared `docops.citation_spans`, the same derivation the TiddlyWiki
projector reads), and hands the projector LITERAL substitutions — the exact
source substring and what to put in its place. The projector then finds that
substring in the object's own text, in order. Nothing is edited by offset
against a text that may have moved: when the substring is not there the
substitution is skipped and counted (645's `citation_span_out_of_bounds`
lesson, 638's "the text moved" guard).

ONLY WHERE A REFERENCE EXISTS. A `\\cite{key}` with no `\\bibitem{key}` prints as
a bold `?`. A Citation whose key reaches no Reference — stub or filled — is
therefore NOT emitted as `\\cite`; its original text stands and it is counted
(`cite_without_reference`). With 010 (a stub Reference at first citation) that
count is 0 on a normally built document, which is a fact to CHECK per document,
not to assume.

AND THE KEY IS THE REFERENCE'S. The `\\bibitem` carries the Reference's citekey,
so that is what `\\cite` must name. Where a linker resolved an in-text label to
a differently-keyed gold entry (`[ASV02]` -> `smith2002`) the stored link
(`cited_reference_id`) is what the projector follows; the in-text label would
dangle.

EVERY BLOCK OF PROSE THE PROJECTOR EMITS (fix round 2). `CITED_TEXT_TYPES` is
638's `RUNNING_TEXT_TYPES` (Paragraph, Abstract, ListItem) PLUS `Footnote`,
because `LaTeXProjector._footnotetext` renders a footnote body and Citations do
sit on footnote lines — 8 on penev_A, 5 on penev_B. Round 1 left that path on
the old number map and the mis-wire below was still reachable there; it also
meant a footnote-body citation reached the page as nothing at all (645-a). Both
are fixed at once: the resolver owns the footnote body too, and a group emitted
in one is counted (`cite_in_footnote`).

`Sidenote` is deliberately NOT in the set: `LaTeXProjector._render` has no
Sidenote branch, so a sidenote body never reaches the .tex on any path (638-c),
and claiming to have substituted a citation into a block nobody prints would be
a count that overstates what the reader gets. Those citations stay under
`citations_outside_running_text`.

`Picture`/`Diagram` ARE in the set (640). A figure caption is prose exactly
like a footnote body — MathPix's own `\caption{…}` can carry `[N]` the same
way a paragraph does (`Adelson's checkerboard illusion [29]`) — and
`LaTeXProjector._render` DOES have a branch for both, so the substitution
reaches the page (or, when there is no `latex_code`, the `% figure pN: …`
comment `_render` falls back to). `Table` is deliberately NOT in the set: a
`Table` with no `latex_code` renders its `raw_text` inside
`\begin{verbatim}…\end{verbatim}`, where LaTeX does not interpret `\cite{…}`
at all — substituting there would print the literal command text instead of a
number. A table-cell citation still gets a Citation object (`bibliography.
detect_numeric_citations` scans cell lines, 640), so the model records it
correctly; it is counted under `citations_outside_running_text` on the LaTeX
side like the Sidenote case, because no emitted block covers it.

ONE RESOLVER OWNS CITATIONS (fix rounds 1 and 2). `latex_pipeline.resolve_citations`
predates this module: it rewrites any `[N]`/`[N,M]` bracket through
`{Reference.number: citekey}` and knows nothing about which Citation owns the
bracket. Left running after this resolver in `_prose`, it UNDID the decision
above — a Citation `NoSuchKey` over `[5]`, correctly left verbatim and counted,
was rewritten to `\cite{Realname2001}` because an unrelated Reference happened
to be numbered 5. It compiles, it looks right, and it cites the wrong paper.

So the numeric fallback lives HERE, behind the claim: a bracket that a Citation
object covers follows the CITATION's decision, always; a bracket NO Citation
covers may still resolve by number (`numeric_brackets_resolved`) — the pass's
legitimate case, which is a `[12]`-style document whose brackets no detector
turned into Citation objects. A Citation that was left verbatim CLAIMS its
bracket even though it produced no substitution; that claim is the whole point.
`LaTeXProjector._prose` no longer runs the old pass AT ALL — every block of
prose it emits comes from a caller that ran the resolver first, so there is no
path left on which the number map can act without the claim.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from docmodel.core import Document, DocObject
from .. import citation_spans as _cspans
from .footnotes import RUNNING_TEXT_TYPES, _flow, object_text

#: The object types whose prose the LaTeX projector emits AND whose citations it
#: therefore owns. 638's running-text set plus `Footnote` (rendered by
#: `_footnotetext`); NOT `Sidenote`, which `_render` never emits at all (638-c).
CITED_TEXT_TYPES = RUNNING_TEXT_TYPES + ("Footnote", "Picture", "Diagram")


@dataclass(frozen=True)
class Sub:
    """One citation group, as a literal substitution on an object's text."""
    anchor: object                     # the line the group was read off
    offset: int                        # the group's offset ON THAT LINE
    length: int
    source: str                        # the exact source substring
    replacement: str                   # `\cite{a,b}`
    keys: tuple[str, ...]
    kind: str = "citation"             # "citation" | "numeric-bracket"


@dataclass
class CiteResolution:
    subs: dict[str, list[Sub]] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    def subs_for(self, obj_id: str) -> list[Sub]:
        return self.subs.get(obj_id, [])

    def table(self) -> dict:
        """The inspectable table (`pdfdrill latex --dump-stages`)."""
        rows = []
        for oid, subs in self.subs.items():
            for s in subs:
                rows.append({"object": oid, "offset": s.offset,
                             "source": s.source, "replacement": s.replacement,
                             "keys": list(s.keys)})
        rows.sort(key=lambda r: (r["object"], r["offset"]))
        return {"counts": dict(self.counts), "groups": rows}


def _surface_spans(cit: DocObject) -> list[tuple[object, int, int]]:
    """`(line anchor, offset, length)` for each `mathpix_lines` surface span the
    Citation carries. Empty when it carries none — a position is never invented
    for it (HANDOVER-RULES rule 5)."""
    out = []
    for r in cit.realizations:
        if (r.stream == "mathpix_lines" and r.role == "surface"
                and r.start is not None):
            off, ln = r.props.get("offset"), r.props.get("length")
            if isinstance(off, int) and isinstance(ln, int):
                out.append((r.start, off, ln))
    return out


def reference_for(doc: Document, cit: DocObject) -> Optional[DocObject]:
    """The Reference a Citation is to be emitted against: the STORED link
    (`cited_reference_id`, written by the linkers) first, then the citekey.
    None when the document holds no Reference for it at all — the case that
    must not become a `\\cite`."""
    rid = cit.props.get("cited_reference_id")
    if rid:
        ref = doc.objects.get(rid)
        if ref is not None and ref.type == "Reference":
            return ref
    key = (cit.props.get("citekey") or "").strip()
    if not key:
        return None
    return next((o for o in doc.objects.values()
                 if o.type == "Reference"
                 and (o.props.get("citekey") or "").strip() == key), None)


def resolve(doc: Document) -> CiteResolution:
    """Every citation group in the document's running text, as a literal
    substitution on the object that carries it."""
    res = CiteResolution()
    res.counts = {
        "citations": 0,
        "citations_without_a_span": 0,
        "cite_without_reference": 0,
        "citations_outside_running_text": 0,
        "cite_spans_out_of_bounds": 0,
        "cite_groups": 0,
        "cite_keys": 0,
        "cite_source_not_in_text": 0,
        "numeric_brackets_resolved": 0,
        "cite_in_footnote": 0,
    }

    spans_by_line: dict = {}
    claimed_by_line: dict = {}       # EVERY Citation span, resolved or not
    placed_lines: dict = {}          # line anchor -> [citation ids] (for 645-a)
    for cit in doc.objects.values():
        if cit.type != "Citation":
            continue
        res.counts["citations"] += 1
        spans = _surface_spans(cit)
        if not spans:
            res.counts["citations_without_a_span"] += 1
            continue
        for anchor, off, ln in spans:
            # A Citation CLAIMS its bracket whatever is decided about it. The
            # numeric fallback below never touches a claimed one.
            claimed_by_line.setdefault(anchor, []).append((off, off + ln))
        ref = reference_for(doc, cit)
        if ref is None:
            # "Only where a Reference exists": a `\cite` with no `\bibitem`
            # prints as a bold `?`, so the citation stays the text it was.
            res.counts["cite_without_reference"] += 1
            continue
        key = (ref.props.get("citekey") or "").strip()
        if not key:
            res.counts["cite_without_reference"] += 1
            continue
        for anchor, off, ln in spans:
            spans_by_line.setdefault(anchor, []).append((off, ln, key))
            placed_lines.setdefault(anchor, []).append(cit.id)

    stream = doc.streams.get("mathpix_lines")
    if stream is None:
        return res
    from .latex_pipeline import reference_map      # local: avoid an import cycle
    ref_map = reference_map(doc)

    reached: set = set()
    ordered = sorted((o for o in doc.objects.values()
                      if o.type in CITED_TEXT_TYPES), key=_flow)
    for obj in ordered:
        # EVERY surface realization, not the first. 637 gave a Footnote more
        # than one: the object built off MathPix's `footnote` PARENT line now
        # also carries the extent on the CHILD lines the cleanup located, and
        # the citations are on the children. Reading only the first realization
        # took the parent line alone and left 8 penev_A footnote-body citations
        # as plain text — counted as `citations_outside_running_text`, which is
        # how it was seen.
        anchors: list = []
        seen: set = set()
        for r in obj.realizations:
            if r.stream != "mathpix_lines" or r.role != "surface" \
                    or r.start is None:
                continue
            end = r.end if r.end is not None else r.start
            try:
                span = stream.slice_anchors(r.start, end)
            except KeyError:
                continue
            for a in span:
                if a not in seen:
                    seen.add(a)
                    anchors.append(a)
        if not anchors:
            continue
        subs: list[Sub] = []
        for anchor in anchors:
            spans = spans_by_line.get(anchor)
            claimed = claimed_by_line.get(anchor, ())
            if not spans and not ref_map:
                continue                       # nothing to substitute here
            text = _cspans.line_text(doc, anchor)
            on_line: list[Sub] = []
            taken: list[tuple[int, int]] = list(claimed)
            if spans:
                for g in _cspans.groups(
                        text, spans,
                        on_out_of_bounds=lambda: res.counts.__setitem__(
                            "cite_spans_out_of_bounds",
                            res.counts["cite_spans_out_of_bounds"] + 1)):
                    keys = tuple(g.payloads)
                    on_line.append(Sub(
                        anchor=anchor, offset=g.start, length=g.length,
                        source=text[g.start:g.end],
                        replacement="\\cite{" + ",".join(keys) + "}",
                        keys=keys))
                    taken.append((g.start, g.end))
                reached.add(anchor)
            on_line += _numeric_fallback(text, taken, ref_map, anchor, res)
            on_line.sort(key=lambda s: s.offset)
            subs += on_line
        if subs:
            res.subs[obj.id] = subs
            # `cite_groups`/`cite_keys` count the CITATION groups, so the
            # accounting identity (citations = keys emitted + citations on a
            # line no running-text object covers) still holds; the numeric
            # fallback has its own counter.
            cits = [s for s in subs if s.kind == "citation"]
            res.counts["cite_groups"] += len(cits)
            res.counts["cite_keys"] += sum(len(s.keys) for s in cits)
            if obj.type == "Footnote":
                res.counts["cite_in_footnote"] += len(cits)

    # 645-a, counted rather than left to be rediscovered: a citation on a line
    # no object in `CITED_TEXT_TYPES` covers — a Sidenote body (`_render` has no
    # branch for it, 638-c), or a line no object claims at all — is never
    # substituted.
    res.counts["citations_outside_running_text"] = sum(
        len(ids) for anchor, ids in placed_lines.items() if anchor not in reached)
    return res


#: A numeric in-text citation bracket, the shape `latex_pipeline` has always
#: recognised: `[11]`, `[11, 12]`, `[11-13]`.
_BRACKET = re.compile(r"\[(\d+(?:\s*[,\-\u2013]\s*\d+)*)\]")


def _numeric_fallback(text: str, taken: list, ref_map: dict, anchor,
                      res: "CiteResolution") -> list[Sub]:
    """`[N]` brackets on this line that NO Citation object covers, resolved
    through `{Reference.number: citekey}`.

    Two guards, both load-bearing. The bracket must overlap NOTHING a Citation
    claims — a Citation left verbatim because its key has no Reference still
    claims its bracket, and rewriting that one by number is the mis-wire this
    fix exists to remove. And EVERY number in the bracket must be a Reference,
    or it is an array index / an interval (`[0,1]`) and stays raw.
    """
    if not ref_map:
        return []
    from .latex_pipeline import _expand_bracket_numbers, resolve_citations
    out: list[Sub] = []
    for m in _BRACKET.finditer(text):
        if any(m.start() < end and start < m.end() for start, end in taken):
            continue
        nums = _expand_bracket_numbers(m.group(1))
        if not nums or any(n not in ref_map for n in nums):
            continue
        # The RULE stays `latex_pipeline.resolve_citations` — the one text-level
        # implementation, with its own tests. What changed is that it is now
        # reached ONLY here, on a bracket the claim allows, instead of being run
        # over whole blocks of prose after the resolver had already decided.
        repl = resolve_citations(m.group(0), ref_map)
        if repl == m.group(0):
            continue
        keys = tuple(dict.fromkeys(ref_map[n] for n in nums))
        out.append(Sub(anchor=anchor, offset=m.start(),
                       length=m.end() - m.start(), source=m.group(0),
                       replacement=repl, keys=keys, kind="numeric-bracket"))
        res.counts["numeric_brackets_resolved"] += 1
    return out


#: A citation source that is nothing but a digit (or a `_numlist_spans` range
#: token, `3-5`) — the LOCANT/table/diagram classes (640) are all keyed this
#: way. Short and content-free, so it can occur ANYWHERE in an object's
#: materialised text by coincidence: `clean` may have already spent the
#: citation's own bracket on a `{{…_REF_Stein1970||CIT}}` token whose NAME
#: contains the same digit, or the object may carry an unrelated bare number
#: (`-1`, a page or equation number) earlier in the same paragraph. An
#: author-year or multi-key source is never this short, so the guard below
#: is scoped to exactly the shape that needs it.
_BARE_NUMERIC_SOURCE = re.compile(r"\d+(?:\s*[-–]\s*\d+)?$")

#: What may sit immediately before a numeric citation's OWN digit: the
#: bracket that opens it, or the `,`/`;` that separates it from the key
#: before it — the exact set `_numlist_spans` splits on. Nothing else does;
#: this is what tells a real `[1` from a coincidental `-1` or the `1` inside
#: `Stein1970`.
_CITE_OPENERS = "[,;"


def _numeric_source_in_context(text: str, at: int, source: str) -> bool:
    """640 fix round 1 — `j == 0` (nothing but whitespace before the match)
    used to be accepted unconditionally, on the theory that a citation can
    open an object's own text. That is true only when the OPENING BRACKET is
    itself part of `source` (the `_numeric_fallback` bracket-inclusive
    sources, e.g. `"[12]"`) — a bare-digit source (`"1"`, never `"[1"`)
    starting the text has NO bracket before it AT ALL, so position 0 is a
    Footnote/caption/table body that happens to begin with a number
    ("1970 was..."), not a citation, and must keep searching forward exactly
    like any other coincidental match."""
    j = at
    while j > 0 and text[j - 1] in " \t":
        j -= 1
    if j == 0:
        return source.startswith("[")
    return text[j - 1] in _CITE_OPENERS


def apply_subs(text: str, subs: list[Sub], *,
               on_missing=None) -> str:
    """Apply `subs` to `text` by LITERAL search, in order, from a moving cursor.

    A group whose source substring is not in the text from the cursor on is
    SKIPPED and reported through `on_missing` — the object's materialised text
    and its lines disagree (a mutator rewrote it), and a positional edit against
    a text that moved replaces the wrong characters.

    640 — a bare-numeric source (`_BARE_NUMERIC_SOURCE`) additionally REQUIRES
    `_numeric_source_in_context` at the position `find` returns, and keeps
    searching forward past a match that fails it. Without this a Citation
    keyed `"1"` corrupted `{{…_REF_Stein1970||CIT}}` (the `1` inside
    `Stein1970`) and turned a bare `-1` in running prose into `-\\cite{…}` —
    both reproduced end to end and pinned by
    `test_a_bare_numeric_source_skips_a_coincidental_digit_inside_a_token`
    and `..._skips_a_coincidental_bare_digit_in_prose`.
    """
    out: list[str] = []
    cursor = 0
    for s in subs:
        if not s.source:
            continue
        numeric = bool(_BARE_NUMERIC_SOURCE.fullmatch(s.source.strip()))
        at = text.find(s.source, cursor)
        if numeric:
            while at >= 0 and not _numeric_source_in_context(text, at, s.source):
                at = text.find(s.source, at + 1)
        if at < 0:
            if on_missing is not None:
                on_missing(s)
            continue
        out.append(text[cursor:at])
        out.append(s.replacement)
        cursor = at + len(s.source)
    out.append(text[cursor:])
    return "".join(out)
