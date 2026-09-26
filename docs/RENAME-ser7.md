# Host-prefix rename on ser7

`pdfdrill relocate` does this — there is no separate script, and there should not
be one: a migration that is not a command is invisible to `steps`, `--ensure`
and the planner (audit A4).

## Run it

The paths on ser7 are not the paths here, so let the script find them:

```bash
cd <wherever the checkout lives on ser7>
git pull
./tools/rename-library-hosts.sh                 # dry run — prints the plan, moves nothing
./tools/rename-library-hosts.sh --apply         # asks before it moves anything
```

It resolves the checkout from its own location and the library from
`$PDFDRILL_LIBRARY`, then `pdfdrill config`, then the usual places — and prints
both before doing anything, so you can see what it picked. Name it explicitly
when you have several:

```bash
./tools/rename-library-hosts.sh ~/workspace/pdfdrill-library --apply
```

**A named path never falls back.** If you name a library that does not exist —
a typo, or a stale `$PDFDRILL_LIBRARY` — the script stops. It does not search
on, because searching on is how a rename lands on a *different* library,
hundreds of folders deep, with no error.

The script also refuses to `--apply` while something is listening on `:8787`
(pass `--yes` to override): a rename pulls a folder out from under the drillui
bridge, which then 404s on a path that was valid a second ago.

The capability itself is `pdfdrill relocate` — the script only locates paths.
Straight to the command, if you prefer:

```bash
PDFDRILL_NO_PREFLIGHT=1 ./pdfdrill relocate --library <path>            # dry run
PDFDRILL_NO_PREFLIGHT=1 ./pdfdrill relocate --library <path> --apply
```

## What it changes

- `<library>/1702.0234/` → `<library>/vixra.1702.0234/`, and every file inside
  that carries the old stem (`…drill.json`, `…inspect.html`, `latex/….tex`,
  at any depth). `model.docmodel.json` and the other fixed names are untouched.
- The sidecar's **path** fields only — `pdf`, `evidence.inspect_path`,
  `evidence.bibkey`. `evidence.source_arxiv_id` and every `bibtex.*` field hold
  the **id**, which does not change; rewriting the stem blindly through the JSON
  would turn the arXiv id into `arxiv.1107.2723` and take the document off every
  free e-print route.
- `pdfdrill-downloads.json` filenames, so `add <url>` still finds the local copy
  instead of downloading the paper again.

A bare id still resolves afterwards: `library_pdf_for("1107.2723")` finds
`arxiv.1107.2723/`.

## What it refuses

- **Ambiguous ids.** A four-digit id from before 1501 is an equally good arXiv
  and viXra id. Those are skipped and named, never guessed.
- **Collisions.** If the prefixed name is taken, that folder moves nothing at
  all — a half-renamed doc is worse than an unrenamed one.

## Which archive — and why the sidecar is read last

1. **Shape**, first: arXiv went to five digits in 1501 and viXra never issued a
   five-digit or old-style id. Arithmetic about the id space; cannot be wrong.
2. **The download registry URL** — the URL the user actually supplied.
3. **The sidecar** (`bibtex.url`, `evidence.source_arxiv_id`) — LAST, because it
   is derived, and derived by the code 806 fixed. Measured here: **nine viXra
   folders carry a sidecar bibtex saying `https://arxiv.org/abs/…`**. Believing
   the sidecar over the shape would have renamed all nine `arxiv.*` and written
   the 806 defect into the filesystem, where a folder name is never questioned
   again. The run reports them, with `pdfdrill bibtex <doc> --force` as the fix.

## Measured on the local library (2026-09-26)

```
519 to rename   arxiv: 505, vixra: 14
  9 flagged     sidecar bibtex names the other archive
  3 skipped     1101.4542, 1107.2723v1, 1412.8390 — no evidence
  1 refused     2510.04618 → arxiv.2510.04618 already exists
```

## A hazard removed in the same change

`relocate` with no path used to default to scanning the library root. A
recursive scan of an already-migrated library offers up **8,460 PDFs that are
not documents**:

- **7,353** are artifacts inside some other document's folder — that folder's
  own `report.pdf`, `evidence-*.pdf`, `residuals.pdf`. Every one of them is a
  "legacy scattered drill" by the old test, and they all relocate into a single
  `<library>/report/`, each overwriting the last.
- Of the 1,107 left, **598 are in `lstgold/`** — provenance-recorded, not to be
  redistributed, let alone moved — plus the datikz fixtures and `out/`.

Running `relocate --apply` with no arguments would have done that today. There
is now no default path: migration 1 runs where you point it, and `find_docs`
treats a folder holding `<its own name>.pdf` as a document whose contents are
its own property.
