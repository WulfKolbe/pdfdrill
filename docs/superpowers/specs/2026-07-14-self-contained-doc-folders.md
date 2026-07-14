# Self-contained document folders (one folder per drilled doc, PDF inside)

**Date:** 2026-07-14
**Status:** Design (brainstorming) — awaiting user review of this spec.
**Author:** wkolbe + Claude

## 1. Problem

For each drilled doc `X`, files are scattered across the download dir as loose
siblings:

```
X.pdf   X.lines.json   X.tex.zip   X.tgz   X.pdf.drill.json   X.pdf.drill/{model,md,tiddlers,texsrc,…}
```

The sidecar blob dir is a *sibling* of the PDF (`Sidecar.blob_dir =
pdf.parent/"<name>.drill"`), and the lines.json / tex.zip / e-print are loose in
the download dir. With hundreds of docs this is unmanageable: to open a doc's
`tiddlers.json` you dig into its `.drill/`, but the PDF isn't there — six-plus
locations per document, all interleaved with every other doc's files.

## 2. Goal

One **library root** (a git repo), one **self-contained folder per document**,
**everything for a doc inside its folder** — the PDF next to its `tiddlers.json`,
`model.docmodel.json`, `md`, etc. Plus a **migration command** to move the
existing hundreds of drills into this shape.

```
<library>/                          # a git repo (config `library_root`)
  2502.20855v2/                     # the doc folder = the "drill folder"
    2502.20855v2.pdf                # the PDF lives HERE
    2502.20855v2.drill.json         # sidecar state
    2502.20855v2.lines.json
    2502.20855v2.tex.zip
    model.docmodel.json  model.docpack.json
    2502.20855v2.md
    2502.20855v2.tiddlers.json
    2502.20855v2.llm.txt
    texsrc/  svg/  inspect/         # directory artifacts stay as subdirs
  1906.02691/
    …
```

## 3. Key decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | **Flat doc folder** — the PDF + all file artifacts live directly in `<stem>/`; only directory artifacts (`texsrc/`, `svg/`, `inspect/`, `ocr/`, `tiles/`) stay as subdirs. | The user's exact ask ("all files under its drill folder"); the tiddlers file sits right next to the PDF. |
| D2 | **Detection by name, no config flag:** a folder is a self-contained doc folder **iff it is named after its PDF** (`pdf.parent.name == pdf.stem`) → `blob_dir = pdf.parent`. | Deterministic, works during a mixed (half-migrated) state, needs no per-doc marker. |
| D3 | **Legacy sibling layout still works** — if `pdf.parent/"<name>.drill"` exists, use it. Ad-hoc PDFs (a one-off `pdfdrill md /tmp/x.pdf`, not in a doc folder) also get a sibling `.drill` (unchanged). | Backward-compatible; hundreds of un-migrated docs keep working; no surprise for one-off runs. |
| D4 | **`library_root` config** (default = the existing `download_dir`, e.g. `~/pdfdrill`). `add`/downloads place a doc at `<library_root>/<stem>/<stem>.pdf`. | "One git folder for all drilled documents"; least disruption (their current dir becomes the root). Overridable via `pdfdrill config --library-root`. |
| D5 | **`pdfdrill relocate` migration** — dry-run then `--apply`; MOVES each `X.pdf` + `X.*` siblings + `X.pdf.drill/*` into `<library>/X/`. Idempotent; skips already-migrated. | The user's explicit "cleanup and move script". |

## 4. Why the code change is small

`_lines_json_path(pdf)` already returns `pdf.parent / "<stem>.lines.json"`, and
the subdir artifacts are `blob_dir / "<name>"`. So once the PDF is **inside** the
doc folder (`pdf.parent == <stem>/`), lines.json/tex.zip already land in the doc
folder, and the ONLY path that must change is `Sidecar.blob_dir` (today
`pdf.parent/"<name>.drill"` → self-contained: `pdf.parent`).

## 5. Components

### 5.1 `Sidecar` (src/pdfdrill/sidecar.py) — the one real change
```python
legacy = pdf.parent / f"{pdf.name}.drill"
if pdf.parent.name == pdf.stem:              # self-contained doc folder
    self.blob_dir = pdf.parent
    self.json_path = pdf.parent / f"{pdf.stem}.drill.json"
elif legacy.exists():                         # legacy sibling (back-compat)
    self.blob_dir = legacy
    self.json_path = pdf.parent / f"{pdf.name}.drill.json"
else:                                         # ad-hoc PDF (unchanged default)
    self.blob_dir = legacy
    self.json_path = pdf.parent / f"{pdf.name}.drill.json"
```
Everything downstream (`_model_path = blob_dir/"model.docmodel.json"`, all
`blob_dir / "<x>"`) follows automatically. `model_io` (docmodel.json +
docpack.json in blob_dir) is unaffected.

### 5.2 `config.library_root()` (src/pdfdrill/config.py)
New key `library_root` (default = `download_dir()`). `pdfdrill config
--library-root <path>` sets it; `pdfdrill config` shows it.

### 5.3 `sources.resolve_input` / the doc-folder placement
When a download/resolve produces `X.pdf`, place it at
`<library_root>/<X>/<X>.pdf` (create the folder). Existing arXiv canonical
naming stays (`<id>.pdf`), now inside `<id>/`. A local file passed by path is
NOT moved (respect the user's location) — only downloads land in the library.
The download registry keys stay URL→file (path updated to the new location).

### 5.4 `pdfdrill relocate <dir>… [--dry-run|--apply] [--into <library>]`
(`src/pdfdrill/relocate.py`, new) — the migration. For each `X.pdf` found
(recursively) under a scanned dir that is NOT already self-contained:
1. target `<library>/<X>/` (default library = `config.library_root()`).
2. plan the moves: `X.pdf`, every loose `X.*` sibling (`X.lines.json`,
   `X.tex.zip`, `X.tgz`, `X.pdf.drill.json`, …), and the CONTENTS of
   `X.pdf.drill/` (flattened into `<library>/X/`).
3. `--dry-run` (default) prints the plan; `--apply` executes with
   `shutil.move`, creating `<library>/X/` first. Collision-safe (never
   overwrite; report). Idempotent (a doc already at `<library>/X/X.pdf` is
   skipped). Renames the sidecar state `X.pdf.drill.json` → `X.drill.json`.
Pure planning (`plan_relocation(pdf, library) -> list[(src,dst)]`) is unit-
tested; the apply is a thin `shutil.move` loop.

## 6. Artifact/URL resolution (drillui, static server)
The bridge's `ART_ROOTS` already include the config download dir and the doc's
own dir; with the library layout the doc folder is under `library_root`, so
adding `library_root` to the roots covers every doc. `registerDocDir` already
pushes an added doc's dir. Doc-relative artifact paths (`<stem>.tiddlers.json`)
resolve under `<library>/<stem>/` unchanged.

## 7. Non-goals
- No change to the on-disk *format* of any artifact (only their location).
- No change to the `pdfdrill repo`/`publish` (github TiddlyWiki) layout — that's
  a separate publishing target; this is the working library.
- Ad-hoc one-off drills on a PDF in place keep the sibling `.drill` (D3).

## 8. Testing
- `Sidecar` blob_dir: self-contained (`<stem>/<stem>.pdf` → blob = `<stem>/`),
  legacy (`X.pdf.drill/` sibling → blob = it), ad-hoc (`/tmp/x.pdf` → `x.pdf.drill`).
- `relocate.plan_relocation`: a legacy doc (PDF + siblings + `.drill/`) → the
  correct (src,dst) list into `<library>/X/`; already-migrated → empty; collision
  reported.
- End-to-end on a copied fixture dir: relocate `--apply` then a command (`status`/
  `md`) works on `<library>/X/X.pdf`.
- Back-compat: an un-migrated legacy doc still drills/reads.

## 9. Migration UX (the user's hundreds of docs)
```
pdfdrill config --library-root ~/pdfdrill          # (or accept the default)
pdfdrill relocate ~/Downloads ~/pdfdrill --dry-run  # review the plan
pdfdrill relocate ~/Downloads ~/pdfdrill --apply    # move them in
git -C ~/pdfdrill init && git -C ~/pdfdrill add -A && git -C ~/pdfdrill commit -m "library"
```
