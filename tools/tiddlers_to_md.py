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

Code / multi-line fields are SIDECAR'd as their own CLEAN files (no escaping):
`lean4` → `<title>.lean`, `svg_tiddler` → `<title>.svg`, `latex_code`/
`latex_original` → `.tex`, `bibtex` → `.bib`, any other field carrying a newline
→ `.txt`. The `.md.meta` then records `<field>: <sidecar filename>` (the
`_canonical_uri` idea, at field level) so the verbatim content lives in a file the
SKILL / wiki can open directly. This is the right shape for the source-code
handling on the way (CHATDRILL whole codebases; LaTeX `lstlisting`s — TiddlyWiki
gives a code snippet its own type + file). `--no-sidecar` falls back to collapsing
multi-line fields to one line in the `.meta`.

CLI:  python3 tools/tiddlers_to_md.py <bibkey>.tiddlers.json [--out DIR] [--bibkey K] [--no-sidecar]
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
# Field order: identity first, then the rest alphabetically (stable diffs).
_LEAD_FIELDS = ("title", "type", "tags", "caption", "created", "modified")
# Fields whose value is CODE / markup → a clean sidecar file with this extension
# (verbatim, no escaping). Any OTHER field carrying a newline → a `.txt` sidecar.
_CODE_EXT = {
    "lean4": "lean", "svg_tiddler": "svg", "latex_code": "tex",
    "latex_original": "tex", "bibtex": "bib", "code": "txt",
}
# An image tiddler (`type: image/*`) is written as the IMAGE FILE (<title>.<ext>)
# + a `<title>.<ext>.meta` sidecar, so TiddlyWiki transcludes it as `{{title}}`
# (no `<$image>` widget) via the file's _canonical_uri.
_IMAGE_EXT = {
    "image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
    "image/gif": "gif", "image/webp": "webp", "image/svg+xml": "svg",
    "image/tiff": "tif", "image/bmp": "bmp",
}


def _decode_image_source(t: dict, src_dir):
    """(bytes|None, ext) for an image tiddler. Bytes come from a `data:` URI, a
    LOCAL-file `_canonical_uri`/`canonical_uri`, or a base64 `text` field; None
    when the source is a remote URL (then only the .meta is written, URL kept)."""
    import base64
    mime = (t.get("type") or "").strip().lower()
    ext = _IMAGE_EXT.get(mime, "png")
    uri = (t.get("_canonical_uri") or t.get("canonical_uri") or "").strip()
    if uri.startswith("data:"):
        m = re.match(r"data:([^;,]*)(;base64)?,(.*)$", uri, re.S)
        if m:
            ext = _IMAGE_EXT.get(m.group(1), ext)
            body = m.group(3)
            return (base64.b64decode(body) if m.group(2) else body.encode()), ext
    if uri and not re.match(r"^https?://", uri):                  # local file
        p = Path(uri)
        if src_dir and not p.is_absolute():
            p = Path(src_dir) / uri
        if p.is_file():
            return p.read_bytes(), (p.suffix.lstrip(".").lower() or ext)
    txt = (t.get("text") or "").strip()
    if txt and not uri:                                          # base64 in text
        try:
            return base64.b64decode(txt), ext
        except Exception:
            pass
    return None, ext                                            # remote/unresolved


def safe_filename(title: str) -> str:
    """A filesystem-safe basename derived from a tiddler title (kept ≤180 chars).
    The exact title is preserved in the `.md.meta` `title:` field."""
    name = _UNSAFE.sub("_", title or "").strip().strip(".") or "untitled"
    return name[:180]


def _meta_value(v) -> str:
    """A single-line `.meta` value (TiddlyWiki fields are single-line)."""
    s = "" if v is None else str(v)
    return s.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")


def _is_sidecar_field(field: str, value) -> bool:
    """A field is externalised to its own clean file if it is a known code field,
    or its value spans multiple lines (can't live in a single-line .meta)."""
    return field in _CODE_EXT or ("\n" in ("" if value is None else str(value)))


def tiddler_files(t: dict, base: str = "", *, sidecar: bool = True) -> tuple[str, str, dict]:
    """Return (md_text, meta_text, sidecars) for one tiddler dict.

    `sidecars` maps a relative filename → verbatim content for each code /
    multi-line field; the `.meta` then points the field at that filename. With
    `sidecar=False` (legacy), multi-line fields are collapsed to one line."""
    md = t.get("text", "") or ""
    sidecars: dict[str, str] = {}
    meta_val: dict[str, str] = {}
    used = set()
    for k, v in t.items():
        if k == "text":
            continue
        if sidecar and base and _is_sidecar_field(k, v):
            ext = _CODE_EXT.get(k, "txt")
            name = f"{base}.{ext}"
            if name in used:                       # rare: two same-ext fields
                name = f"{base}.{k}.{ext}"
            used.add(name)
            sidecars[name] = "" if v is None else str(v)
            meta_val[k] = name                     # field → sidecar filename
        else:
            meta_val[k] = _meta_value(v)
    keys = ([k for k in _LEAD_FIELDS if k in meta_val]
            + sorted(k for k in meta_val if k not in _LEAD_FIELDS))
    meta = "\n".join(f"{k}: {meta_val[k]}" for k in keys) + "\n"
    return md, meta, sidecars


def export_tiddlers(tiddlers, out_dir, bibkey: str | None = None,
                    *, sidecar: bool = True, src_dir=None) -> tuple[int, Path, int]:
    """Write every tiddler as `<title>.md` + `<title>.md.meta` under
    `<out_dir>/<bibkey>/`, plus a clean sidecar per code/multi-line field. An
    `image/*` tiddler is written as the IMAGE FILE `<title>.<ext>` +
    `<title>.<ext>.meta` instead (transcluded as `{{title}}`, no `<$image>`).
    `src_dir` resolves a tiddler's relative local image path (default: cwd).
    Returns (tiddler_count, folder, extra_file_count)."""
    out = Path(out_dir)
    if bibkey:
        out = out / safe_filename(bibkey)
    out.mkdir(parents=True, exist_ok=True)
    seen: dict[str, int] = {}
    written = extra_written = 0
    for t in tiddlers:
        base = safe_filename(t.get("title") or f"tiddler_{written}")
        if base in seen:                                   # disambiguate collisions
            seen[base] += 1
            base = f"{base}~{seen[base]}"
        else:
            seen[base] = 0
        if (t.get("type") or "").lower().startswith("image/"):
            data, ext = _decode_image_source(t, src_dir)
            fname = f"{base}.{ext}"
            meta_val = {k: _meta_value(v) for k, v in t.items() if k != "text"}
            if data is not None:                           # write the bytes + point at them
                (out / fname).write_bytes(data)
                meta_val["_canonical_uri"] = fname
                extra_written += 1
            keys = ([k for k in _LEAD_FIELDS if k in meta_val]
                    + sorted(k for k in meta_val if k not in _LEAD_FIELDS))
            (out / f"{fname}.meta").write_text(
                "\n".join(f"{k}: {meta_val[k]}" for k in keys) + "\n", encoding="utf-8")
            written += 1
            continue
        md, meta, sidecars = tiddler_files(t, base, sidecar=sidecar)
        (out / f"{base}.md").write_text(md, encoding="utf-8")
        (out / f"{base}.md.meta").write_text(meta, encoding="utf-8")
        for name, content in sidecars.items():
            (out / name).write_text(content, encoding="utf-8")
            extra_written += 1
        written += 1
    return written, out, extra_written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Export a pdfdrill tiddlers.json to .md + .md.meta files.")
    ap.add_argument("tiddlers_json")
    ap.add_argument("--out", default="tiddlers_md", help="output root directory")
    ap.add_argument("--bibkey", default=None,
                    help="subfolder name (default: the tiddlers.json filename stem)")
    ap.add_argument("--no-sidecar", action="store_true",
                    help="collapse multi-line fields into the .meta (no code sidecars)")
    a = ap.parse_args(argv)
    p = Path(a.tiddlers_json)
    data = json.loads(p.read_text(encoding="utf-8"))
    bibkey = a.bibkey or p.name.split(".tiddlers")[0]
    n, out, side = export_tiddlers(data, a.out, bibkey, sidecar=not a.no_sidecar,
                                   src_dir=p.parent)
    print(f"Wrote {n} tiddler(s) as .md/.md.meta (image tiddlers as <name>.<ext>+"
          f".meta)" + (f" + {side} sidecar/image file(s)" if side else "")
          + f" under {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
