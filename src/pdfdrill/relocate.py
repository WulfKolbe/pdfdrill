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


def legacy_remnants(pdf: Path) -> bool:
    r"""True when a PDF still has the pre-migration furniture beside it —
    `X.pdf.drill.json` and/or an `X.pdf.drill/` blob directory.

    839 — THE FOLDER'S NAME IS NOT THE LAYOUT. `plan_relocation` and
    `find_docs` both treated "the parent folder is named after the PDF" as
    "already migrated", and the two came apart on three documents moved in
    from ~/Downloads: each was `<stem>/<stem>.pdf`, correctly named, with
    `<stem>.pdf.drill/` and `<stem>.pdf.drill.json` still inside it. pdfdrill
    looks for `<stem>.drill.json`, so `status` answered "No information
    gathered yet" for documents carrying a model, tiddlers and a semantic
    graph — 31 to 83 files of work, invisible, and `relocate` skipped them as
    done.

    The canonical layout has neither name (its sidecar is `X.drill.json`, with
    no `.pdf` in it), so this is unambiguous and costs two stat calls.
    """
    d = pdf.parent
    return ((d / f"{pdf.name}.drill.json").exists()
            or (d / f"{pdf.name}.drill").is_dir())


#: The sibling suffixes ONLY pdfdrill writes beside a document: its readings,
#: caches, inspector and the e-print it downloaded. P11 — the automatic filing
#: (`doclock.ensure_doc_folder`) moves these and nothing else. Names an OWNER
#: writes too (`X.tex` beside the `X.pdf` it makes, `X.md`, `X.log`, `X.bib`,
#: `X.txt`, a script's `X.out`) are never moved without being asked: one of
#: them moved is lost work, one left behind is a projection rebuilt.
PDFDRILL_SUFFIXES = (
    ".lines.json", ".glyphs.md", ".glyphs.tex", ".mathpix.bak.json",
    ".lines.mathpix.bak.json", ".mathpix.lines.json", ".drill.json",
    ".tiddlers.json", ".yolo.tsv", ".labels.json", ".struct.md",
    ".profile.json", ".equations.json", ".eqglyphs.json", ".chars.json",
    ".chars.bak.json", ".incomplete", ".scan.png", ".inspect.html",
    ".docmodel.json", ".docpack", ".tex.zip", ".tgz", ".llm.txt",
    ".ingest.json",
)

#: The owner's INPUTS that a build reads beside the PDF: `X.bib`
#: (`_load_bib_sidecar`) and `X.md`. pdfdrill does not write them, so the
#: automatic filing never moves them; it COPIES them into the new folder, so
#: the owner's file stays where it was and the build still finds its input.
OWNER_INPUTS = (".bib", ".md")

#: (src, dst) of every move the last `apply_relocation` made, and every copy.
LAST_MOVES: list = []
LAST_COPIES: list = []


def plan_relocation(pdf: str | Path, library: str | Path,
                    owned_only: bool = False) -> list[tuple[Path, Path]]:
    """The ordered (src, dst) moves that migrate `pdf` into `<library>/<stem>/`.

    Empty when the doc is already self-contained (its parent IS `<library>/<stem>`).
    Pure: no disk writes. Order: PDF → sidecar state → blob contents → loose
    siblings, so the destination folder is created by the first move.
    """
    pdf = Path(pdf).resolve()
    library = Path(library).resolve()
    stem = pdf.stem
    target = library / stem
    if pdf.parent == target and not legacy_remnants(pdf):
        return []                                   # already self-contained

    d = pdf.parent
    sidecar = d / f"{pdf.name}.drill.json"
    blob = d / f"{pdf.name}.drill"

    # A PDF already sitting in its own folder does not move; only the legacy
    # layout AROUND it does (839).
    moves: list[tuple[Path, Path]] = []
    if pdf.parent != target:
        moves.append((pdf, target / pdf.name))
    if sidecar.exists():
        moves.append((sidecar, target / f"{stem}.drill.json"))
    if blob.is_dir():
        for item in sorted(blob.iterdir()):
            moves.append((item, target / item.name))   # flatten blob into the folder

    handled = {pdf, sidecar, blob}
    for sib in sorted(d.glob(_glob.escape(stem) + ".*")):
        if sib in handled or sib.is_dir():
            continue
        if owned_only and not sib.name.endswith(PDFDRILL_SUFFIXES):
            continue                                    # not ours: it stays (P11)
        moves.append((sib, target / sib.name))          # X.* data siblings
    return moves


def apply_relocation(pdf: str | Path, library: str | Path,
                     owned_only: bool = False) -> tuple[int, int]:
    """Execute the plan with shutil.move. Returns (moved, skipped). A destination
    that already exists is SKIPPED (never overwritten) — collision-safe and
    idempotent. Empties the old blob dir afterwards. Every move made is in
    `LAST_MOVES`."""
    LAST_MOVES.clear()
    LAST_COPIES.clear()
    plan = plan_relocation(pdf, library, owned_only=owned_only)
    if not plan:
        return (0, 0)
    if owned_only:
        _p = Path(pdf).resolve()
        _target = Path(library).resolve() / _p.stem
        for ext in OWNER_INPUTS:
            src = _p.parent / f"{_p.stem}{ext}"
            dst = _target / src.name
            if src.is_file() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))
                LAST_COPIES.append((src, dst))
    moved = skipped = 0
    for src, dst in plan:
        if not src.exists():
            continue
        if dst.exists():
            skipped += 1
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        LAST_MOVES.append((src, dst))
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
        if anc / f"{anc.name}.pdf" == pdf:
            continue        # 839 — its OWN folder. The guard is about being
            # inside SOMEONE ELSE's document; a half-migrated doc sits in a
            # folder named after itself and was excluded by its own PDF, so
            # `find_docs` returned nothing for exactly the documents that
            # needed migrating.
        if (anc / f"{anc.name}.pdf").exists():
            return True
    return False


def find_docs(root: str | Path) -> list[Path]:
    """Every legacy PDF under `root` that is NOT already self-contained — i.e.
    PDFs whose parent folder isn't named after them, OR which still carry the
    legacy furniture beside them (`legacy_remnants`, 839), and which do not
    live inside some other document's folder. Recursive."""
    root = Path(root).resolve()
    out: list[Path] = []
    for pdf in sorted(root.rglob("*.pdf")):
        if pdf.parent.name == pdf.stem and not legacy_remnants(pdf):
            continue                                # already migrated
        if _inside_a_doc_folder(pdf, root):
            continue                                # an artifact, not a document
        out.append(pdf)
    return out
