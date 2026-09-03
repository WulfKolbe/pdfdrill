r"""560 — one place that answers "which tiddler array is this document's".

Four production sites globbed `*.tiddlers.json` and took whatever came
first. `Path.glob` yields FILESYSTEM order, not sorted order and not stable
between documents: with the nine pre-rename duplicates on disk, 558 measured
it returning the current file on five documents and a two-day-old one on
gilmore, johnston, lyche and mielke — `corrections.py`'s identifier join
among the affected. Deleting the duplicates made the glob correct; it did
not make it right, and the next rename would put it back.

THE ORDER, and every step of it is a fact rather than a guess:

  1. the sidecar's recorded `tiddlers_path` — the writer said where it wrote
  2. `<bibkey>.tiddlers.json`, the name `cmd_tiddlers` builds from the model
  3. `<stem>.tiddlers.json`, the pre-rename name
  4. the NEWEST `*.tiddlers.json` — never the first one the filesystem hands
     back. If a document really does carry two, the newer is the projection
     of the current model.

A folder is enough. `_tiddlers_path` in commands.py needs a `pdf` and a
`Sidecar`, which the corpus-wide callers do not have.
"""
from __future__ import annotations

import json
from pathlib import Path


def _sidecar_of(doc_dir: Path) -> "Path | None":
    """The document's own sidecar, not a stray one.

    A folder can hold more than one `*.drill.json`: 545 drilled `B.pdf` by
    accident and left `B.pdf.drill.json` beside the real one. Prefer a
    sidecar whose stem matches a PDF that is not an output of ours.
    """
    cands = sorted(doc_dir.glob("*.drill.json"))
    if not cands:
        return None
    outputs = {"B.pdf", "report.pdf"}
    for c in cands:
        stem = c.name[:-len(".drill.json")]
        if stem + ".pdf" not in outputs and (doc_dir / (stem + ".pdf")).is_file():
            return c
    return cands[0]


def tiddlers_in(doc_dir) -> "Path | None":
    """This document's current tiddler array, or None."""
    doc_dir = Path(doc_dir)
    if not doc_dir.is_dir():
        return None
    sc = _sidecar_of(doc_dir)
    if sc is not None:
        try:
            ev = (json.loads(sc.read_text(encoding="utf-8", errors="replace"))
                  .get("evidence") or {})
            rel = ev.get("tiddlers_path")
            bib = ev.get("bibkey")
        except (OSError, ValueError):
            rel = bib = None
        if rel:
            p = doc_dir / rel
            if p.is_file() and p.stat().st_size > 0:
                return p
        if bib:
            p = doc_dir / ("%s.tiddlers.json" % bib)
            if p.is_file() and p.stat().st_size > 0:
                return p
        stem = sc.name[:-len(".drill.json")]
        p = doc_dir / ("%s.tiddlers.json" % stem)
        if p.is_file() and p.stat().st_size > 0:
            return p
    hits = [p for p in doc_dir.glob("*.tiddlers.json")
            if p.is_file() and p.stat().st_size > 0]
    if not hits:
        return None
    return max(hits, key=lambda p: p.stat().st_mtime)
