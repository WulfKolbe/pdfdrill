#!/usr/bin/env python3
"""Unpack a pdfdrill tiddlers.json into a TiddlyWiki node folder — stdlib only.

Each tiddler's `text` -> <title>.md; every other field -> <title>.md.meta
(title first, rest sorted, newlines folded). Byte-format-compatible with
pdfdrill's tiddlers_to_md / repo_publish. Logs every path to unpack.log.

    python3 unpack.py <tiddlers.json> [--out tiddlers]
"""
import json
import re
import sys
from pathlib import Path


def safe_filename(title):
    return re.sub(r"[^\w.\-]+", "_", title or "") or "tiddler"


def main(argv):
    if not argv:
        print(__doc__)
        return 1
    src = Path(argv[0])
    out = Path("tiddlers")
    if "--out" in argv:
        out = Path(argv[argv.index("--out") + 1])
    out.mkdir(parents=True, exist_ok=True)
    log = open("unpack.log", "w", encoding="utf-8")
    log.write(f"READ    {src.resolve()}\n")
    tiddlers = json.loads(src.read_text(encoding="utf-8"))
    log.write(f"PARSED  {len(tiddlers)} tiddlers\n")
    seen = {}
    for i, t in enumerate(tiddlers):
        base = safe_filename(t.get("title") or f"tiddler_{i}")
        if base in seen:
            seen[base] += 1
            base = f"{base}~{seen[base]}"
        else:
            seen[base] = 0
        md = out / f"{base}.md"
        md.write_text(t.get("text", "") or "", encoding="utf-8")
        log.write(f"WRITE   {md.resolve()}\n")
        lines = [f"title: {t.get('title', '')}"]
        for k in sorted(t):
            if k in ("text", "title"):
                continue
            v = t[k]
            if isinstance(v, str):
                v = v.replace("\n", " ")
            lines.append(f"{k}: {v}")
        meta = out / f"{base}.md.meta"
        meta.write_text("\n".join(lines) + "\n", encoding="utf-8")
        log.write(f"WRITE   {meta.resolve()}\n")
    log.close()
    print(f"Unpacked {len(tiddlers)} tiddlers into {out}/ (see unpack.log)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
