#!/usr/bin/env python3
"""Minimal `tiddlers.json` → per-tiddler `.md` + `.md.meta` exporter.

Reads a pdfdrill `<bibkey>.tiddlers.json` (the array of tiddler dicts) and
writes, under `<out>/<bibkey>/`, one `<title>.md` (the `text` field) plus a
`<title>.md.meta` sidecar (the remaining fields, one `field: value` per line —
the TiddlyWiki file-system convention). This is the on-disk form for a
TiddlyWiki / llmwiki where each tiddler is a file, so a SKILL can point at an
EXACT path derived from the object-wise bibkey-prefixed title
(`2110.11150_H19.md`, `2110.11150_THM0003.md`, …), and the wiki server's
index.html preview lists them.

The content tiddlers are `text/markdown` (templates stay `text/vnd.tiddlywiki`);
the `.md.meta` carries the `type:` field, so a mixed set round-trips. Transclusion
templates (FO/PARA/THM/PROOF/…) are exported too, so `{{id||TPL}}` resolves.

Caveat: TiddlyWiki `.meta` fields are single-line — a field whose value spans
lines (e.g. `lean4`, `svg_tiddler`) has its newlines collapsed to spaces in the
`.meta`; read those verbatim from the `.json` (a later revision may sidecar them
as their own files). Reference-list driven features are not built yet.

CLI:  python3 tools/tiddlers_to_md.py <bibkey>.tiddlers.json [--out DIR] [--bibkey K]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
# Field order: identity first, then the rest alphabetically (stable diffs).
_LEAD_FIELDS = ("title", "type", "tags", "caption", "created", "modified")


def safe_filename(title: str) -> str:
    """A filesystem-safe basename derived from a tiddler title (kept ≤180 chars).
    The exact title is preserved in the `.md.meta` `title:` field."""
    name = _UNSAFE.sub("_", title or "").strip().strip(".") or "untitled"
    return name[:180]


def _meta_value(v) -> str:
    """A single-line `.meta` value (TiddlyWiki fields are single-line)."""
    s = "" if v is None else str(v)
    return s.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")


def tiddler_files(t: dict) -> tuple[str, str]:
    """Return (md_text, meta_text) for one tiddler dict."""
    md = t.get("text", "") or ""
    keys = ([k for k in _LEAD_FIELDS if k in t]
            + sorted(k for k in t if k not in _LEAD_FIELDS and k != "text"))
    meta = "\n".join(f"{k}: {_meta_value(t[k])}" for k in keys) + "\n"
    return md, meta


def export_tiddlers(tiddlers, out_dir, bibkey: str | None = None) -> tuple[int, Path]:
    """Write every tiddler as `<title>.md` + `<title>.md.meta` under
    `<out_dir>/<bibkey>/`. Returns (count, folder)."""
    out = Path(out_dir)
    if bibkey:
        out = out / safe_filename(bibkey)
    out.mkdir(parents=True, exist_ok=True)
    seen: dict[str, int] = {}
    written = 0
    for t in tiddlers:
        base = safe_filename(t.get("title") or f"tiddler_{written}")
        if base in seen:                                   # disambiguate collisions
            seen[base] += 1
            base = f"{base}~{seen[base]}"
        else:
            seen[base] = 0
        md, meta = tiddler_files(t)
        (out / f"{base}.md").write_text(md, encoding="utf-8")
        (out / f"{base}.md.meta").write_text(meta, encoding="utf-8")
        written += 1
    return written, out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Export a pdfdrill tiddlers.json to .md + .md.meta files.")
    ap.add_argument("tiddlers_json")
    ap.add_argument("--out", default="tiddlers_md", help="output root directory")
    ap.add_argument("--bibkey", default=None,
                    help="subfolder name (default: the tiddlers.json filename stem)")
    a = ap.parse_args(argv)
    p = Path(a.tiddlers_json)
    data = json.loads(p.read_text(encoding="utf-8"))
    bibkey = a.bibkey or p.name.split(".tiddlers")[0]
    n, out = export_tiddlers(data, a.out, bibkey)
    print(f"Wrote {n} tiddler(s) as .md + .md.meta under {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
