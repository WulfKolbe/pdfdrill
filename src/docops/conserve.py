r"""646 — THE CONSERVATION CHECK. No content lost, none mixed up.

That is the whole claim the extraction pipeline makes, and until this module
nothing tested it. `pdfdrill conserve <pdf>` is READ-ONLY: it makes the
failure visible and fixes nothing.

TWO INDEPENDENT QUESTIONS, ONE PER DIRECTION OF THE PIPELINE
------------------------------------------------------------
REACHABILITY (the OUTPUT side).  Every DocObject must arrive in the emitted
projection under exactly one parent. The emitted projection is the TiddlyWiki
array — the projector every other projector takes its identity from — built
IN MEMORY from the Document, never read from disk (a file on disk can be
stale, and a conservation check that measures a stale artefact measures
nothing).

CLAIMS (the INPUT side; 634 measures the same surface from the other end).
Every `mathpix_lines` anchor — one OCR line — must land in exactly one
object. A line no object covers is content the model dropped; a line two
objects both cover is content the model mixed up (the "footnote body carries
its neighbour's text" class).

REACHABILITY IS A WALK, NOT A SCAN
----------------------------------
`reachability` runs a BFS from the roots. Asking only "is this title named
anywhere?" — which is what fix round 1 replaced — calls an island of two
tiddlers that transclude each other reachable, and calls every paragraph
under an unreachable section reachable. Neither is in the document.

THE ROOTS, as `TiddlyWikiProjector._emit_tiddlers` writes them: the DOCUMENT
tiddler (titled with the bibkey, tagged `document`), whose body lists every
top-level section, and the TOC INDEX `<bibkey>_TOC` (tagged `toc`), the
rebuilt fractal xref whose rows list every captioned section (262). The
`template` tiddlers are scaffolding; none of the three is an object's
tiddler, so none enters the object population.

A PARENT is a CONTENT TRANSCLUSION `{{title}}` / `{{title||TPL}}` in some
REACHED tiddler's text. That is the only containment edge TiddlyWiki has:
the section body emits one per child block, the paragraph text one per
inline formula/citation/footnote marker.

A LISTING carries the walk downwards but is never a parent: the root's and
the TOC's `- <$link to="H">`, and a section's
`- <$link to="S">{{S!!caption}}</$link>`. The root and the TOC each list
EVERY section, so counting a listing as a parent would report every section
in every document as multi-parent. `<$link to="…">` with a literal title is
followed only out of a `document`, `toc` or `section` tiddler — the only
three places the projector emits that form; a `\ref`-resolved `<$link>`
lives in a section's `caption` FIELD, never in `text`, so a cross-reference
cannot parent anything.

MULTI-PARENT IS NOT ALWAYS A DEFECT. Transclusion exists so that one formula
is stored once and referenced N times (docs/TRANSCLUSION.md). For Formula and
Reference, 2+ parents is the design working. For Paragraph, Table, Picture,
ListItem it is duplication. The count is reported PER TYPE so the reader can
tell the two apart rather than being handed one number that mixes them.

TWO DEVIATIONS FROM THE BRIEF'S LITERAL DEFINITIONS, WITH REASONS
-----------------------------------------------------------------
1. THE WALK (above). The brief says "reachable when the tiddler ... is named
by exactly one transclusion in some OTHER tiddler's text, walking down from
the roots". The two halves of that sentence disagree when a naming tiddler is
itself unreached, and the walk is what the definition is FOR, so the walk
wins: `unreachable` = the object's tiddler was never reached, `multi_parent`
= reached from 2+ distinct reached parents. Each entry carries `named_by`,
the count a flat scan would have reported, so nothing is hidden by the
choice.

2. CONTAINER_TYPES. The brief defines a claim as a `surface` realization on `mathpix_lines`
whose [start, end] contains the anchor and which carries no sub-anchor
offset/length. Read literally that makes a Page a claimant: `PageProcessor`
gives every Page a surface realization spanning every line of the page, so
EVERY anchor would be claimed by its Page plus its real owner and the
doubly-claimed count would equal the anchor count. A measure that reports
3178 of 3178 says nothing. `CONTAINER_TYPES` names the types whose range is
a container by construction rather than a claim on content; they are listed
in the result under `containers_excluded` so the exclusion is visible in the
output, not hidden in the code. It holds `Page` ALONE: `List` was in it until
fix round 1 and excluded nothing, because `cmd_lists` builds a List DocObject
with no realization of any kind — an exclusion asserting a shape that does
not exist is worse than no exclusion, since a reader takes it for a measured
fact.

656 — CONSERVE BECOMES A GATE
------------------------------
A transclusion audit (2026-09) found that `conserve` already catches every
one of seven object types (Theorem, Proof, CodeListing, Algorithm,
AlgorithmStep, List, Link — and, measured here, MathTail) that never reach
the reader, and that nothing runs it: `cmd_conserve` was read-only, opt-in,
and untested against the corpus. A full corpus scan (1,362 models) for this
task found an EIGHTH: `Citation` fails the identical structural test (no row
in `TITLE_SHAPES` at all — the same mechanism as the other eight, not the
"marker rewritten to a REF transclusion" story the audit weighed and
declined to resolve) — see `BY_DESIGN`'s own docstring below. It also found
that the same corpus carries a much longer tail of OTHER unreachable types
(Formula, Paragraph, Equation, ...) whose rate is nowhere near 100% — a
working path with catalogued incidental gaps (645/646's own follow-ups),
not a missing one; `OUT_OF_SCOPE` names them and why they are not this
gate's business.

This module gains `BY_DESIGN` (the reachability-side twin of
`CONTAINER_TYPES`, same standard: name the route, verify it, or don't list
it), `OUT_OF_SCOPE` (a working path, explicitly not ratcheted here),
`gate()` (a RATCHET against a checked-in baseline of known violation counts
— `conserve_baseline.json`, DATA not code) and `format_gate_report()`. None
of this makes the nine violation types reachable — that is a separate,
larger task — it makes their absence, and any FUTURE absence or new type,
impossible to pass silently.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

from docmodel.core import Document

#: Types whose `mathpix_lines` surface range is a CONTAINER, not a claim.
#: A Page's `surface` realization spans every line of the page by
#: construction (`docmodel.modules.page`), so counting it as a claim makes
#: every anchor doubly claimed. Only types that ACTUALLY carry such a
#: realization belong here: `List` was in this tuple until fix round 1 and
#: was inert — `cmd_lists` creates a List DocObject with no realization at
#: all, so the exclusion excluded nothing and asserted a shape that does not
#: exist.
CONTAINER_TYPES = ("Page",)

# =========================================================================
# 656 — THE GATE. CONTAINER_TYPES (above) answers "does this type CLAIM a
# line" for the anchors half; BY_DESIGN answers the same question one level
# up, for REACHABILITY: which object types are ALLOWED to have no tiddler
# (or no reached tiddler) because their content demonstrably reaches the
# reader some other, verified way — as opposed to a type that is simply
# dropped and happens not to have been caught yet.
#
# THE STANDARD IS THE ONE `CONTAINER_TYPES` ALREADY SETS: an entry states the
# ROUTE the content takes and where that route was VERIFIED, not that the
# type "doesn't matter". `List` sat in `CONTAINER_TYPES` for exactly one
# round, asserted nothing, and was removed — the same fate awaits any entry
# here that stops being true. `Citation` is the sharpest case this repo has
# for what does NOT qualify: its marker is rewritten to a `{{REF||CIT}}`
# transclusion, so a citation's PRESENCE is felt in the page, but the
# Citation DocObject's own printed text is replaced, not carried — the
# transclusion-audit (2026-09) named this "arguably correct by design" and
# explicitly declined to resolve it. Not substantiated, not listed here:
# `Citation` is a VIOLATION type in the baseline below, like every other
# unreachable type nobody has proven a route for.
BY_DESIGN: dict[str, str] = {
    "Page": "addressed by FIELD (`page`/`page_number` on the objects that "
            "sit on it), never transcluded: `PAGE` has no entry in "
            "`TEMPLATES` or `BLOCK_TEMPLATE` at all "
            "(docops/projectors/tiddlywiki.py) — there is no shape for a "
            "Page tiddler to take. Navigational addressing, not content.",
    "TableCell": "folded into the parent Table's `raw_text` "
                 "(docmodel/modules/table.py:61 joins every child "
                 "cell/row's own `text`); the Table's own tiddler carries "
                 "that text whenever no SVG/cdn image is rendered instead. "
                 "Verified corpus-wide (transclusion-audit.md Q2): 0 of "
                 "12,094 Table objects have BOTH a populated `raw_text` AND "
                 "a rendered image that would shadow it — the case where a "
                 "cell's text would actually be lost never occurs.",
    "TableRow": "same mechanism, same corpus-wide verification as "
                "TableCell.",
    "Toc": "deliberately never emitted (262): the outline is REBUILT as the "
           "`<bibkey>_TOC` fractal index straight from the Section tree "
           "(tiddlywiki.py `_emit_tiddlers`, the '262' block), and that "
           "rebuilt index is one of `reachability`'s own two ROOTS — the "
           "walk already depends on the substitution existing. A frozen "
           "Toc tiddler would duplicate it and go stale the moment a "
           "section is retitled or renumbered.",
    "Document": "the model's own `Document` DocObject (`docmodel/modules/"
                "document_structure.py`'s `_create_document_root`, id=bibkey) "
                "is a SUMMARY container: `total_pages`/`total_sections`/"
                "`total_paragraphs`/`first_section_id` are corpus-verified "
                "unread fields (`docmodel.prop_contract.NO_READER_REASON` — "
                "\"consumers walk the flow instead\"/\"count the objects "
                "instead\"), and its real structural role (listing every "
                "top-level section) is independently duplicated by the "
                "PROJECTOR'S OWN root tiddler (tiddlywiki.py, title=bibkey, "
                "built from `doc.meta` + `inv[\"sections\"]`, not from this "
                "DocObject at all — `reachability`'s other ROOT). Measured "
                "corpus-wide at 100% unreachable (1358 of 1358, 1358 of 1358 "
                "documents) — the identical rate BY_DESIGN's other four "
                "entries show, for the identical reason: a second root "
                "already carries what this object would.",
}

#: 656 (fix round 1) — types explicitly OUT OF SCOPE for the ratchet below:
#: each has a WORKING code path that reaches most instances (measured
#: corpus-wide well under 100%, unlike BY_DESIGN's and the baseline's own
#: types, which sit at ~100% for a provable structural reason), and its
#: nonzero count is an INCIDENTAL, already-catalogued gap — not a missing
#: path. Round 0 gave all 13 ONE shared reason string; a review correctly
#: called that an unverified blanket exemption ("exactly how a real drop
#: hides") and spot-checked 4 of 13. This round individually verified the
#: remaining 9 against source and found FIVE distinct mechanisms, not one —
#: grouped below by mechanism (types sharing one literal code path share one
#: literal explanation, the same convention `BY_DESIGN["TableRow"]` already
#: uses for `TableCell`), never by assumption.
#:
#: (A) BLOCK-LEVEL: a direct Section child, transcluded once per child by
#: `_section_body` when the child's type is in `_BLOCK_TYPES_IN_SECTION`
#: (`tiddlywiki.py:686-688`, the loop at `:1698-1730`). GAP: an ORPHAN
#: SUBTREE — the parent Section itself unreached, or the object never
#: placed in any Section's `children` at all — exactly what
#: `test_conserve.py`'s own passing (g) proves
#: (`test_g_a_paragraph_under_an_unreachable_section_is_unreachable`) and
#: what 646-g/646-j found on real documents (kolbe2018hubbard's empty-
#: caption subsections; penev_B's 15 page-1 paragraphs in no Section's
#: children).
_BLOCK_LEVEL_REASON = (
    "a direct Section child, transcluded once per child by `_section_body` "
    "when its type is in `_BLOCK_TYPES_IN_SECTION` (tiddlywiki.py:686-688, "
    "the loop at :1698-1730) — VERIFIED by reading that loop. GAP: an "
    "orphan subtree, either the parent Section itself unreached or the "
    "object never placed in any Section's `children` — the exact shape "
    "test_conserve.py's own passing (g) proves "
    "(test_g_a_paragraph_under_an_unreachable_section_is_unreachable), and "
    "646-g/646-j's real-document instances.")

#: (B) INLINE PER-LINE SUBSTITUTION: a `{{title||FO}}` / `{{title||CIT}}`
#: replacement built by `_build_inline_subs` (`tiddlywiki.py:860-950`) into
#: `subs_by_line`, applied ONLY inside `_transclude_paragraph`
#: (`:1518-1560`, the sole `subs_by_line.get(anchor, [])` call site,
#: `:1558`) — VERIFIED: grepped for every use of `subs_by_line`, found one.
#: GAP: the SAME orphan subtree as (A) one level down (the hosting
#: Paragraph unreached); the anchor outside every Paragraph's `surface`
#: range at all (646-d's dark Contents-page Formulas — the Toc object
#: claims those lines, no Paragraph does); or the object's own body copied
#: verbatim by a NON-Paragraph emitter that never calls
#: `_transclude_paragraph` at all (a Footnote/Sidenote/Abstract's content —
#: 645-a: "no formula and no citation inside a footnote... has EVER become
#: a transclusion, on any document"). Reference ALSO loses a span outright
#: when `bibliography.py`'s detectors cannot anchor a citation group on its
#: own line (645's `spans_unrecorded` counter, `cmd_bibliography` prints
#: it) — a citation with no span gets no stub and no substitution.
_INLINE_SUBLINE_REASON = (
    "a `{{title||FO}}`/`{{title||CIT}}` replacement built into "
    "`subs_by_line` by `_build_inline_subs` (tiddlywiki.py:860-950), "
    "applied ONLY inside `_transclude_paragraph` (:1518-1560, the sole "
    "`subs_by_line.get(anchor, [])` call site, :1558 — VERIFIED, grepped "
    "for every use). GAP: the same orphan-Paragraph subtree as the "
    "block-level types, one level down; the anchor outside every "
    "Paragraph's surface range (646-d's dark Contents-page Formulas, "
    "claimed only by a Toc object); the body copied verbatim by a "
    "non-Paragraph emitter that never calls `_transclude_paragraph` at all "
    "(a Footnote/Sidenote/Abstract's own content — 645-a); or, for "
    "Reference specifically, a citation group `bibliography.py` could not "
    "anchor on its own line at all (645's `spans_unrecorded`) — no span, "
    "no stub, no substitution.")

#: (C) FOOTNOTE MARKER MATCH: `_substitute_footnotes` (`tiddlywiki.py:1614`,
#: called from `_transclude_paragraph:1562`) is a REGEX match on the
#: paragraph's joined text against `fn_by_refnum` — a DIFFERENT mechanism
#: from (B)'s offset index (VERIFIED: `_substitute_footnotes` never touches
#: `subs_by_line`). GAP: the marker pattern never matched in any paragraph
#: — 645-a's own headline finding, and the largest single OUT_OF_SCOPE
#: percentage measured here (Footnote 89.5%) is exactly this.
_FOOTNOTE_MARKER_REASON = (
    "`_substitute_footnotes` (tiddlywiki.py:1614, called from "
    "_transclude_paragraph:1562) is a REGEX match on the paragraph's "
    "joined text against `fn_by_refnum` — a DIFFERENT mechanism from "
    "Formula/Reference's offset index (VERIFIED: `_substitute_footnotes` "
    "never touches `subs_by_line`). GAP: the marker pattern never matched "
    "in any paragraph — 645-a's own headline finding; measured here at "
    "89.5% unreachable, the largest OUT_OF_SCOPE percentage of the "
    "thirteen, which is exactly this failure mode dominating.")

#: (D) BUILD-TIME BAKED MARKER: `{{title||LTX}}` is written straight into
#: the hosting text's OWN `props["text"]` at LaTeX-ingestion time
#: (`latex_source._capture_ltx`), before the model even exists — NOT a
#: `tiddlywiki.py` runtime substitution (VERIFIED: grepped `tiddlywiki.py`
#: for any `subs_by_line`/dedicated-loop entry for `ltx`; found none — only
#: unconditional per-object TITLE assignment, `:851`, and unconditional
#: tiddler emission, `:1298-1302`, both already the reviewer's own
#: spot-check). GAP: the same orphan-subtree mechanism as (A)/(B), inherited
#: transitively from wherever the leaked command landed.
_LTX_BAKED_REASON = (
    "`{{title||LTX}}` is written straight into the hosting text's OWN "
    "`props[\"text\"]` at LaTeX-ingestion time "
    "(pdfdrill.latex_source._capture_ltx), before the model even exists — "
    "NOT a tiddlywiki.py runtime substitution at all (VERIFIED: grepped "
    "tiddlywiki.py for any subs_by_line/dedicated-loop entry naming ltx; "
    "found only the unconditional per-object title assignment, :851, and "
    "unconditional tiddler emission, :1298-1302). GAP: the same "
    "orphan-subtree mechanism as the block-level/inline types above, "
    "inherited transitively from wherever the leaked command landed.")

#: (E) SECTION LISTING: a Section is not content-transcluded at all — it is
#: LISTED, either by the root/TOC (every top-level captioned section) or by
#: a parent Section's own "## Subsections" list (`_section_body`,
#: `tiddlywiki.py:1736-1740`). GAP: an orphan subtree, the exact shape
#: `test_conserve.py`'s own passing (g) proves.
_SECTION_LISTING_REASON = (
    "not content-transcluded at all — it is LISTED, either by the root/TOC "
    "(every top-level captioned section) or by a parent Section's own "
    "\"## Subsections\" list (_section_body, tiddlywiki.py:1736-1740). GAP: "
    "an orphan subtree, the exact shape test_conserve.py's own passing (g) "
    "proves (test_g_a_paragraph_under_an_unreachable_section_is_unreachable"
    ").")

OUT_OF_SCOPE: dict[str, str] = {
    **{t: _BLOCK_LEVEL_REASON for t in
       ("Paragraph", "Equation", "Table", "Picture", "Diagram", "ListItem",
        "Abstract", "Sidenote")},
    **{t: _INLINE_SUBLINE_REASON for t in ("Formula", "Reference")},
    "Footnote": _FOOTNOTE_MARKER_REASON,
    "LtxCommand": _LTX_BAKED_REASON,
    "Section": _SECTION_LISTING_REASON,
}

#: 656 — the checked-in RATCHET. {bibkey: {type: count}}, the exact
#: unreachable-object count `conserve()` measured for that document's
#: VIOLATION types (types in neither BY_DESIGN nor OUT_OF_SCOPE) the last
#: time the baseline was reviewed. Data, not code — reviewing "did a count
#: change" is a diff of numbers, not a code review. See `gate()`.
BASELINE_PATH = Path(__file__).with_name("conserve_baseline.json")

_TRANSCLUDE = re.compile(r"\{\{([^{}]+?)\}\}")
_LINK_TO = re.compile(r"<\$link\s+to=\"([^\"]+)\"")

_MAX_EXAMPLES = 10


def _sanitize_title(t: str) -> str:
    """The projector's own title sanitiser — the title map holds the RAW
    title, the emitted tiddler holds the sanitised one, and comparing the two
    unsanitised is how a check silently reports everything unreachable."""
    return re.sub(r"[^A-Za-z0-9_\-\.]", "_", t or "")


def _tags(t: dict) -> list[str]:
    return (t.get("tags") or "").split()


def _excerpt(s: Any, n: int = 60) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[:n - 1] + "…"


# --------------------------------------------------------------- projection

def project_in_memory(doc: Document) -> tuple[list[dict], dict[str, str], str]:
    """Build the TiddlyWiki projection from the Document IN MEMORY.

    Returns (tiddlers, title-by-object-id, bibkey). Nothing is read from or
    written to disk: the artefact on disk may be stale, and 646 audits what
    the model WOULD project today.
    """
    import json

    from docops.base import OperatorConfig
    from docops.projectors.tiddlywiki import TiddlyWikiProjector

    bibkey = doc.meta.get("bibkey", "DOC")
    proj = TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector"))
    tiddlers = json.loads(proj.project(doc))
    titles, _inv = proj._assign_titles(doc, bibkey)
    return tiddlers, titles, bibkey


# ------------------------------------------------------------- reachability

def _edges(text: str, src: str, follow_links: bool) -> tuple[set[str], set[str]]:
    """(content children, listing children) named by one tiddler's text.

    CONTENT — `{{T}}` / `{{T||TPL}}`: containment, and the only thing that
    makes `src` a PARENT of T.
    LISTING — `{{T!!field}}` (a section's subsection list transcludes the
    subsection's caption field) and `<$link to="T">`. Navigation: it carries
    the walk downwards but confers no parenthood, because the root and the
    TOC index each list every section and one-to-many is their whole job.
    `{{!!field}}` addresses the current tiddler and names nobody.
    """
    content: set[str] = set()
    listing: set[str] = set()
    for m in _TRANSCLUDE.finditer(text):
        inner = m.group(1).strip()
        if inner.startswith("!!"):
            continue
        head = inner.split("||")[0]
        target = head.split("!!")[0].strip()
        if not target or target == src:
            continue
        (listing if "!!" in head else content).add(target)
    if follow_links:
        for m in _LINK_TO.finditer(text):
            t = m.group(1).strip()
            if t and t != src:
                listing.add(t)
    return content, listing


def reachability(doc: Document, tiddlers: list[dict],
                 titles: dict[str, str]) -> dict:
    """Every DocObject reached from exactly one parent, WALKING FROM THE ROOTS.

    THIS IS A BFS, NOT A SCAN. "Is this title named anywhere?" counts an
    island of two tiddlers that transclude each other as reachable, and
    counts every paragraph under an unreachable section as reachable. Both
    are content that is not in the document. So the walk starts at the roots
    the projector actually emits and only what it reaches is reachable.

    THE ROOTS, as `TiddlyWikiProjector._emit_tiddlers` writes them:
      * the DOCUMENT tiddler — titled with the bibkey, tagged `document`,
        whose body lists every TOP-LEVEL section as `- <$link to="H">cap`;
      * the TOC INDEX `<bibkey>_TOC` — tagged `toc`, the rebuilt fractal
        xref, whose rows list EVERY captioned section the same way (262).
    From a section the walk continues through its body: one content
    transclusion per child block (`{{P||PARA}}`, `{{E||EQ}}`, …) and
    `- <$link to="S">{{S!!caption}}` per subsection. From a paragraph it
    continues through the inline markers baked into its text
    (`{{F||FO}}`, `{{R||CIT}}`, `{{N||FN}}`).

    `<$link to="…">` with a literal title is followed only out of the root,
    a `toc` tiddler and a `section` tiddler — the only three places the
    projector emits that form (root body, TOC rows, the `## Subsections`
    list). A `\ref`-resolved `<$link>` lives in a section's `caption` FIELD,
    never in `text`, so it is not an edge here and a cross-reference cannot
    parent anything.

    `unreachable` — the object's tiddler was never reached: `reason`
    "no tiddler" when the projector emits nothing at all for it, else
    "not reached". `named_by` says how many tiddlers name it REGARDLESS of
    whether they were reached, so "nothing names it" and "only unreached
    things name it" are distinguishable in the output.
    `multi_parent` — content-transcluded by 2+ distinct REACHED tiddlers.
    """
    bibkey = doc.meta.get("bibkey", "DOC")
    root_title = _sanitize_title(bibkey)
    by_title_tiddler = {t.get("title"): t for t in tiddlers}
    emitted = set(by_title_tiddler)

    roots = [root_title] if root_title in emitted else []
    roots += sorted(t.get("title") for t in tiddlers
                    if "toc" in _tags(t) and t.get("title") != root_title)

    # Every naming, reached or not — the number a flat scan would report.
    named_by: Counter = Counter()
    for t in tiddlers:
        c, l = _edges(t.get("text") or "", t.get("title"), follow_links=True)
        for tgt in c | l:
            named_by[tgt] += 1

    # THE WALK.
    parents: dict[str, set[str]] = defaultdict(set)
    reached: set[str] = set(roots)
    queue: deque = deque(roots)
    while queue:
        src = queue.popleft()
        t = by_title_tiddler.get(src)
        if t is None:
            continue
        follow = bool({"document", "toc", "section"} & set(_tags(t))) \
            or src == root_title
        content, listing = _edges(t.get("text") or "", src, follow)
        for tgt in content:
            if tgt in emitted:
                parents[tgt].add(src)          # only REACHED sources parent
                if tgt not in reached:
                    reached.add(tgt)
                    queue.append(tgt)
        for tgt in listing:
            if tgt in emitted and tgt not in reached:
                reached.add(tgt)
                queue.append(tgt)

    # Two objects that share ONE tiddler title are one object in the
    # projection: content is not lost but it IS mixed up, and neither of the
    # three headline counts can see it (the title is reached exactly once).
    by_title: dict[str, list] = defaultdict(list)
    for o in doc.objects.values():
        raw = titles.get(o.id)
        if raw:
            by_title[_sanitize_title(raw)].append(o)
    collisions = [
        {"title": t, "objects": [{"id": o.id, "type": o.type,
                                  "text": _excerpt(_describe(o), 40)}
                                 for o in objs]}
        for t, objs in sorted(by_title.items()) if len(objs) > 1]

    unreachable: list[dict] = []
    multi_parent: list[dict] = []
    by_type: dict[str, dict[str, int]] = {}
    for obj in doc.objects.values():
        bucket = by_type.setdefault(
            obj.type, {"objects": 0, "unreachable": 0, "multi_parent": 0})
        bucket["objects"] += 1
        raw = titles.get(obj.id)
        title = _sanitize_title(raw) if raw else None
        page = obj.props.get("page") or obj.props.get("page_number")
        if not title or title not in emitted:
            bucket["unreachable"] += 1
            unreachable.append({"id": obj.id, "type": obj.type,
                                "title": title, "reason": "no tiddler",
                                "named_by": named_by.get(title, 0) if title else 0,
                                "page": page,
                                "text": _excerpt(_describe(obj))})
            continue
        if title not in reached:
            bucket["unreachable"] += 1
            unreachable.append({"id": obj.id, "type": obj.type,
                                "title": title, "reason": "not reached",
                                "named_by": named_by.get(title, 0),
                                "page": page,
                                "text": _excerpt(_describe(obj))})
            continue
        ps = sorted(parents.get(title, ()))
        if len(ps) > 1:
            bucket["multi_parent"] += 1
            multi_parent.append({"id": obj.id, "type": obj.type,
                                 "title": title, "parents": ps,
                                 "named_by": named_by.get(title, 0),
                                 "page": page,
                                 "text": _excerpt(_describe(obj))})

    return {
        "objects": len(doc.objects),
        "tiddlers": len(tiddlers),
        "roots": roots,
        "reached": len(reached),
        "templates": sum(1 for t in tiddlers if "template" in _tags(t)),
        "unreachable": unreachable,
        "multi_parent": multi_parent,
        "collisions": collisions,
        "by_type": by_type,
    }


def _round_robin(entries: list[dict], limit: int) -> list[dict]:
    """Up to `limit` examples, one per type in turn.

    A flat head() of this list is all Pages on a real document, and a reader
    handed ten identical rows learns nothing about the other ten classes.
    """
    by: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        by[e["type"]].append(e)
    out: list[dict] = []
    while len(out) < limit and any(by.values()):
        for t in sorted(by):
            if by[t] and len(out) < limit:
                out.append(by[t].pop(0))
    return out


def _describe(obj) -> str:
    """The most identifying string an object carries, for a named example."""
    p = obj.props
    for k in ("text", "latex", "caption", "content", "raw_text", "citekey",
              "statement", "title"):
        if p.get(k):
            return str(p[k])
    return ""


# --------------------------------------------------------------- claims

def anchor_claims(doc: Document, stream: str = "mathpix_lines") -> dict:
    """Every anchor of `stream` claimed by exactly one object?

    A CLAIM is a `surface` Realization on the stream whose [start, end] range
    contains the anchor and which carries NO sub-anchor offset/length — an
    inline object (Formula, Citation, footnote marker) lives inside a line
    and does not claim it. `CONTAINER_TYPES` are excluded; see the module
    docstring for why, and `containers_excluded` in the result.
    """
    st = doc.streams.get(stream)
    if st is None or not st.anchors:
        return {"stream": stream, "total": 0, "unclaimed": [],
                "doubly_claimed": [], "pairs": Counter(),
                "containers_excluded": list(CONTAINER_TYPES),
                "claims": 0, "inline_skipped": 0}

    claims: dict[Any, list] = defaultdict(list)
    inline = 0
    for obj in doc.objects.values():
        if obj.type in CONTAINER_TYPES:
            continue
        for r in obj.realizations:
            if r.stream != stream or r.role != "surface" or r.start is None:
                continue
            if isinstance(r.props.get("offset"), int) \
                    and isinstance(r.props.get("length"), int):
                inline += 1                      # lives INSIDE a line
                continue
            end = r.end if r.end is not None else r.start
            try:
                span = st.slice_anchors(r.start, end)
            except KeyError:                     # an anchor from another doc
                continue
            for a in span:
                claims[a].append(obj)

    unclaimed: list[dict] = []
    doubly: list[dict] = []
    pairs: Counter = Counter()
    for i, a in enumerate(st.anchors):
        got = claims.get(a)
        pay = st.payload.get(a, {})
        if not got:
            unclaimed.append({
                "anchor": a.id, "index": i,
                "page": pay.get("_page") or pay.get("page"),
                "line_type": pay.get("type"),
                "text": _excerpt(pay.get("text") or pay.get("_text")),
            })
        elif len(got) > 1:
            types = tuple(sorted(o.type for o in got))
            pairs[types] += 1
            doubly.append({
                "anchor": a.id, "index": i,
                "page": pay.get("_page") or pay.get("page"),
                "line_type": pay.get("type"),
                "text": _excerpt(pay.get("text") or pay.get("_text")),
                "types": list(types),
                "claimants": [{"id": o.id, "type": o.type,
                               "text": _excerpt(_describe(o), 40)}
                              for o in got],
            })

    return {"stream": stream, "total": len(st.anchors),
            "unclaimed": unclaimed, "doubly_claimed": doubly, "pairs": pairs,
            "containers_excluded": list(CONTAINER_TYPES),
            "claims": sum(len(v) for v in claims.values()),
            "inline_skipped": inline}


# --------------------------------------------------------------- the check

def conserve(doc: Document) -> dict:
    """Run the projector in memory and both checks. JSON-safe result.

    `dark_anchors` joins the two halves: a line whose every claimant is an
    unreachable object is claimed — so neither headline count sees it — and
    still reaches no tiddler. penev_A's 291-line Contents region is that
    shape: one Toc object covers it, and the projector emits nothing for a
    Toc (262), so the whole region is dark.
    """
    tiddlers, titles, bibkey = project_in_memory(doc)
    reach = reachability(doc, tiddlers, titles)
    claims = anchor_claims(doc)
    counts = {
        "unreachable": len(reach["unreachable"]),
        "unclaimed": len(claims["unclaimed"]),
        "doubly_claimed": len(claims["doubly_claimed"]),
    }
    dark = _dark_anchors(doc, reach, claims)
    claims = dict(claims)
    claims["pairs"] = [{"types": list(k), "count": v}
                       for k, v in claims["pairs"].most_common()]
    claims["dark"] = dark
    return {
        "bibkey": bibkey,
        "counts": counts,
        "conserved": not any(counts.values()),
        "reachability": reach,
        "anchors": claims,
        # 636's two refusals. They are NOT folded into `conserved` — they are
        # decisions the split made about content it kept, not content lost —
        # but a reader of the conservation report is the reader who wants
        # them, and they were written to the model and read by nothing.
        "footnote_refusals": {
            "orphan_tail": int(doc.meta.get("footnote_orphan_tail") or 0),
            "span_not_located": int(doc.meta.get("footnote_span_not_located") or 0),
            # 637 — not a refusal but the same kind of fact: how many bodies the
            # cleanup filled into a Footnote that already existed rather than
            # creating a second object for.
            "adopted": int(doc.meta.get("footnote_adopted") or 0),
            # 650 review round 3, finding 6 — a footnote-shortened Paragraph
            # whose surviving text `_narrow_surface_to_remaining` could NOT
            # map to an exact whole-line suffix/prefix of the original
            # (e.g. a sub-line fragment left by the footnote's own
            # tail-consumption): the `surface` Realization is left wide and
            # `footnote_extracted` gates rendering instead, at the cost of
            # that paragraph's own transclusions. A sibling refusal, counted
            # the same way, so a rise in how often it fires shows up here
            # rather than needing per-object inspection to notice.
            "not_narrowed": int(doc.meta.get("footnote_not_narrowed") or 0),
        },
    }


def _dark_anchors(doc: Document, reach: dict, claims: dict) -> dict:
    """Anchors every one of whose claimants is unreachable — content that is
    in the model, is claimed, and still reaches no tiddler."""
    st = doc.streams.get(claims["stream"])
    if st is None:
        return {"count": 0, "by_type": {}}
    bad = {e["id"] for e in reach["unreachable"]}
    if not bad:
        return {"count": 0, "by_type": {}}
    owners: dict[Any, list] = defaultdict(list)
    for obj in doc.objects.values():
        if obj.type in CONTAINER_TYPES:
            continue
        for r in obj.realizations:
            if r.stream != claims["stream"] or r.role != "surface" \
                    or r.start is None:
                continue
            if isinstance(r.props.get("offset"), int) \
                    and isinstance(r.props.get("length"), int):
                continue
            end = r.end if r.end is not None else r.start
            try:
                span = st.slice_anchors(r.start, end)
            except KeyError:
                continue
            for a in span:
                owners[a].append(obj)
    by_type: Counter = Counter()
    n = 0
    for a, objs in owners.items():
        if all(o.id in bad for o in objs):
            n += 1
            by_type[tuple(sorted({o.type for o in objs}))] += 1
    return {"count": n,
            "by_type": [{"types": list(k), "count": v}
                        for k, v in by_type.most_common()]}


# ------------------------------------------------------------------ 656 gate

def load_baseline() -> dict:
    """{bibkey: {type: count}} as last recorded in `conserve_baseline.json`.

    Missing file -> `{}`, the same "zero tolerance until someone looks"
    posture `gate()` gives an unaudited bibkey: absence is not an exemption.
    """
    if not BASELINE_PATH.is_file():
        return {}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def classify_unreachable(reach: dict) -> dict:
    """Partition `reach['unreachable']` into THREE buckets, counted per type.
    A separate lens over the same list `reachability()` already returns —
    none of `conserve()`'s three headline counts changes — so a human (or
    `gate()`) can see the real drops first instead of drowning in
    Page/TableCell/TableRow/Toc/Document, which is exactly the
    signal-to-noise problem the transclusion-audit named in `cmd_conserve`'s
    own output.

      - `by_design`    — BY_DESIGN: a verified alternate route; not a defect.
      - `out_of_scope` — OUT_OF_SCOPE: a working transclusion path with a
        catalogued INCIDENTAL gap (645/646's own numbered follow-ups); not
        ratcheted by THIS gate.
      - `violations`   — everything else: a type with NO code path at all
        (measured ~100% unreachable corpus-wide) that nobody has named a
        route for. This is what `gate()` ratchets.
    """
    by_design: Counter = Counter()
    out_of_scope: Counter = Counter()
    violations: Counter = Counter()
    for e in reach["unreachable"]:
        t = e["type"]
        if t in BY_DESIGN:
            by_design[t] += 1
        elif t in OUT_OF_SCOPE:
            out_of_scope[t] += 1
        else:
            violations[t] += 1
    return {"by_design": dict(by_design), "out_of_scope": dict(out_of_scope),
            "violations": dict(violations)}


def gate(doc: Document, res: "dict | None" = None,
        baseline: "dict | None" = None) -> dict:
    """656 — THE RATCHET. Every unreachable object is BY_DESIGN (a verified
    route), OUT_OF_SCOPE (a working path with a catalogued incidental gap —
    645/646's own follow-ups, not this gate's business), or a VIOLATION
    whose count for this document's bibkey must match the checked-in
    baseline EXACTLY.

    `res` — a `conserve(doc)` result already computed by the caller, so this
    does not project the document a second time; `conserve(doc)` if omitted.
    `baseline` — `load_baseline()` if omitted.

    A bibkey with NO row in the baseline is held to an EMPTY one: every
    violation type it has is reported as NEW. An unaudited document gets
    zero tolerance, not a silent pass — the same posture `type_contract`
    takes with an unclaimed corpus type.

    Four outcomes, not one boolean, because "it failed" is not an action:
      - `new_types`   — a violation type with no baseline row at all: either
        classify it (a real route -> BY_DESIGN) or record its count;
      - `increased`   — MORE unreachable objects of a known type than the
        baseline: a regression, or a change that earns a new baseline;
      - `decreased`   — FEWER (including zero): good news that leaves the
        baseline stale if not recorded — 646/656's own rule that a fixed
        defect must not go on being "found" forever;
      - `matched`     — exactly the baseline: reported too, so a PASS shows
        the numbers it passed on rather than just the word.
    `passed` is true only when `new_types`, `increased` and `decreased` are
    all empty.
    """
    if res is None:
        res = conserve(doc)
    if baseline is None:
        baseline = load_baseline()
    bibkey = res["bibkey"]
    cls = classify_unreachable(res["reachability"])
    current = cls["violations"]
    recorded = dict(baseline.get(bibkey, {}))

    new_types = {t: n for t, n in current.items() if t not in recorded}
    increased = {t: {"baseline": recorded[t], "now": current[t]}
                for t in current
                if t in recorded and current[t] > recorded[t]}
    decreased = {t: {"baseline": recorded[t], "now": current.get(t, 0)}
                for t in recorded
                if current.get(t, 0) < recorded[t]}
    matched = {t: n for t, n in current.items()
              if t in recorded and current[t] == recorded[t]}
    passed = not (new_types or increased or decreased)
    return {
        "bibkey": bibkey,
        "passed": passed,
        "has_baseline_row": bibkey in baseline,
        "by_design": cls["by_design"],
        "out_of_scope": cls["out_of_scope"],
        "violations": current,
        "baseline": recorded,
        "new_types": new_types,
        "increased": increased,
        "decreased": decreased,
        "matched": matched,
    }


def format_gate_report(g: dict) -> str:
    """The prose `cmd_conserve --gate` prints: verdict first, then every
    reason a FAIL fired (new/increased/decreased, worst first), THEN the
    quiet classes (matched baseline, by-design) — real violations before
    housekeeping, per the transclusion-audit's own signal-to-noise finding.
    """
    L: list[str] = []
    verdict = "PASS" if g["passed"] else "FAIL"
    row_note = "" if g["has_baseline_row"] else "  (no baseline row for this bibkey — zero tolerance)"
    L.append(f"conserve --gate {g['bibkey']}: {verdict}{row_note}")
    for t in sorted(g["new_types"]):
        n = g["new_types"][t]
        L.append(f"  NEW unreachable type: {t} ({n} object{'s' if n != 1 else ''}) "
                 f"— not in BY_DESIGN and not in the baseline. Either name the "
                 f"verified route (BY_DESIGN) or record {n} in "
                 f"conserve_baseline.json.")
    for t in sorted(g["increased"]):
        d = g["increased"][t]
        L.append(f"  INCREASED: {t} {d['baseline']} -> {d['now']} — a "
                 f"regression, unless this is an intentional change that "
                 f"needs a new baseline number.")
    for t in sorted(g["decreased"]):
        d = g["decreased"][t]
        if d["now"] == 0:
            L.append(f"  FIXED: {t} {d['baseline']} -> 0 — remove it from "
                     f"conserve_baseline.json rather than leaving a stale "
                     f"entry (a fixed defect must not go on being \"found\").")
        else:
            L.append(f"  DROPPED: {t} {d['baseline']} -> {d['now']} — update "
                     f"the baseline to the new, lower count.")
    if g["matched"]:
        L.append("  at baseline: "
                 + ", ".join(f"{t}={n}" for t, n in sorted(g["matched"].items())))
    if g["by_design"]:
        L.append("  by design (not counted against the gate): "
                 + ", ".join(f"{t}={n}" for t, n in sorted(g["by_design"].items())))
    if g.get("out_of_scope"):
        L.append("  out of scope (working path, incidental gaps tracked "
                 "elsewhere — 645/646): "
                 + ", ".join(f"{t}={n}" for t, n in sorted(g["out_of_scope"].items())))
    if not (g["new_types"] or g["increased"] or g["decreased"] or g["matched"]
           or g["by_design"] or g.get("out_of_scope")):
        L.append("  no unreachable objects of any kind.")
    return "\n".join(L)


# --------------------------------------------------------------- rendering

def format_report(res: dict, limit: int = _MAX_EXAMPLES) -> str:
    """The prose the command prints: three counts, the per-type breakdown,
    then up to `limit` named examples per class."""
    c = res["counts"]
    reach, anch = res["reachability"], res["anchors"]
    L: list[str] = []
    L.append(f"conserve {res['bibkey']}: "
             + ("CONSERVED" if res["conserved"] else "NOT CONSERVED"))
    L.append(f"unreachable objects:  {c['unreachable']} of {reach['objects']}"
             f"  (objects the projection never places under a parent)")
    L.append(f"unclaimed anchors:    {c['unclaimed']} of {anch['total']}"
             f"  ({anch['stream']} lines no object covers)")
    L.append(f"doubly-claimed:       {c['doubly_claimed']} of {anch['total']}"
             f"  (lines 2+ objects both cover)")
    L.append("")
    L.append(f"projection: {reach['tiddlers']} tiddlers, "
             f"{reach['templates']} templates, "
             f"{reach.get('reached', 0)} reached by the walk from "
             f"roots {', '.join(reach['roots']) or '(none)'}")
    dark = (anch.get("dark") or {}).get("count", 0)
    if dark:
        L.append(f"dark anchors:         {dark} of {anch['total']}"
                 f"  (claimed, but every claimant is unreachable: "
                 + ", ".join(f"{'+'.join(e['types'])}={e['count']}"
                             for e in anch["dark"]["by_type"][:6]) + ")")
    ref = res.get("footnote_refusals") or {}
    if ref.get("orphan_tail") or ref.get("span_not_located"):
        L.append(f"footnote split refusals: "
                 f"orphan_tail={ref.get('orphan_tail', 0)} "
                 f"(a tail kept on the body before a REPEATED number, marked "
                 f"tail_unassigned), span_not_located="
                 f"{ref.get('span_not_located', 0)} (a lifted footnote whose "
                 f"number is on no single line, keeping its paragraph's claim)")
    if ref.get("adopted"):
        L.append(f"footnote bodies adopted: {ref['adopted']} filled into a "
                 f"Footnote that already held that body (one object per "
                 f"footnote, not two — 637)")
    if ref.get("not_narrowed"):
        L.append(f"footnote paragraph(s) not narrowed: {ref['not_narrowed']} "
                 f"whose surviving text was not an exact whole-line "
                 f"suffix/prefix of the original — the `surface` Realization "
                 f"stays wide and `footnote_extracted` gates rendering "
                 f"instead, at the cost of that paragraph's own "
                 f"transclusions (650)")
    L.append(f"claims: {anch['claims']} covering, {anch['inline_skipped']} inline "
             f"(sub-anchor offset — does not claim its line); "
             f"container types not claiming: {', '.join(anch['containers_excluded'])}")

    L.append("")
    L.append("per type (objects / unreachable / multi-parent):")
    rows = sorted(reach["by_type"].items(),
                  key=lambda kv: (-kv[1]["unreachable"], -kv[1]["objects"]))
    for t, b in rows:
        flag = ""
        if b["unreachable"] or b["multi_parent"]:
            flag = "   <--"
        L.append(f"  {t:<12} {b['objects']:>6} {b['unreachable']:>6} "
                 f"{b['multi_parent']:>6}{flag}")

    if reach["unreachable"]:
        L.append("")
        ex = _round_robin(reach["unreachable"], limit)
        L.append(f"unreachable, {len(ex)} of {len(reach['unreachable'])} "
                 f"(one per type in turn):")
        for e in ex:
            L.append(f"  {e['type']:<10} {e['title'] or '(no title)':<22} "
                     f"{e['reason']:<11} named_by={e['named_by']} "
                     f"p{e['page']}  {e['text']}")
    if reach["multi_parent"]:
        L.append("")
        ex = _round_robin(reach["multi_parent"], limit)
        L.append(f"multi-parent, {len(ex)} of {len(reach['multi_parent'])} "
                 f"(one per type in turn):")
        for e in ex:
            L.append(f"  {e['type']:<10} {e['title']:<22} "
                     f"{len(e['parents'])} parents: "
                     f"{', '.join(e['parents'][:4])}")
    if reach.get("collisions"):
        L.append("")
        L.append(f"title collisions (2+ objects -> ONE tiddler): "
                 f"{len(reach['collisions'])}")
        for e in reach["collisions"][:limit]:
            L.append(f"  {e['title']:<22} "
                     + " | ".join(f"{o['type']} {o['text']}"
                                  for o in e["objects"]))
    if anch["unclaimed"]:
        L.append("")
        by_kind = Counter(e["line_type"] or "?" for e in anch["unclaimed"])
        L.append("unclaimed by line type: "
                 + ", ".join(f"{k}={v}" for k, v in by_kind.most_common()))
        L.append(f"unclaimed, first {min(limit, len(anch['unclaimed']))}:")
        for e in anch["unclaimed"][:limit]:
            L.append(f"  line {e['index']:<6} p{e['page']} "
                     f"{str(e['line_type']):<16} {e['text']}")
    if anch["doubly_claimed"]:
        L.append("")
        L.append("doubly-claimed by type pair: "
                 + ", ".join(f"{'+'.join(p['types'])}={p['count']}"
                             for p in anch["pairs"]))
        L.append(f"doubly-claimed, first {min(limit, len(anch['doubly_claimed']))}:")
        for e in anch["doubly_claimed"][:limit]:
            L.append(f"  line {e['index']:<6} p{e['page']} "
                     f"{'+'.join(e['types'])}: {e['text']}")
    return "\n".join(L)
