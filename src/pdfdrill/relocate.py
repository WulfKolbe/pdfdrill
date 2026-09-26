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


def _inside_a_doc_folder(pdf: Path, root: Path) -> bool:
    """True when `pdf` lies anywhere INSIDE an already-migrated doc folder.

    A migrated folder is full of PDFs that are not documents: `report.pdf`,
    `evidence-equation.pdf`, `residuals.pdf`, the rendered crops. Judging them
    one at a time by `parent.name == stem` calls every one of them a legacy
    scattered drill — and "relocating" them collapses hundreds of different
    documents' artifacts into a single `<library>/report/`, each overwriting
    the last. Measured on this library: of 8,460 PDFs whose parent is not named
    after them, **7,353 are artifacts inside someone else's doc folder** — and
    `relocate --apply` over the library root would have moved every one.

    The containing folder is the unit, not the file. An ancestor holding
    `<its own name>.pdf` IS a doc folder, and everything below it is its
    property.
    """
    for anc in pdf.parents:
        if anc == root or root not in anc.parents:
            break                                   # at or above the library
        if (anc / f"{anc.name}.pdf").exists():
            return True
    return False


def find_docs(root: str | Path) -> list[Path]:
    """Every legacy PDF under `root` that is NOT already self-contained — i.e.
    PDFs whose parent folder isn't named after them AND which do not live
    inside some other document's folder. Recursive."""
    root = Path(root).resolve()
    out: list[Path] = []
    for pdf in sorted(root.rglob("*.pdf")):
        if pdf.parent.name == pdf.stem:
            continue                                # already migrated
        if _inside_a_doc_folder(pdf, root):
            continue                                # an artifact, not a document
        out.append(pdf)
    return out
