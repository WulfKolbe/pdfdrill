# SCANDRILL — the absorbed acquisition project

The SCANDRILL project was **absorbed into pdfdrill** on 2026-07-16: its code is
vendored at `src/pdfdrill/scandrill/`, its 122 tests at `tests/scandrill/`, and
the driver is `src/pdfdrill/scan.py` (`pdfdrill scan`). The original `~/SCANDRILL`
checkout — which was never a git repo — is gone.

These documents are preserved because they are the *why* behind that code, and
the code alone doesn't carry it:

| file | what it is |
|---|---|
| `PROPOSAL.md` | the original design: scan → lossless PDF, nothing destroyed |
| `PROPOSAL-ADF.md` | the ADF producer (the fixed rig, duplex, blank handling) |
| `PROPOSAL-ASSEMBLY.md` | assembly: the PDF as a *projection* of `ingest.json` |
| `TOPOLOGY-VS-RASTER.md` | why topology (BlobTracker) beats raster for skew |
| `PROMPT-FOR-PDFDRILL.md` | the integration brief; its OPEN items are listed below |
| `SCANDRILL-CLAUDE.md` | SCANDRILL's own operating instructions |

**Read these as history, not as instructions.** They describe SCANDRILL as a
separate project invoked over a CLI (`python -m scandrill.cli …`, `handoff`,
`$SCANDRILL_HOME`). None of that is true any more — pdfdrill imports the code
directly. Where a document and the code disagree, the code wins.

## What survived, and where the rules now live

The invariants these documents argue for are enforced in code and locked by
tests; see the "Scan acquisition" section of the top-level `CLAUDE.md`:

- nothing is destroyed (`raw/` retained; blank sides recorded, never deleted);
- rotation is the only pixel-touching step, and it is recorded;
- assembly never resamples — the PDF is a projection of the manifest;
- no OCR text layer on the path feeding pdfdrill (it would make `route` read the
  scan as born-digital). The underlay is a human deliverable, produced separately.

## Still open (from the brief)

- **BlobTracker** (`~/BlobTracker`) — glyph coordinates, incl. for glyphs OCR
  could not decode; also the skew signal `TOPOLOGY-VS-RASTER.md` argues for.
- **The `route` born-digital misread** — `route` infers born-digital from the mere
  *presence* of a text layer, so a scan OCR'd by anyone (ocrmypdf, Acrobat, or our
  own future underlay) misroutes to pdfminer. The brief's fix (consult the
  scandrill sidecar) covers only our own PDFs; an invisible-text (`Tr 3`) probe is
  the source-independent one.
- **The drillui drop zone** — `POST /job/<job>/pages`, `/paths`, `/manifest`,
  thumbnails, re-order (`server.py` + `producers/upload.py` are vendored already).
- **sender-date-type prefix promotion** — derive the per-document bibkey after
  segmentation and freeze it (`scan` only names the acquisition event).
