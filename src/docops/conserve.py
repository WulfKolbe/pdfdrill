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
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict, deque
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
