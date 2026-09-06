"""
CitationProcessor (procOrder 3).

Scans body text lines for `[citekey]` patterns (the MathPix convention for
citations) and creates Citation DocObjects. The realization for each citation
points to the line anchor in `mathpix_lines` PLUS offset/length props giving
the sub-line position. This avoids creating per-character anchors for the
entire body while still preserving exact location.

If you later promote body text to character-level anchors, the citation's
realization can be upgraded by replacing the offset/length props with explicit
start/end anchors — no surrounding structure has to change.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Alignment, Document, DocObject, Range, Realization


# Matches [citekey], where citekey contains letters, digits, _, - and contains
# no LaTeX backslashes (avoids picking up `\cite[opt]{key}` artifacts).
_CITE = re.compile(r"\[([A-Za-z0-9_\-,;:\s]+?)\]")

# Inline/display math spans. A `[...]` inside one of these is math (e.g.
# `\([A x, B x]\)` — an interval, MathPix's render of `[A_x, B_x]`), NOT a
# citation. Longest delimiters first so `$$` isn't split as `$..$`.
_MATH_SPAN = re.compile(
    r"\\\[[\s\S]*?\\\]"          # \[ ... \]
    r"|\$\$[\s\S]*?\$\$"         # $$ ... $$
    r"|\\\([\s\S]*?\\\)"         # \( ... \)
    r"|\$(?:[^$\n]|\\\$)*?\$"    # $ ... $
)


def _math_ranges(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _MATH_SPAN.finditer(text)]


def _in_math(pos: int, ranges: list[tuple[int, int]]) -> bool:
    return any(a <= pos < b for a, b in ranges)


def _is_valid_citekey(citekey: str) -> bool:
    """The TS heuristic, slightly relaxed for multi-citation comma lists."""
    if "\\" in citekey:
        return False
    if not citekey.strip():
        return False
    # Must contain at least one letter (so we skip [1], [2.3], pure-numeric refs
    # which are typically equation numbers handled elsewhere).
    if not re.search(r"[A-Za-z]", citekey):
        return False
    return True


def add_cites_alignment(doc: Document, left: Range, right: Range, props: dict) -> Optional[Alignment]:
    """010 fix round 2 — the one place a `cites` Alignment gets added, so
    `ensure_reference_stub` (below) and `bibliography.link_citations` can't
    both add the same edge. Skips (returns `None`) when an identical one --
    same `left`, same `right`, same `citekey` -- already exists.

    010 fix round 4 made the claim true rather than aspirational: every
    Citation->Reference edge in the codebase now comes through here --
    `ensure_reference_stub`, `bibliography.link_citations`,
    `bibliography.link_citations_by_label`, `absorb_stub` and
    `markdown_source.cite_objects`. (`annotations.link_xref_alignments` also
    emits `kind="cites"`, but its edges run Link->Citation on the `links`
    stream: a different relation that happens to share the kind name, not a
    second creator of this one.)

    `citekey` has to be part of that identity, not just `left`+`right`: a
    citation is anchored at LINE granularity (`start == end == the line's
    anchor`, sub-position tracked separately via `offset`/`length` props,
    not the Range), so two DIFFERENT citekeys parsed off the SAME line
    (`(Oja, 1989; Sanger, 1989)`) share one `left` Range -- and each gets
    its own brand-new stub anchored at THAT SAME line, so their `right`
    Ranges collide too. Deduping on `(left, right)` alone silently dropped
    10 of those as "already linked" when they were two distinct edges to
    two distinct References; `citekey` is what actually tells them apart.

    penev_A had 162 `cites` Alignments for 81 Citations before this fix:
    every citekey `ensure_reference_stub` had already linked at creation
    time got a SECOND, identical edge from `cmd_bibliography`'s
    unconditional `link_citations(doc)` call afterward.
    """
    key = props.get("citekey")
    for a in doc.alignments:
        if (a.kind == "cites" and a.left == left and a.right == right
                and a.props.get("citekey") == key):
            return None
    a = Alignment(kind="cites", left=left, right=right, props=props)
    doc.add_alignment(a)
    return a


def _surface_range(obj: DocObject) -> Optional[Range]:
    r = next((x for x in obj.realizations
              if x.role == "surface" and x.start is not None), None)
    if r is None:
        r = next((x for x in obj.realizations if x.start is not None), None)
    return Range(r.stream, r.start, r.end) if r is not None else None


def absorb_stub(doc: Document, stub: DocObject, into: DocObject,
                extra_props: Optional[dict] = None) -> int:
    """010 fix round 4 — MERGE a citation stub into the REAL Reference a linker
    just resolved its Citation to, and drop the stub.

    `ensure_reference_stub` links a Citation to a stub at creation time, by
    EXACT citekey. A linker that later resolves the same Citation by a
    different criterion -- the alpha `.bbl` label (`link_citations_by_label`:
    in-text `[ASV02]` -> gold `smith2002`), the reference NUMBER, or the fuzzy
    surname+year prefix (`link_citations`: `[Asai]` -> `Asai2023`) -- reaches a
    Reference that is NOT that stub. Adding its edge and walking away left the
    Citation with TWO edges to TWO References and the stub permanent (measured
    on the gold `.bbl` path). So: every `cites` edge that pointed at the stub
    is re-pointed at `into` (keeping `into`'s OWN anchor -- a gold Reference's
    `references`-stream anchor, not the citation prose line the stub borrowed),
    the moved edge's `citekey` becomes `into`'s so the linker's own
    `add_cites_alignment` call dedupes against it instead of adding a second,
    and the stub object is dropped.

    Only edges carrying the STUB's citekey are moved: a stub is anchored at its
    citation's LINE, so two stubs born on one line share a Range and `citekey`
    is the only thing that tells their edges apart (see `add_cites_alignment`).

    `extra_props` is merged onto each moved edge -- the calling linker's own
    edge props (e.g. `link_citations_by_label`'s `label`), which would
    otherwise be lost: the linker's follow-up `add_cites_alignment` dedupes
    against the moved edge and never gets to attach them.

    Returns the number of edges moved. A no-op (0) when `stub is into`, when
    `stub` is not a stub, or when it is already gone from the document.
    """
    if stub is into or stub.id not in doc.objects or not stub.props.get("stub"):
        return 0
    stub_range = _surface_range(stub)
    target = _surface_range(into)
    if stub_range is None or target is None:
        return 0
    key = stub.props.get("citekey")
    into_key = into.props.get("citekey")
    stale = [a for a in doc.alignments
             if a.kind == "cites" and a.right == stub_range
             and a.props.get("citekey") == key]
    if stale:                                   # detach BEFORE re-adding, so
        drop = {id(a) for a in stale}           # the new edge can't be deduped
        doc.alignments = [a for a in doc.alignments if id(a) not in drop]
    moved = 0
    for a in stale:
        props = dict(a.props)
        props.update(extra_props or {})
        props["citekey"] = into_key
        if add_cites_alignment(doc, a.left, target, props) is not None:
            moved += 1
    doc.objects.pop(stub.id, None)
    return moved


def ensure_reference_stub(doc: Document, citation: DocObject, bibkey: str) -> Optional[DocObject]:
    """010 — the spec's own words: "Create an empty Reference on first
    Citation". Called by EVERY Citation creator at the moment it creates a
    citation -- `CitationProcessor.create_object` below for `[key]`, and the
    three detectors in `pdfdrill.bibliography` for `[N]`, `(Author, Year)`
    and the stream-agnostic prose form -- so "first occurrence" falls out of
    creation order for free; no separate post-pass, no population this
    module can't see.

    Returns the Reference for `citation`'s citekey: an existing one (a stub
    from an earlier citation with the same key, or one already filled by
    `bibliography`/`bibsource`/`bibfetch`) if there is one, else a new stub
    (`stub: True`, `ref_source: "citation"`) anchored at THIS citation's own
    surface Realization. Either way `citation` is linked to it via a `cites`
    Alignment (`bibliography.link_citations`'s edge shape), so every Citation
    ends up linked without a relink pass. `bibliography.py`'s three Reference
    creators fill a stub in place (same id, same anchor) rather than
    creating a second Reference for the same key.

    Returns None (does nothing) if `citation` carries no citekey or no
    surface Realization -- there'd be nothing to anchor a new stub at.
    """
    key = citation.props.get("citekey")
    if not key:
        return None
    c_surface = next((r for r in citation.realizations if r.role == "surface"), None)
    if c_surface is None:
        return None

    ref = next((r for r in doc.objects_of_type("Reference")
               if r.props.get("citekey") == key), None)
    if ref is None:
        # 010 fix round 3 -- the stub's `added_by` is the CITATION's, so a
        # cleanup gate that retracts "everything a command added" (by
        # `added_by`) retracts a bibliography-detected citation and the
        # stub made for it TOGETHER, and never touches a stub whose
        # citation came from CitationProcessor (model build): that one has
        # no `added_by` of its own, so the stub's is the literal marker
        # "citation" instead.
        ref_props = {
            "citekey": key, "bibkey": bibkey, "stub": True, "ref_source": "citation",
            "added_by": citation.props.get("added_by") or "citation",
        }
        # 639 -- the author-year detectors (`detect_author_year_citations`,
        # `detect_author_year_in_objects`) already parsed `author`/`year` off
        # the citing text to BUILD the citekey (`f"{surname}{year}"`); that is
        # data the citation carries, not a guess, so a fresh stub inherits it
        # instead of sitting on empty fields until bibsource/bibfetch runs.
        for k in ("author", "year"):
            v = citation.props.get(k)
            if v:
                ref_props[k] = v
        ref = DocObject(type="Reference", props=ref_props)
        ref.add_realization(Realization(
            stream=c_surface.stream, start=c_surface.start, end=c_surface.end,
            role="surface",
        ))
        doc.add(ref)

    ref_surface = next((r for r in ref.realizations if r.role == "surface"), None)
    if ref_surface is not None:
        # Same edge shape as `bibliography.link_citations`'s own edges
        # (`citekey` + `number`, `number` omitted when the citation has none)
        # so a consumer reading either can't tell which pass made the edge.
        props = {"citekey": key}
        if citation.props.get("number") is not None:
            props["number"] = citation.props["number"]
        add_cites_alignment(
            doc,
            Range(c_surface.stream, c_surface.start, c_surface.end),
            Range(ref_surface.stream, ref_surface.start, ref_surface.end),
            props,
        )
    return ref


class CitationProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        items: list[dict[str, Any]] = []

        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            if payload.get("type") not in ("text", "title"):
                continue
            text = payload.get("text_display") or payload.get("text") or ""
            if not text:
                continue
            math = _math_ranges(text)
            for match in _CITE.finditer(text):
                # A `[...]` inside a math span is an interval/set, not a cite.
                if _in_math(match.start(), math):
                    continue
                key = match.group(1).strip()
                if not _is_valid_citekey(key):
                    continue
                # The pattern may be a comma-separated list (e.g. [smith,jones]).
                # We create one Citation per key; their realizations all point
                # to the same anchor + sub-range.
                offsets = self._split_offsets(key, match)
                for sub_key, sub_off, sub_len in offsets:
                    items.append({
                        "citekey": sub_key,
                        "anchor": anchor,
                        "offset": sub_off,
                        "length": sub_len,
                        "page": payload.get("_page"),
                        "line_id": payload.get("id"),
                    })
        return items

    @staticmethod
    def _split_offsets(group_text: str, match: re.Match) -> list[tuple[str, int, int]]:
        """Split a citation group `[a, b, c]` into individual (key, off, len)."""
        out: list[tuple[str, int, int]] = []
        base = match.start() + 1  # skip past '['
        cursor = 0
        for raw_part in group_text.split(","):
            stripped = raw_part.strip()
            if not stripped or "\\" in stripped:
                cursor += len(raw_part) + 1  # +1 for the comma we ate
                continue
            # find stripped's offset within raw_part
            lead = len(raw_part) - len(raw_part.lstrip())
            out.append((stripped, base + cursor + lead, len(stripped)))
            cursor += len(raw_part) + 1
        return out

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        obj = DocObject(
            type="Citation",
            props={
                "citekey": item["citekey"],
                "page": item["page"],
                "bibkey": self.bibkey,
            },
        )
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface",
            props={
                "offset": item["offset"],   # sub-anchor character position
                "length": item["length"],
            },
        ))
        self.bump("citations_created")

        # 010 — a Reference stub at first citation. `ensure_reference_stub`
        # returns the existing Reference for this key (stub or filled) or
        # creates one; we only know a NEW stub was made when there was no
        # Reference for the key a moment ago, so the counter still means
        # exactly what it always has.
        had_ref = any(r.props.get("citekey") == item["citekey"]
                      for r in doc.objects_of_type("Reference"))
        ensure_reference_stub(doc, obj, self.bibkey)
        if not had_ref:
            self.bump("reference_stubs_created")
        return obj
