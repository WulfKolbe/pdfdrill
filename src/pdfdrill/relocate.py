"""
`pdfdrill relocate` — migrate a legacy scattered drill into the self-contained
library layout.

Legacy (scattered next to the PDF):
    <dir>/X.pdf
    <dir>/X.lines.json            (+ any X.* data siblings: X.tex.zip, X.tgz, …)
    <dir>/X.pdf.drill.json        (sidecar STATE)
    <dir>/X.pdf.drill/…           (blob dir: model, tiddlers, texsrc/, svg/, …)

Self-contained (one folder per doc, everything together):
    <library>/X/X.pdf
    <library>/X/X.lines.json
    <library>/X/X.drill.json      (renamed from X.pdf.drill.json)
    <library>/X/model.docmodel.json …  (blob contents FLATTENED into the folder)

The Sidecar detects this layout (`parent.name == pdf.stem`) and uses the folder
itself as `blob_dir`, so once relocated every command Just Works.

`plan_relocation` is pure — it returns the ordered list of (src, dst) moves and
touches no disk — so it is testable and previewable. `apply_relocation` performs
the moves, refusing to overwrite (collision-safe). See
docs/superpowers/specs/2026-07-14-self-contained-doc-folders.md.
"""
from __future__ import annotations

import glob as _glob
import shutil
from pathlib import Path


def plan_relocation(pdf: str | Path, library: str | Path) -> list[tuple[Path, Path]]:
    """The ordered (src, dst) moves that migrate `pdf` into `<library>/<stem>/`.

    Empty when the doc is already self-contained (its parent IS `<library>/<stem>`).
    Pure: no disk writes. Order: PDF → sidecar state → blob contents → loose
    siblings, so the destination folder is created by the first move.
    """
    pdf = Path(pdf).resolve()
    library = Path(library).resolve()
    stem = pdf.stem
    target = library / stem
    if pdf.parent == target:
        return []                                   # already self-contained

    d = pdf.parent
    sidecar = d / f"{pdf.name}.drill.json"
    blob = d / f"{pdf.name}.drill"

    moves: list[tuple[Path, Path]] = [(pdf, target / pdf.name)]
    if sidecar.exists():
        moves.append((sidecar, target / f"{stem}.drill.json"))
    if blob.is_dir():
        for item in sorted(blob.iterdir()):
            moves.append((item, target / item.name))   # flatten blob into the folder

    handled = {pdf, sidecar, blob}
    for sib in sorted(d.glob(_glob.escape(stem) + ".*")):
        if sib in handled or sib.is_dir():
            continue
        moves.append((sib, target / sib.name))          # X.* data siblings
    return moves


def apply_relocation(pdf: str | Path, library: str | Path) -> tuple[int, int]:
    """Execute the plan with shutil.move. Returns (moved, skipped). A destination
    that already exists is SKIPPED (never overwritten) — collision-safe and
    idempotent. Empties the old blob dir afterwards."""
    plan = plan_relocation(pdf, library)
    if not plan:
        return (0, 0)
    moved = skipped = 0
    for src, dst in plan:
        if not src.exists():
            continue
        if dst.exists():
            skipped += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        moved += 1
    # remove the now-empty legacy blob dir if we drained it
    blob = Path(pdf).resolve().parent / f"{Path(pdf).name}.drill"
    try:
        if blob.is_dir() and not any(blob.iterdir()):
            blob.rmdir()
    except OSError:
        pass
    return (moved, skipped)


def find_docs(root: str | Path) -> list[Path]:
    """Every legacy PDF under `root` that is NOT already self-contained — i.e.
    PDFs whose parent folder isn't named after them. Recursive."""
    root = Path(root).resolve()
    out: list[Path] = []
    for pdf in sorted(root.rglob("*.pdf")):
        if pdf.parent.name == pdf.stem:
            continue                                # already migrated
        out.append(pdf)
    return out
