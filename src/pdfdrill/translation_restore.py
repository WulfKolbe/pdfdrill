"""825 — put a translation back on a model that was rebuilt after it.

`translate` writes the target language IN PLACE over each prose object's
`text`. There is no `text_original` on the object, so a `model --force` reverts
every translated field and the only surviving record is an older model FILE.
That is not a hypothetical: it cost this project BH3FR's 130-object EN-US
translation, and the guard that refuses `--force` on a translated model exists
because of the same loss.

The join is the problem worth writing down. Two builds of one document share
NOTHING that looks like an identity:

  * object ids are freshly minted per build;
  * stream anchor ids likewise, so a Realization's span does not carry across;
  * prose objects have no `region`, so geometry cannot separate them.

What they do share is `lines.json`, and every prose object records its extent
in it as `from_line_index` / `to_line_index`. `(type, page, from, to)` is
therefore stable across builds by construction rather than by luck. Measured on
BH3FR: 124 of 124 Paragraphs matched 1:1, none ambiguous.

It restores ONLY where that key occurs exactly once on each side. A structural
pass that landed between the two builds legitimately changes the object set —
BH3FR's Sections went 6 to 33 and its ListItems 7 to 18 — and for those there
is nothing to copy. They are left in the source language and counted, because
guessing which old heading became which new one is how a translation silently
attaches to the wrong text.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

#: Object types whose `text` a translation rewrites.
PROSE_TYPES = ("Paragraph", "Section", "Sidenote", "ListItem", "Toc")


def _key(obj_type: str, props: dict) -> tuple:
    return (obj_type, props.get("page"),
            props.get("from_line_index"), props.get("to_line_index"))


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def translated_text(source: Path) -> tuple[dict, dict]:
    """`({key: text}, meta)` from an older model file, ambiguous keys dropped.

    A key that occurs twice on the source side names two different paragraphs
    with one label; neither can be attributed, so both are withheld.
    """
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    objs = data.get("objects") or []
    objs = objs if isinstance(objs, list) else list(objs.values())

    seen: dict = {}
    text: dict = {}
    for o in objs:
        if o.get("type") not in PROSE_TYPES:
            continue
        k = _key(o["type"], o.get("props") or {})
        seen[k] = seen.get(k, 0) + 1
        text[k] = (o.get("props") or {}).get("text")
    for k, n in seen.items():
        if n > 1:
            text.pop(k, None)
    return text, (data.get("meta") or {})


def restore(doc, source: Path) -> dict:
    """Copy the translated prose of `source` onto `doc`. Returns counts.

    Mutates `doc` and records where the text came from. It did NOT come from a
    translation call made against this model, and a reader who cannot tell
    those apart cannot tell whether the text matches the objects it now sits
    on — so the provenance is the sha256 of the file it was taken from, which
    survives copying between machines, and not a path or an mtime, which do
    not. This file arrived here by `scp`; its mtime is when it was copied.
    """
    source = Path(source)
    text, src_meta = translated_text(source)

    live = [o for o in doc.objects.values() if o.type in PROSE_TYPES]
    counts: dict = {}
    for o in live:
        k = _key(o.type, o.props)
        counts[k] = counts.get(k, 0) + 1

    restored = unchanged = 0
    skipped: dict = {}
    for o in live:
        k = _key(o.type, o.props)
        new = text.get(k)
        if counts[k] != 1 or not new:
            skipped[o.type] = skipped.get(o.type, 0) + 1
            continue
        if (o.props.get("text") or "") == new:
            unchanged += 1
            continue
        o.props["text"] = new
        restored += 1

    lang = src_meta.get("translated_lang")
    if lang:
        doc.meta["translated_lang"] = lang
    if src_meta.get("source_lang"):
        doc.meta["source_lang"] = src_meta["source_lang"]
    doc.meta["translation_restored"] = {
        "sha256": _digest(source),
        "path": str(source.resolve()),
        "source_build": src_meta.get("build"),      # None before 575
        "restored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "objects": restored,
    }
    return {"restored": restored, "unchanged": unchanged,
            "skipped": skipped, "lang": lang,
            "sha256": doc.meta["translation_restored"]["sha256"]}
