"""642 — put every in-text Citation back into the LaTeX running text as `\\cite`.

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

RUNNING TEXT ONLY. `RUNNING_TEXT_TYPES` (Paragraph, Abstract, ListItem) is
638's set and it is the same boundary 645-a names for TiddlyWiki: a citation
whose line is owned by a Footnote or Sidenote body is not substituted, because
those bodies are emitted from `props["content"]` verbatim. Those citations are
counted (`citations_outside_running_text`) rather than silently absent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from docmodel.core import Document, DocObject
from .. import citation_spans as _cspans
from .footnotes import RUNNING_TEXT_TYPES, _flow, object_text


@dataclass(frozen=True)
class Sub:
    """One citation group, as a literal substitution on an object's text."""
    anchor: object                     # the line the group was read off
    offset: int                        # the group's offset ON THAT LINE
    length: int
    source: str                        # the exact source substring
    replacement: str                   # `\cite{a,b}`
    keys: tuple[str, ...]


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
    }

    spans_by_line: dict = {}
    placed_lines: dict = {}          # line anchor -> [citation ids] (for 645-a)
    for cit in doc.objects.values():
        if cit.type != "Citation":
            continue
        res.counts["citations"] += 1
        spans = _surface_spans(cit)
        if not spans:
            res.counts["citations_without_a_span"] += 1
            continue
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

    reached: set = set()
    ordered = sorted((o for o in doc.objects.values()
                      if o.type in RUNNING_TEXT_TYPES), key=_flow)
    for obj in ordered:
        surface = next((r for r in obj.realizations
                        if r.stream == "mathpix_lines" and r.role == "surface"
                        and r.start is not None), None)
        if surface is None:
            continue
        subs: list[Sub] = []
        for anchor in stream.slice_anchors(surface.start, surface.end):
            spans = spans_by_line.get(anchor)
            if not spans:
                continue
            text = _cspans.line_text(doc, anchor)
            for g in _cspans.groups(
                    text, spans,
                    on_out_of_bounds=lambda: res.counts.__setitem__(
                        "cite_spans_out_of_bounds",
                        res.counts["cite_spans_out_of_bounds"] + 1)):
                keys = tuple(g.payloads)
                subs.append(Sub(anchor=anchor, offset=g.start, length=g.length,
                                source=text[g.start:g.end],
                                replacement="\\cite{" + ",".join(keys) + "}",
                                keys=keys))
            reached.add(anchor)
        if subs:
            res.subs[obj.id] = subs
            res.counts["cite_groups"] += len(subs)
            res.counts["cite_keys"] += sum(len(s.keys) for s in subs)

    # 645-a, counted rather than left to be rediscovered: a citation on a line
    # no running-text object covers (a Footnote or Sidenote body) is never
    # substituted, because those bodies are emitted verbatim.
    res.counts["citations_outside_running_text"] = sum(
        len(ids) for anchor, ids in placed_lines.items() if anchor not in reached)
    return res


def apply_subs(text: str, subs: list[Sub], *,
               on_missing=None) -> str:
    """Apply `subs` to `text` by LITERAL search, in order, from a moving cursor.

    A group whose source substring is not in the text from the cursor on is
    SKIPPED and reported through `on_missing` — the object's materialised text
    and its lines disagree (a mutator rewrote it), and a positional edit against
    a text that moved replaces the wrong characters.
    """
    out: list[str] = []
    cursor = 0
    for s in subs:
        if not s.source:
            continue
        at = text.find(s.source, cursor)
        if at < 0:
            if on_missing is not None:
                on_missing(s)
            continue
        out.append(text[cursor:at])
        out.append(s.replacement)
        cursor = at + len(s.source)
    out.append(text[cursor:])
    return "".join(out)
