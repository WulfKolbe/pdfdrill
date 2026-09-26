"""`pdfdrill relocate` phase 2 — put the HOST in the folder name.

`<library>/1702.0234/` → `<library>/vixra.1702.0234/`, and every file inside
that carries the old stem with it (`1702.0234.drill.json` →
`vixra.1702.0234.drill.json`, `latex/1702.0234.tex` → `latex/vixra.…tex`).

Why this migration exists (807, and the defects behind it): a bare `1702.0234`
names a viXra e-print and a pre-2015 arXiv paper equally well. Fourteen folders
in this library were viXra while looking like arXiv (805), and `_augment_bibtex`
read an id off such a FILENAME and cited the wrong archive's paper (806).
`sources.archive_stem` fixed the name for NEW downloads; this fixes the ones
already on disk.

WHICH ARCHIVE — the precedence, and why it is not the obvious one
----------------------------------------------------------------
1. **Shape**, first, because it is arithmetic about the id space and cannot be
   wrong: arXiv went to five digits in 1501 and viXra never issued a five-digit
   or old-style id, so `2510.04618` is arXiv, `math_0309136` is arXiv, and a
   four-digit id from 1501 on is viXra.
2. **The download registry** — a real URL the user supplied, on a known host.
3. **The sidecar** (`bibtex.url` host, `evidence.source_arxiv_id`) — LAST,
   because it is DERIVED, and derived by the code 806 fixed. Measured on this
   library: nine viXra folders carry a sidecar bibtex saying
   `https://arxiv.org/abs/2505.0100v1`. Trusting the sidecar over the shape
   would have renamed all nine `arxiv.*` and written the 806 bug into the
   filesystem, where nothing would ever question it again.
4. No evidence → **skipped and named**, never guessed. Three folders here.

A rename never overwrites: any collision aborts that folder whole (no partial
rename), and the doc is reported.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import sources as S

# A new-style id: YYMM.NNNN (4) or YYMM.NNNNN (5), optional version.
_NEW = re.compile(r"^(\d{2})(\d{2})\.(\d{4,5})(v\d+)?$")
# An old-style arXiv id as it survives a filename: `math_0309136`, `hep-th_9901001`,
# `cond-mat.str-el_0309136` — the slash became an underscore (`archive_stem`).
_OLD = re.compile(r"^[a-z-]+(?:\.[A-Za-z-]{2,})?[_/]\d{7}(v\d+)?$")

# arXiv's five-digit era begins 1501; viXra has used four digits every year.
_FIVE_DIGIT_FROM = 1501

#: sidecar fields that hold a PATH or the bibkey — the only ones a rename may
#: touch. `evidence.source_arxiv_id` and every `bibtex.*` field hold the ID,
#: which the rename does NOT change; rewriting the stem blindly through the
#: JSON would turn the arXiv id into `arxiv.1107.2723` and break every free route.
_PATH_FIELDS = (("pdf",), ("evidence", "inspect_path"), ("evidence", "bibkey"))


def shape_kind(ident: str) -> Optional[str]:
    """The archive an id's SHAPE proves, or None when the shape allows both.

    Arithmetic, not inference: five digits or an old-style id is arXiv (viXra
    issued neither); four digits from 1501 on is viXra (arXiv had left four
    digits behind). Four digits up to 1412 is genuinely ambiguous — the case
    that needs evidence.
    """
    ident = (ident or "").strip()
    if _OLD.match(ident):
        return "arxiv"
    m = _NEW.match(ident)
    if not m:
        return None
    yymm = int(m.group(1) + m.group(2))
    if len(m.group(3)) == 5:
        return "arxiv"
    return "vixra" if yymm >= _FIVE_DIGIT_FROM else None


def looks_like_archive_id(stem: str) -> bool:
    """True for a bare archive-id stem — one this migration is about at all.

    An already-prefixed stem (`arxiv.2510.04618`) is NOT one: `archive_ident`
    resolves it, so it is done.
    """
    if not stem or S.archive_ident(stem):
        return False
    return bool(_NEW.match(stem) or _OLD.match(stem))


def registry_kind(stem: str, registry: dict) -> Optional[str]:
    """The archive proved by a download-registry URL whose file lives in this
    folder — the strongest evidence after the shape, because it is the URL the
    user actually handed us."""
    for url, entry in (registry or {}).items():
        fn = str((entry or {}).get("filename") or "")
        if fn.split("/")[0] != stem:
            continue
        kind = S.known_host(url)
        if kind in ("arxiv", "vixra"):
            return kind
    return None


def sidecar_kind(folder: Path, stem: str) -> Optional[str]:
    """The archive the sidecar CLAIMS — read last, and never over the shape.

    Tolerates a corrupt sidecar (three in this library are truncated JSON): a
    doc with an unreadable sidecar still has a shape and a registry entry, and
    a rename is not the place to fail on it.
    """
    sc = folder / f"{stem}.drill.json"
    if not sc.exists():
        return None
    try:
        data = json.loads(sc.read_text(encoding="utf-8"))
    except Exception:                                        # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None
    url = str(((data.get("bibtex") or {}) if isinstance(data.get("bibtex"), dict)
               else {}).get("url") or "")
    kind = S.known_host(url) if url else None
    if kind in ("arxiv", "vixra"):
        return kind
    ev = data.get("evidence") if isinstance(data.get("evidence"), dict) else {}
    if (ev or {}).get("source_arxiv_id"):
        return "arxiv"
    return None


@dataclass
class Rename:
    """One folder's migration. `moves` are (src, dst) absolute, folder LAST so
    the files inside are renamed in place first and the directory move is the
    single commit point."""
    folder: Path
    stem: str
    kind: str
    via: str                                   # shape | registry | sidecar
    new_stem: str
    new_folder: Path
    moves: list = field(default_factory=list)
    collisions: list = field(default_factory=list)
    bibtex_disagrees: bool = False

    @property
    def ok(self) -> bool:
        return not self.collisions


@dataclass
class Skip:
    folder: Path
    stem: str
    reason: str


def plan_rename(folder: Path, registry: Optional[dict] = None):
    """Plan one folder's host-prefix rename. Pure — no disk writes.

    Returns a `Rename`, a `Skip` (ambiguous / not an archive id), or None when
    the folder is already prefixed and there is nothing to do.
    """
    folder = Path(folder)
    stem = folder.name
    if not looks_like_archive_id(stem):
        return None

    kind, via = shape_kind(stem), "shape"
    if not kind:
        kind, via = registry_kind(stem, registry or {}), "registry"
    if not kind:
        kind, via = sidecar_kind(folder, stem), "sidecar"
    if not kind:
        return Skip(folder, stem,
                    "four-digit id from before 1501 — arXiv and viXra both use "
                    "this shape, and no URL, registry entry or sidecar says "
                    "which. Re-add it from its URL, or rename it by hand.")

    new_stem = S.archive_stem(kind, stem)
    new_folder = folder.parent / new_stem
    plan = Rename(folder=folder, stem=stem, kind=kind, via=via,
                  new_stem=new_stem, new_folder=new_folder)

    if new_folder.exists():
        plan.collisions.append(str(new_folder))
        return plan

    # every file that carries the old stem, at any depth
    for p in sorted(folder.rglob("*")):
        if p.is_dir():
            continue
        name = p.name
        if name == stem or name.startswith(stem + "."):
            dst = p.with_name(new_stem + name[len(stem):])
            if dst.exists():
                plan.collisions.append(str(dst))
            plan.moves.append((p, dst))

    # the sidecar's own bibtex may name the OTHER archive — the 806 residue.
    claimed = sidecar_kind(folder, stem)
    plan.bibtex_disagrees = bool(claimed and claimed != kind)
    return plan


def rewrite_sidecar(sidecar: Path, stem: str, new_stem: str) -> bool:
    """Point the sidecar's PATH fields at the new names. Returns True if written.

    Only `pdf`, `evidence.inspect_path` and `evidence.bibkey` — see `_PATH_FIELDS`.
    A corrupt sidecar is left exactly as it is rather than rewritten from a
    partial parse.
    """
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:                                        # noqa: BLE001
        return False
    if not isinstance(data, dict):
        return False
    changed = False
    for path in _PATH_FIELDS:
        node = data
        for key in path[:-1]:
            node = node.get(key) if isinstance(node, dict) else None
            if not isinstance(node, dict):
                node = None
                break
        if node is None:
            continue
        val = node.get(path[-1])
        if isinstance(val, str) and (val == stem or val.startswith(stem + ".")):
            node[path[-1]] = new_stem + val[len(stem):]
            changed = True
    if changed:
        tmp = sidecar.with_name(sidecar.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        tmp.replace(sidecar)
    return changed


def apply_rename(plan: Rename) -> int:
    """Execute one `Rename`. Files first, sidecar rewrite, folder last.

    Refuses outright when the plan carries a collision — a half-renamed doc is
    worse than an unrenamed one, so nothing moves.
    """
    if not isinstance(plan, Rename) or not plan.ok:
        return 0
    moved = 0
    for src, dst in plan.moves:
        if src.exists() and not dst.exists():
            src.rename(dst)
            moved += 1
    rewrite_sidecar(plan.folder / f"{plan.new_stem}.drill.json",
                    plan.stem, plan.new_stem)
    plan.folder.rename(plan.new_folder)
    return moved


def rewrite_registry(registry: dict, renames) -> int:
    """Repoint `pdfdrill-downloads.json` filenames at the renamed folders.

    The registry's KEY is the URL, so a rename touches only `filename` — whose
    value is `<folder>/<file>` relative to the library root. Left stale, the
    next `add <url>` finds no file at the recorded path and downloads the paper
    again. Returns the number of entries rewritten; mutates `registry`.
    """
    by_stem = {r.stem: r for r in renames if isinstance(r, Rename) and r.ok}
    n = 0
    for entry in (registry or {}).values():
        if not isinstance(entry, dict):
            continue
        fn = str(entry.get("filename") or "")
        head, _, tail = fn.partition("/")
        r = by_stem.get(head)
        if not r or not tail:
            continue
        name = tail
        if name == r.stem or name.startswith(r.stem + "."):
            name = r.new_stem + name[len(r.stem):]
        entry["filename"] = f"{r.new_stem}/{name}"
        n += 1
    return n


def find_folders(library: Path) -> list:
    """Every doc folder under `library` whose name is a bare archive id."""
    library = Path(library)
    if not library.is_dir():
        return []
    return [p for p in sorted(library.iterdir())
            if p.is_dir() and looks_like_archive_id(p.name)]
