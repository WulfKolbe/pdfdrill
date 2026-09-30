"""Which pdf2mmd produced this artefact.

Promoted out of `out/eqtable_716.py`, where 753 had already worked out the
hard part and only the table could use it. 785 needed the same answer about a
document's `mmd-out/` and there was nothing in the output to ask: `report.txt`
recorded document, pages, glyphs, lines, maths spans and deferrals, and not one
word about the reader. Two installs existed on that machine — a checkout at
784 and a standalone copy frozen days earlier — and the only way to tell their
results apart was the file mtime, which is evidence about the filesystem and
not about the code.

Three rules, each learned rather than assumed:

  * A COMMIT, when there is one. It cannot drift.
  * `+local changes` when the tree is dirty, because a checkout plus edits is
    not the commit it claims to be.
  * A CONTENT DIGEST when the tree is not a checkout — NOT the newest mtime
    753 fell back to. That fallback is exactly what failed here: copying a
    tree rewrites every mtime, so the copy and its original report different
    revisions while being byte-identical, and a copy made twice reports two.
    The digest of the sources is the same number wherever the tree is, which
    is the whole point of an identity.
"""
from __future__ import annotations

import datetime
import hashlib
import os
import subprocess
from pathlib import Path

#: The tree to describe. Overridable so a caller running from elsewhere still
#: names the code that is actually imported.
CODE_DIR = Path(os.environ.get(
    "PDF2MMD_CODE", Path(__file__).resolve().parent))


def _git(*args, cwd: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(cwd), *args],
                              capture_output=True, text=True,
                              timeout=30).stdout.strip()
    except Exception:
        return ""


def _tree_digest(src: Path) -> str:
    """sha256 over the sources themselves, so a copy keeps its identity."""
    h = hashlib.sha256()
    for f in sorted(src.glob("*.py")):
        try:
            h.update(f.name.encode())
            h.update(f.read_bytes())
        except OSError:
            continue
    return h.hexdigest()[:12]


def identity(src: Path | None = None) -> dict:
    """`{kind, rev, when, dirty}` — machine-readable, for a JSON artefact."""
    src = Path(src) if src else CODE_DIR
    head = _git("rev-parse", "--short", "HEAD", cwd=src)
    if head:
        return {
            "kind": "git",
            "rev": head,
            "when": _git("log", "-1", "--format=%cd",
                         "--date=format:%Y-%m-%d %H:%M", cwd=src),
            "dirty": bool(_git("status", "--porcelain", cwd=src)),
        }
    return {"kind": "tree", "rev": _tree_digest(src), "when": None,
            "dirty": False}


def stamp(src: Path | None = None) -> str:
    """One line naming the reader, for a human-readable report."""
    i = identity(src)
    dirty = " +local changes" if i["dirty"] else ""
    if i["kind"] == "git":
        return "pdf2mmd %s of %s%s" % (i["rev"], i["when"], dirty)
    # Not a checkout. Say so plainly: a digest is an identity, not a version,
    # and a reader must not mistake it for one.
    return "pdf2mmd tree:%s (not a checkout)" % i["rev"]


def built_line(src: Path | None = None) -> str:
    """The stamp plus when this run happened — the report's first line."""
    return "%s — run %s" % (
        stamp(src), datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
