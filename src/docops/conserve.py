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

WHAT COUNTS AS A PARENT
-----------------------
A CONTENT TRANSCLUSION `{{title}}` / `{{title||TPL}}` in some OTHER tiddler's
text. That is the only containment edge TiddlyWiki has: the section body
emits one per child block, and the paragraph text carries one per inline
formula/citation/footnote marker.

A LISTING is not a parent, but it does make a tiddler REACHABLE: the root
document tiddler lists its top-level sections as `<$link to="...">`, the
rebuilt TOC index lists every section the same way, and a section lists its
subsections as `- <$link to="S">{{S!!caption}}</$link>`. Those are how a
reader walks down from the roots, so a tiddler named by one is reachable —
but they are one-to-many by design, so they never make an object
multi-parent. Counting them as parents would flag every section in every
document.

The ROOTS are the document tiddler (titled with the bibkey, tagged
`document`) and the rebuilt TOC index (`<bibkey>_TOC`, tagged `toc`); the
`template` tiddlers are the wiki's scaffolding. None of the three is an
object's tiddler, so none appears in the object population at all.

MULTI-PARENT IS NOT ALWAYS A DEFECT. Transclusion exists so that one formula
is stored once and referenced N times (docs/TRANSCLUSION.md). For Formula and
Reference, 2+ parents is the design working. For Paragraph, Table, Picture,
ListItem it is duplication. The count is reported PER TYPE so the reader can
tell the two apart rather than being handed one number that mixes them.

DEVIATION FROM THE BRIEF'S LITERAL CLAIM RULE, AND WHY
------------------------------------------------------
The brief defines a claim as a `surface` realization on `mathpix_lines`
whose [start, end] contains the anchor and which carries no sub-anchor
offset/length. Read literally that makes a Page a claimant: `PageProcessor`
gives every Page a surface realization spanning every line of the page, so
EVERY anchor would be claimed by its Page plus its real owner and the
doubly-claimed count would equal the anchor count. A measure that reports
3178 of 3178 says nothing. `CONTAINER_TYPES` names the types whose range is
a container by construction rather than a claim on content; they are listed
in the result under `containers_excluded` so the exclusion is visible in the
output, not hidden in the code.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from docmodel.core import Document

#: Types whose `mathpix_lines` surface range is a CONTAINER, not a claim.
#: A Page spans every line it holds; a List spans every item it nests.
CONTAINER_TYPES = ("Page", "List")

#: Tiddlers that list rather than contain. `<$link to="X">` inside one of
#: these makes X reachable without making it X's parent.
_LISTING_TAGS = ("document", "toc")

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

def reachability(doc: Document, tiddlers: list[dict],
                 titles: dict[str, str]) -> dict:
    """Every DocObject reachable from exactly one parent in the projection?

    `unreachable` — 0 parents and not listed from a root. `reason` is
    "no tiddler" when the projector emits nothing at all for the object
    (its title is unassigned, or assigned but never emitted), else
    "no parent".
    `multi_parent` — named by a content transclusion in 2+ OTHER tiddlers.
    """
    bibkey = doc.meta.get("bibkey", "DOC")
    root_title = _sanitize_title(bibkey)
    emitted = {t.get("title") for t in tiddlers}

    # title -> set of tiddler titles that CONTAIN it (content transclusion)
    parents: dict[str, set[str]] = defaultdict(set)
    # titles a root/TOC listing (or a `{{X!!field}}` field transclusion)
    # points at — reachable, but not parented
    listed: set[str] = {root_title}

    for t in tiddlers:
        src = t.get("title")
        text = t.get("text") or ""
        is_listing = any(g in _LISTING_TAGS for g in _tags(t))
        for m in _TRANSCLUDE.finditer(text):
            inner = m.group(1).strip()
            if inner.startswith("!!"):              # {{!!field}} — this tiddler
                continue
            head = inner.split("||")[0]
            target = head.split("!!")[0].strip()
            if not target or target == src:
                continue
            if "!!" in head:                        # {{X!!caption}} — a listing
                listed.add(target)
            else:
                parents[target].add(src)
        if is_listing:
            for m in _LINK_TO.finditer(text):
                listed.add(m.group(1).strip())

    unreachable: list[dict] = []
    multi_parent: list[dict] = []
    by_type: dict[str, dict[str, int]] = {}
    # Two objects that share ONE tiddler title are one object in the
    # projection: content is not lost but it IS mixed up, and neither of the
    # three headline counts can see it (the title is reachable exactly once).
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

    for obj in doc.objects.values():
        bucket = by_type.setdefault(
            obj.type, {"objects": 0, "unreachable": 0, "multi_parent": 0})
        bucket["objects"] += 1
        raw = titles.get(obj.id)
        title = _sanitize_title(raw) if raw else None
        if not title or title not in emitted:
            bucket["unreachable"] += 1
            unreachable.append({"id": obj.id, "type": obj.type,
                                "title": title, "reason": "no tiddler",
                                "page": obj.props.get("page") or obj.props.get("page_number"),
                                "text": _excerpt(_describe(obj))})
            continue
        ps = sorted(parents.get(title, ()))
        if len(ps) == 0 and title not in listed:
            bucket["unreachable"] += 1
            unreachable.append({"id": obj.id, "type": obj.type,
                                "title": title, "reason": "no parent",
                                "page": obj.props.get("page") or obj.props.get("page_number"),
                                "text": _excerpt(_describe(obj))})
        elif len(ps) > 1:
            bucket["multi_parent"] += 1
            multi_parent.append({"id": obj.id, "type": obj.type,
                                 "title": title, "parents": ps,
                                 "page": obj.props.get("page") or obj.props.get("page_number"),
                                 "text": _excerpt(_describe(obj))})

    return {
        "objects": len(doc.objects),
        "tiddlers": len(tiddlers),
        "roots": sorted(
            t.get("title") for t in tiddlers
            if any(g in _LISTING_TAGS for g in _tags(t))),
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
             f"{reach['templates']} templates, roots {', '.join(reach['roots'])}")
    dark = (anch.get("dark") or {}).get("count", 0)
    if dark:
        L.append(f"dark anchors:         {dark} of {anch['total']}"
                 f"  (claimed, but every claimant is unreachable: "
                 + ", ".join(f"{'+'.join(e['types'])}={e['count']}"
                             for e in anch["dark"]["by_type"][:6]) + ")")
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
                     f"{e['reason']:<11} p{e['page']}  {e['text']}")
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
