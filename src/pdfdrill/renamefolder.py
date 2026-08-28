"""
Folder rename (276), built on the inventory 275 measured.

A drilled folder carries its name in four different ways, and they need four
different treatments:

  A  PATH-DERIVED   the directory itself and the `<stem>.*` files in it. A move.
  B  BIBKEY-DERIVED `report-crops/<bibkey>_EQ0001.jpg`, `okf/<bibkey>/**`. A
                    move, but only when the bibkey is being changed too, and
                    always through `sanitize_title` — `0111016 (1)` is on disk
                    as `0111016__1_`.
  C  CONTENT        the old name inside JSON, at NAMED FIELDS: `meta.bibkey`,
                    `meta.source_path`, `props.bibkey`, every tiddler `title`,
                    the sidecar's path evidence, `\\ident{}` in report.tex.
  D  UNTOUCHABLE    the same string as the document's own words.

D is what rules out the obvious implementation. A drilled arXiv folder is named
for its arXiv id, and that id is printed down the margin of page 1 — so it is in
`lines.json` `"text"`, in `probe-page-text.json`, in `pdfinfo.Title` and in the
BibTeX derived from it. A substitution over the folder would rewrite the
document's own text and its citation. Everything below edits a NAMED FIELD or
moves a FILE; nothing matches the old name against free text.

The stem and the bibkey are separable — 264 showed they already diverge in
practice — so renaming the folder does NOT rename the object namespace unless
asked. Both prior names are recorded on the model: `meta.folder_history` and
`meta.bibkey_history`.

No rebuild. 275 measured what one costs: 7 documents carry the TRANSLATED fact,
2 of them already hold zero translated units, and one holds 81 with no fact at
all, so the existing guard cannot see it.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any, Optional

from .report_tex import sanitize_title

#: Sidecar evidence keys whose value is a path relative to the folder.
_PATH_EVIDENCE_SUFFIX = ("_path",)

#: Model/docpack meta keys holding a filesystem path.
_META_PATH_KEYS = ("source_path",)


class RenameRefused(Exception):
    """The rename cannot proceed; nothing has been touched."""


def stem_files(folder: Path, stem: str) -> list[Path]:
    """The `<stem>.*` files in `folder` — group A."""
    return sorted(p for p in folder.iterdir()
                  if p.is_file() and (p.name == stem or p.name.startswith(stem + ".")))


def _rewrite_json(path: Path, fn) -> bool:
    """Load, hand to `fn`, write back if it returns True. Atomic-ish."""
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not fn(data):
        return False
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)
    return True


def _retarget_meta(meta: dict, old_stem: str, new_stem: str,
                   old_key: Optional[str], new_key: Optional[str]) -> bool:
    changed = False
    for k in _META_PATH_KEYS:
        v = meta.get(k)
        if isinstance(v, str) and v:
            # Only the PATH SEGMENT equal to the old stem, never a substring of
            # some other component.
            parts = [new_stem if seg == old_stem else seg for seg in Path(v).parts]
            nv = str(Path(*parts)) if parts else v
            nv = re.sub(rf"(^|/){re.escape(old_stem)}\.", rf"\g<1>{new_stem}.", nv)
            if nv != v:
                meta[k] = nv
                changed = True
    hist = [h for h in (meta.get("folder_history") or []) if h != old_stem]
    hist.append(old_stem)
    meta["folder_history"] = hist
    changed = True
    if old_key and new_key and old_key != new_key:
        if meta.get("bibkey") == old_key:
            meta["bibkey"] = new_key
        if meta.get("root_id") == old_key:
            meta["root_id"] = new_key
        bh = [h for h in (meta.get("bibkey_history") or []) if h != old_key]
        bh.append(old_key)
        meta["bibkey_history"] = bh
    return changed


def _retarget_model(data: dict, old_stem, new_stem, old_key, new_key) -> bool:
    changed = _retarget_meta(data.setdefault("meta", {}),
                             old_stem, new_stem, old_key, new_key)
    if not (old_key and new_key and old_key != new_key):
        return changed
    objs = data.get("objects")
    objs = list(objs.values()) if isinstance(objs, dict) else (objs or [])
    for o in objs:
        # The Document root object's `id` IS the bibkey; meta.root_id was being
        # updated while the object it names was not.
        if o.get("type") == "Document" and o.get("id") == old_key:
            o["id"] = new_key
            changed = True
        props = o.get("props") or {}
        if props.get("bibkey") == old_key:
            props["bibkey"] = new_key
            changed = True
        ps = props.get("parent_section")
        if isinstance(ps, str) and ps.startswith(old_key):
            props["parent_section"] = new_key + ps[len(old_key):]
            changed = True
    return changed


def _retarget_sidecar(data: dict, old_stem, new_stem, old_key, new_key) -> bool:
    changed = False
    pdf = data.get("pdf")
    if isinstance(pdf, str) and pdf.startswith(old_stem + "."):
        data["pdf"] = new_stem + pdf[len(old_stem):]
        changed = True
    ev = data.get("evidence") or {}
    # Nested path lists — `evidence.mathpix_files[i].path` — are real paths and
    # were missed by a rule that only looked at top-level `*_path` KEYS.
    def _walk_paths(node) -> int:
        hits = 0
        if isinstance(node, dict):
            for kk, vv in list(node.items()):
                if kk == "path" and isinstance(vv, str) and vv.startswith(old_stem + "."):
                    node[kk] = new_stem + vv[len(old_stem):]
                    hits += 1
                else:
                    hits += _walk_paths(vv)
        elif isinstance(node, list):
            for vv in node:
                hits += _walk_paths(vv)
        return hits
    if _walk_paths(ev):
        changed = True
    for k, v in list(ev.items()):
        if not isinstance(v, str) or not v:
            continue
        if k.endswith(_PATH_EVIDENCE_SUFFIX):
            nv = re.sub(rf"(^|/){re.escape(old_stem)}\.", rf"\g<1>{new_stem}.", v)
            if old_key and new_key:
                nv = re.sub(rf"(^|/){re.escape(sanitize_title(old_key))}(/|$)",
                            rf"\g<1>{sanitize_title(new_key)}\g<2>", nv)
            if nv != v:
                ev[k] = nv
                changed = True
    if old_key and new_key and old_key != new_key and ev.get("bibkey") == old_key:
        ev["bibkey"] = new_key
        changed = True
    return changed


def _retarget_tiddlers(data: Any, old_key, new_key) -> bool:
    """Every tiddler `title` in the bibkey namespace, and nothing else."""
    if not (old_key and new_key and old_key != new_key) or not isinstance(data, list):
        return False
    o, n = sanitize_title(old_key), sanitize_title(new_key)
    changed = False
    for t in data:
        if not isinstance(t, dict):
            continue
        for field in ("title", "caption_of", "parent_section"):
            v = t.get(field)
            if isinstance(v, str) and (v == o or v.startswith(o + "_")):
                t[field] = n + v[len(o):]
                changed = True
        # The bibkey is also a whitespace-delimited TAG on every tiddler
        # ("formula 0008113v1"). 341 of the 341 residual hits in the first run
        # were this, not a broken reference.
        tags = t.get("tags")
        if isinstance(tags, str) and tags:
            parts = [n if x == o else x for x in tags.split()]
            if parts != tags.split():
                t["tags"] = " ".join(parts)
                changed = True
        # Transclusions and links inside the body, anchored to `<key>_`.
        body = t.get("text")
        if isinstance(body, str) and o + "_" in body:
            t["text"] = body.replace(o + "_", n + "_")
            changed = True
    return changed


def rename_report_tex(path: Path, old_key: str, new_key: str) -> int:
    """`\\ident{<key>_…}` and `report-crops/<key>_….jpg`, anchored — never a
    bare substitution, because the key may also be printed inside a formula."""
    if not path.exists() or old_key == new_key:
        return 0
    o, n = sanitize_title(old_key), sanitize_title(new_key)
    text = path.read_text(encoding="utf-8", errors="replace")
    # LaTeX writes the underscore as `\_\allowbreak{}`, so an `_`-anchored
    # pattern matched none of the 97 \ident{} sites on the first run.
    us = r"(?:_|\\_(?:\\allowbreak\{\})?)"
    out, n1 = re.subn(rf"(\\ident\{{){re.escape(o)}(?={us})", rf"\g<1>{n}", text)
    out, n2 = re.subn(rf"(report-crops/){re.escape(o)}(_)", rf"\g<1>{n}\g<2>", out)
    # The report's own title line.
    out, n3 = re.subn(rf"(\\section\*\{{){re.escape(o)}(\s)", rf"\g<1>{n}\g<2>", out)
    if n1 + n2 + n3:
        path.write_text(out, encoding="utf-8")
    return n1 + n2 + n3


def rename_bibkey_files(folder: Path, old_key: str, new_key: str) -> int:
    """Group B: crops and the OKF bundle, through `sanitize_title` both ways."""
    if old_key == new_key:
        return 0
    o, n = sanitize_title(old_key), sanitize_title(new_key)
    moved = 0
    crops = folder / "report-crops"
    if crops.is_dir():
        for f in sorted(crops.iterdir()):
            if f.is_file() and f.name.startswith(o + "_"):
                f.rename(crops / (n + f.name[len(o):]))
                moved += 1
    okf = folder / "okf" / o
    if okf.is_dir():
        for f in sorted(okf.rglob("*")):
            if f.is_file() and f.name.startswith(o + "_"):
                f.rename(f.parent / (n + f.name[len(o):]))
                moved += 1
        okf.rename(okf.parent / n)
        moved += 1
        # The bundle's own cross-links, `resource:` URIs and bibkey tag. Renaming
        # the FILES without this leaves every relative link pointing at a name
        # that no longer exists — worse than not renaming them at all.
        #
        # Anchored on `<key>_`, `pdfdrill:<key>/` and the tag token, because a
        # paragraph body legitimately contains the bare stem: the folder is
        # named for the arXiv id and the id is printed on page 1.
        for f in sorted((okf.parent / n).rglob("*.md")):
            t = f.read_text(encoding="utf-8", errors="replace")
            u = t.replace(f"{o}_", f"{n}_").replace(f"pdfdrill:{o}/", f"pdfdrill:{n}/")
            u = re.sub(rf"^(tags:.*?[\[,\s]){re.escape(o)}(\s*[\],])", rf"\g<1>{n}\g<2>",
                       u, flags=re.M)
            if u != t:
                f.write_text(u, encoding="utf-8")
    return moved


def plan(folder: Path, new_stem: str, new_key: Optional[str] = None) -> dict:
    """What the rename would do. Raises RenameRefused if it must not run."""
    folder = folder.resolve()
    if not folder.is_dir():
        raise RenameRefused(f"not a directory: {folder}")
    old_stem = folder.name
    if not new_stem or new_stem in (".", "..") or "/" in new_stem:
        raise RenameRefused(f"not a usable folder name: {new_stem!r}")
    target = folder.parent / new_stem
    if target.exists() and target != folder:
        raise RenameRefused(f"target already exists: {target}")
    sidecar = folder / f"{old_stem}.drill.json"
    old_key = None
    if sidecar.exists():
        try:
            old_key = ((json.loads(sidecar.read_text(encoding="utf-8"))
                        .get("evidence") or {}).get("bibkey"))
        except Exception:
            old_key = None
    old_key = old_key or old_stem
    return {
        "folder": folder, "target": target,
        "old_stem": old_stem, "new_stem": new_stem,
        "old_bibkey": old_key, "new_bibkey": new_key or old_key,
        "stem_files": [p.name for p in stem_files(folder, old_stem)],
        "renames_bibkey": bool(new_key and new_key != old_key),
    }


def rename_folder(folder: Path, new_stem: str, new_key: Optional[str] = None) -> dict:
    """Do it. Returns the plan plus counts. No rebuild, no substitution."""
    p = plan(folder, new_stem, new_key)
    old_stem, new_stem = p["old_stem"], p["new_stem"]
    old_key, new_key = p["old_bibkey"], p["new_bibkey"]
    src: Path = p["folder"]

    # A — the directory, then the <stem>.* files inside it.
    dst: Path = p["target"]
    if dst != src:
        src.rename(dst)
    renamed = 0
    for f in stem_files(dst, old_stem):
        f.rename(dst / (new_stem + f.name[len(old_stem):]))
        renamed += 1

    # B — crops and the OKF bundle (only when the bibkey moves).
    moved = rename_bibkey_files(dst, old_key, new_key)

    # C — named fields only.
    model = dst / "model.docmodel.json"
    pack = dst / "model.docpack.json"
    sidecar = dst / f"{new_stem}.drill.json"
    tid = dst / f"{new_stem}.tiddlers.json"
    _rewrite_json(model, lambda d: _retarget_model(d, old_stem, new_stem, old_key, new_key))
    # The docpack is a PACKED, string-interned cache of the model — the same
    # `parent_section` value appears 127 times through an intern table, and
    # rewriting that format by hand is a worse risk than losing a cache. It is
    # derived, `load_model` falls back to the plain model when it is absent, and
    # the next `save_model` regenerates it. So: delete, don't edit.
    if pack.exists():
        pack.unlink()
    _rewrite_json(sidecar, lambda d: _retarget_sidecar(d, old_stem, new_stem, old_key, new_key))
    _rewrite_json(tid, lambda d: _retarget_tiddlers(d, old_key, new_key))
    tex_hits = rename_report_tex(dst / "report.tex", old_key, new_key)

    p.update({"stem_files_renamed": renamed, "bibkey_files_moved": moved,
              "report_tex_refs": tex_hits, "folder": dst,
              "docpack_invalidated": True})
    return p


def residue(folder: Path, old_stem: str, old_key: str = "") -> dict:
    """Where the OLD name still appears after a rename, by file, split into
    what is expected (the document's own words) and what is not."""
    folder = Path(folder)
    keys = {k for k in (old_stem, old_key, sanitize_title(old_key or "")) if k}
    # `.md` alone matched every generated okf unit file and buried real residue
    # in the "expected" bucket on the first run. Only the document's OWN
    # markdown is expected to contain its name.
    #
    # These are named from the folder's CURRENT stem, not the old one: residue
    # is measured AFTER the rename, so `<old>.lines.json` no longer exists and
    # a list built from `old_stem` matches nothing and reports every expected
    # hit as a leftover.
    cur = folder.name
    expected_files = {f"{cur}.lines.json", "probe-page-text.json",
                      f"{cur}.md", "report.log"}
    out: dict[str, Any] = {"expected": {}, "UNEXPECTED": {}}
    for f in sorted(folder.rglob("*")):
        if not f.is_file() or f.suffix in (".jpg", ".png", ".pdf", ".zip", ".tgz"):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        n = sum(text.count(k) for k in keys)
        if not n:
            continue
        rel = str(f.relative_to(folder))
        bucket = ("expected" if rel in expected_files or
                  any(rel.endswith("/" + e) for e in expected_files)
                  else "UNEXPECTED")
        out[bucket][rel] = n
    return out
