r"""TiddlyWiki -> docmodel: a correction made in the wiki reaches the model.

OWNER, 2026-11-12: "To change formulas and correct errors I would always prefer
Tiddlywiki. Therefore we need an importer that is able to update existing
docmodel data by Tiddlywiki."

WHAT WAS WRONG
--------------
`pdfdrill tiddlers --update` already reads an edited tiddlers.json, matches BY
TITLE, restores hand edits and refuses stale ones with stated reasons (651).
It writes the result to `<bibkey>.update.json`, and there it stops. The docmodel
never learns, so `md`, `latex`, `inspect` and every other projection keep
showing the uncorrected value -- correcting a formula in the wiki changed the
wiki and nothing else.

And `KEEP_LIST` guards `text`, `caption` and `trailing_punct` but NOT `latex`,
so the one field the owner most wants to edit was overwritten by the
projector's own value on the next `--update`, before any question of reaching
the model.

THE RULE: PROVE THE CORRESPONDENCE, OR REFUSE
---------------------------------------------
A tiddler field may be written back to a prop only when the FRESH projection of
the current model reproduces that prop's value VERBATIM. Then the edit has
exactly one place to land and the importer can name it.

This is deliberately not a hand-written field->prop table. `tiddlywiki.py` says
of its own numbering that "a second implementation would silently drift"; a
table of which field maps to which prop is exactly such a second
implementation, and it would drift the first time a template changed. Proving
it per object from the projection cannot drift, because the projection IS the
mapping.

MEASURED on BH2, 6,450 titles -- what the rule admits:

    Formula    tiddler[latex]   == props[latex]     4870
    Equation   tiddler[latex]   == props[latex]      342
    ListItem   tiddler[text]    == props[content]    120
    Sidenote   tiddler[text]    == props[content]     11
    Section    tiddler[caption] == props[caption]      8
    Footnote   tiddler[text]    == props[content]      6

and what it refuses: 651 of 656 Paragraph `text` fields. The projector REBUILDS
a paragraph's text from the model's own realization in the reading stream
rather than reading `props['text']` -- which on BH2 is visible as the tiddler
holding GERMAN while `props['text']` holds the English translation. Such an
edit has no prop to land in; it is refused with that reason rather than written
somewhere plausible.

WHAT IT WILL NOT DO
-------------------
Create or delete objects (a title the model does not have is REPORTED).
Write `latex_raw` / `latex_original` / `latex_author` or any `<field>_source`
twin -- those are the producer's verbatim record and the pre-translation
baseline. Empty a field. Trigger a rebuild: a rebuild regenerates object ids
and would throw away the very mapping this works through.
"""
from __future__ import annotations

import json
from typing import Any

#: Fields a wiki author edits. `trailing_punct` is excluded on purpose: it is
#: owned by `pdfdrill trailingpunct` (025) and named in KEEP_LIST as such.
IMPORT_FIELDS: tuple[str, ...] = ("latex", "text", "caption")

#: Props an import may NEVER target. The first three are what the reader
#: produced, verbatim; a `<field>_source` twin is the pre-translation baseline
#: that `translate` captured. A correction is a new value for the live field,
#: never a rewriting of the record it came from.
PROTECTED_PROPS = frozenset({"latex_raw", "latex_original", "latex_author"})


def _is_template(t: dict) -> bool:
    """A TEMPLATE tiddler is wiki machinery, not a document object.

    The projector ships 16 of them (`FO`, `CIT`, `PARA`, `EQ`, …) tagged
    `template`; they hold the `<$latex>`/`<$link>` widgets the object tiddlers
    transclude. They have no object and never will, so listing them as "titles
    the model does not have" put 17 alarming rows in the report of a clean
    import. Skipped silently, and counted separately if a caller wants.
    """
    tags = t.get("tags")
    if isinstance(tags, str):
        return "template" in tags.split()
    if isinstance(tags, (list, tuple)):
        return "template" in [str(x) for x in tags]
    return False


def _protected(prop: str) -> bool:
    return prop in PROTECTED_PROPS or prop.endswith("_source")


def _projector():
    from docops.base import OperatorConfig
    from docops.projectors.tiddlywiki import TiddlyWikiProjector
    return TiddlyWikiProjector(
        OperatorConfig(op="projector", classname="TiddlyWikiProjector"))


def object_titles(doc, bibkey: str) -> dict[str, str]:
    """`{object_id: tiddler_title}` for every object the wiki names.

    From the projector's own assignment, not a second copy of the numbering:
    `tiddlywiki.math_titles` already warns that a second implementation
    "would silently drift and emit references that resolve to the wrong
    formula", and the same holds for every other type.
    """
    titles, _inv = _projector()._assign_titles(doc, bibkey)
    return dict(titles)


def fresh_tiddlers(doc, bibkey: str) -> list[dict]:
    """The tiddler file this model projects to right now -- the baseline an
    edited file is compared against."""
    out = json.loads(_projector().project(doc))
    return out if isinstance(out, list) else []


def _candidate_props(obj, baseline: str, field: str) -> tuple[str | None, str]:
    """(prop to write, reason it was refused) for one field of one object.

    `baseline` is what the FRESH projection put in that field. A prop whose
    current value equals it is a proved correspondence.
    """
    props = obj.props or {}
    matches = [k for k, v in props.items()
               if isinstance(v, str) and v == baseline and not _protected(k)]
    if not matches:
        if any(isinstance(v, str) and v == baseline for v in props.values()):
            return None, (
                f"the only prop holding this value is one an import may never "
                f"write (the producer's verbatim record, or a "
                f"pre-translation `_source` twin)")
        return None, (
            f"the projection does not reproduce any prop's value verbatim in "
            f"`{field}` -- the template builds it (a widget, a heading, or a "
            f"paragraph rebuilt from the reading stream), so there is no prop "
            f"for this edit to land in")
    if field in matches:                   # same name wins: latex -> latex
        return field, ""
    if len(matches) == 1:
        return matches[0], ""
    return None, (
        f"`{field}` matches more than one prop ({', '.join(sorted(matches))}) "
        f"and nothing here can say which the edit meant")


def plan(doc, bibkey: str, edited: list[dict]) -> dict[str, Any]:
    """What `edited` would change in `doc`. READ ONLY -- writes nothing.

    Returns {"changes": [...], "refused": [...], "unmatched": [...],
             "titles": n, "compared": n}.
    """
    titles = object_titles(doc, bibkey)
    id_of = {t: i for i, t in titles.items()}
    fresh = {t.get("title"): t for t in fresh_tiddlers(doc, bibkey)
             if isinstance(t, dict) and t.get("title")}
    changes: list[dict] = []
    refused: list[dict] = []
    unmatched: list[str] = []
    compared = 0
    furniture = 0
    for t in edited:
        if not isinstance(t, dict):
            continue
        title = t.get("title")
        if not title:
            continue
        base = fresh.get(title)
        oid = id_of.get(title)
        if base is not None and (oid is None or oid not in doc.objects):
            # PROJECTOR FURNITURE, not a missing object: the 16 `template`
            # tiddlers holding the `<$latex>`/`<$link>` widgets, the document's
            # own root tiddler, the generated TOC. The projection HAS them and
            # no object owns them, which is the structural test -- reporting
            # them as "titles the model does not have" put 17 alarming rows in
            # the report of a perfectly clean import on 1911.02782.
            furniture += 1
            continue
        if base is None:
            # Not in the projection at all: a tiddler the wiki author created,
            # or a title from an older build. Reported, never created.
            unmatched.append(title)
            continue
        compared += 1
        obj = doc.objects[oid]
        for field in IMPORT_FIELDS:
            if field not in t:
                continue
            new = t.get(field)
            if not isinstance(new, str):
                continue
            old_rendered = base.get(field)
            if not isinstance(old_rendered, str) or new == old_rendered:
                continue                                  # not an edit
            if not new.strip():
                refused.append({"title": title, "obj_id": oid,
                                "field": field,
                                "reason": "the edit would leave the field "
                                          "empty, which is far more likely a "
                                          "slip than an instruction to delete "
                                          "the content"})
                continue
            prop, why = _candidate_props(obj, old_rendered, field)
            if prop is None:
                refused.append({"title": title, "obj_id": oid,
                                "field": field, "reason": why})
                continue
            changes.append({"title": title, "obj_id": oid, "type": obj.type,
                            "field": field, "prop": prop,
                            "old": (obj.props or {}).get(prop, ""),
                            "new": new})
    return {"changes": changes, "refused": refused, "unmatched": unmatched,
            "titles": len(titles), "compared": compared,
            "furniture": furniture}


#: Stamped on every object an import changes. `commands.ENRICHMENT_MARKERS`
#: lists it, so `model` refuses to rebuild over it and says so.
EDIT_MARKER = "wiki_edit"


def apply(doc, changes: list[dict]) -> int:
    """Write `changes` into the document's props. Returns the number written.

    No object is created or removed, and every target was checked by `plan`;
    this re-checks `_protected` all the same, because a caller could hand us a
    hand-built list.

    EVERY CHANGED OBJECT IS STAMPED `wiki_edit`, and that is not bookkeeping --
    it is what stops the correction being thrown away. MEASURED on the first
    end-to-end round trip (1911.02782): the import wrote `{}^{1, 2}`, and the
    next `pdfdrill latex --force` ran the lazy rebuild, regenerated every
    object id (obj_ca8c2d32ed23 -> obj_2ec8cf656c22), and put `^{1, 2}` back.
    lines.json holds no hand correction, so a rebuild cannot reproduce one;
    the marker puts it in `ENRICHMENT_MARKERS`, where the rebuild guard sees
    it and refuses.
    """
    n = 0
    touched: set[str] = set()
    for c in changes:
        oid, prop, new = c.get("obj_id"), c.get("prop"), c.get("new")
        if not oid or not prop or not isinstance(new, str):
            continue
        if _protected(prop) or oid not in doc.objects:
            continue
        props = doc.objects[oid].props
        props[prop] = new
        fields = sorted(set(str(props.get(EDIT_MARKER) or "").split(",")
                            ) | {prop}) if props.get(EDIT_MARKER) else [prop]
        props[EDIT_MARKER] = ",".join(f for f in fields if f)
        touched.add(oid)
        n += 1
    return n


def report(result: dict, bibkey: str, *, applied: bool) -> str:
    """The prose a reader gets: what changed, what was refused and why."""
    ch, rf, um = result["changes"], result["refused"], result["unmatched"]
    head = (f"{'Imported' if applied else 'Would import'} {len(ch)} field(s) "
            f"from the wiki into {bibkey}'s docmodel "
            f"({result['compared']} of {result['titles']} titles compared).")
    lines = [head]
    by_kind: dict[tuple[str, str, str], int] = {}
    for c in ch:
        key = (c["type"], c["field"], c["prop"])
        by_kind[key] = by_kind.get(key, 0) + 1
    for (typ, field, prop), n in sorted(by_kind.items()):
        lines.append(f"  {typ}: tiddler `{field}` -> props['{prop}']  x{n}")
    for c in ch[:12]:
        lines.append(f"    {c['title']} [{c['prop']}]")
        lines.append(f"      was: {str(c['old'])[:90]}")
        lines.append(f"      now: {str(c['new'])[:90]}")
    if len(ch) > 12:
        lines.append(f"    … and {len(ch) - 12} more")
    if rf:
        lines.append(f"  REFUSED {len(rf)} edit(s):")
        seen: set[str] = set()
        for r in rf:
            if r["reason"] in seen:
                continue
            seen.add(r["reason"])
            lines.append(f"    {r['title']} `{r['field']}`: {r['reason']}")
        if len(rf) > len(seen):
            lines.append(f"    ({len(rf)} refusals, {len(seen)} distinct "
                         f"reason(s))")
    if result.get("furniture"):
        lines.append(f"  {result['furniture']} tiddler(s) skipped as wiki "
                     f"machinery (templates, the root tiddler, the generated "
                     f"TOC) -- the projection has them and no object owns "
                     f"them")
    if um:
        lines.append(f"  {len(um)} title(s) the model does not have "
                     f"(reported, never created): {', '.join(um[:6])}"
                     + (" …" if len(um) > 6 else ""))
    if not applied and ch:
        lines.append("  Nothing was written. Re-run with --apply to write "
                     "these into the model.")
    return "\n".join(lines)
