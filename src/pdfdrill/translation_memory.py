"""The tiddler translations, kept where a rebuild cannot reach them — 786.

A translated tiddler lived in exactly one place: `<bibkey>.tiddlers.json`. The
model could not hold it, because the TiddlyWiki projector rebuilds transcluded
paragraphs from the immutable source stream BY OFFSET, so a translated `text`
on the model never reaches the tiddler — which is why `translate` does a second,
tiddler-level pass at all.

The consequence was that any plain `pdfdrill tiddlers` regenerated the file from
the model and silently dropped every translation, and only a PAID rerun of
`translate` put it back. BH1org_OCR shows the whole shape in two timestamps:

    BH1org_OCR.md            2026-08-27   translated
    BH1org_OCR.tiddlers.json 2026-08-29   rebuilt — translation gone

and the rerun that restored it sent 689,340 characters to DeepL for prose that
had already been paid for once.

So the translation is written here as well, keyed by the tiddler's title AND a
hash of the source text it was made from. The hash is what makes re-applying
safe: if the projection changed the prose, the stored translation is not a
translation of THIS text and is skipped rather than pasted over new content.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

#: Bumped when the record shape changes, so an old file is ignored rather than
#: half-read.
VERSION = 1


def path_for(blob_dir: Path, bibkey: str) -> Path:
    return Path(blob_dir) / f"{bibkey}.translation.json"


def key_of(source_text: str) -> str:
    """The identity of a source string — what the translation was made FROM."""
    return hashlib.sha256(source_text.encode("utf-8")).hexdigest()[:32]


def load(blob_dir: Path, bibkey: str) -> dict:
    p = path_for(blob_dir, bibkey)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if data.get("version") != VERSION:
        return {}
    return data.get("entries") or {}


def save(blob_dir: Path, bibkey: str, entries: dict, *, target_lang: str,
         source_lang: str | None = None) -> Path:
    p = path_for(blob_dir, bibkey)
    p.write_text(json.dumps({
        "version": VERSION, "target_lang": (target_lang or "").upper(),
        "source_lang": (source_lang or "").upper() or None,
        "entries": entries,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def harvest(tiddlers: list[dict], field_for) -> dict:
    """Every translation present in a tiddler array, as {title: record}."""
    out: dict[str, Any] = {}
    for t in tiddlers:
        field = field_for(t)
        if not field:
            continue
        src = t.get(field + "_source")
        if not (isinstance(src, str) and src.strip()):
            continue
        out[str(t.get("title") or "")] = {
            "field": field, "src_key": key_of(src),
            "source": src, "translated": t.get(field),
        }
    out.pop("", None)
    return out


def reapply(tiddlers: list[dict], entries: dict, field_for) -> tuple[int, int]:
    """Put stored translations back into a freshly projected tiddler array.

    Returns (applied, skipped_because_the_text_changed). A tiddler whose prose
    no longer hashes to what was translated is LEFT ALONE: pasting an old
    translation over new text is the one failure worse than an untranslated
    tiddler, because nothing downstream can see it.
    """
    applied = stale = 0
    for t in tiddlers:
        field = field_for(t)
        if not field or (field + "_source") in t:
            continue
        rec = entries.get(str(t.get("title") or ""))
        if not rec or rec.get("field") != field:
            continue
        cur = t.get(field)
        if not isinstance(cur, str):
            continue
        if key_of(cur) != rec.get("src_key"):
            stale += 1
            continue
        t[field + "_source"] = cur
        t[field] = rec.get("translated")
        applied += 1
    return applied, stale
