# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What SCANDRILL is

Image/scan **ingestion → optimal PDF** front-end for the `pdfdrill` pipeline
(`~/MX/PDFDRILL`). Four ingestion producers — CLI `find`, drillui drag/drop,
camera, ADF scanner — converge on ONE canonical artifact: a job dir of ordered
page images plus an `ingest.json` sidecar. Processing stages are pure transforms
of that manifest; the PDF is a **lossless** projection of it. SCANDRILL then hands
the PDF to pdfdrill.

**Design rule:** pdfdrill's OCR/analysis and the parallel-dev image tools
(`~/pylepto`, `~/BlobTracker`) are used **only to prepare a better PDF** — never
as the deliverable. They are reached through `scandrill/tools.py` adapters, never
shelled out ad hoc. See `PROPOSAL.md` for the full grounded design and build order.

## Commands

- Run tests: `python3 -m pytest tests/ -q` (needs `PYTHONPATH=$PWD` or `pip install -e .`).
- One-shot build: `PYTHONPATH=$PWD python3 -m scandrill.cli build <img_dir> -o out.pdf --job NAME --lang de-DE`
- Two-step: `... ingest <dir> --job NAME` → `... assemble NAME.ingest.json -o out.pdf`
- Full ADF pipeline: `... adf --job N` (scan+deskew) → `... assemble N.ingest.json -o N.pdf`
  → `... handoff N.ingest.json --pdf N.pdf`
- Check external-tool wiring: `... scandrill.cli tools`; scanners: `... devices`
- pdfdrill preflight: the token is the LAST line of `src/pdfdrill/skill/SKILL.md`.
  **Never hardcode it** — it is a checksum that changes with the file (it moved
  from `DRILL-ba78c697` to `DRILL-665bb1d6` overnight in commit `cad59c5`), and
  quoting a stale one attests to a file you didn't read.
  Read-only commands are ungated; `tools.run_pdfdrill` sets `PDFDRILL_NO_PREFLIGHT=1`
  for automation. Build/extract commands (`model`/`mathpix`/`tiddlers`) are
  pdfdrill's job downstream — SCANDRILL does not call them.

## Architecture

- `scandrill/manifest.py` — `ingest.json` schema (`Manifest`/`Page` dataclasses).
  **Not** named `manifest.json` (pdfdrill's pyramid viewer owns that name).
  Removed pages keep a `removed_*` status (never deleted) so pdfdrill can account
  for them. `merge_into_sidecar()` writes provenance under a single `scandrill`
  key — additive, never clobbers pdfdrill's `.drill.json` keys.
- `scandrill/ingest.py` — shared producer machinery: hash/stat/dimensions, blank
  detection (`blank_mean`, mirrors `scanp.sh`'s shave+grayscale-mean, threshold
  0.999), version-aware ordering (`name`/`mtime`).
- `scandrill/assemble.py` — the genuinely new core, three separable stages, only
  the first touching pixels (and it doesn't re-encode them): `img2pdf`
  (JPEG→DCTDecode verbatim, PNG→FlateDecode identical pixels) → `meta.stamp` →
  optional `ocr.graft_text_layer`. pdfdrill has no image→PDF step.
- `scandrill/meta.py` — `DocMeta` + `stamp()`. A PDF stores metadata **twice**
  (legacy DocInfo *and* XMP) and they must agree or readers disagree; `stamp()`
  writes both, plus catalog `/Lang` and `/PageLabels`. `dc:creator` is a *list*.
- `scandrill/ocr.py` — searchable text layer **without touching the image**:
  `tesseract -c textonly_pdf=1` emits invisible text only (no image), and
  `pikepdf Page.add_overlay` grafts it on. Verified: image streams stay
  byte-identical. See `docs/PROPOSAL-ASSEMBLY.md`.

## Why not Ghostscript pdfocr8/24/32 (asked before; answered)

Measured: this gs (10.07.1) **does not ship them** — `Unknown device: pdfocr8`;
they need gs compiled with Tesseract. Moot anyway: the pdfocr devices **rasterize
the page** through the gs renderer (a decode→re-encode round trip on an image
that is already the scanner's exact output), `pdfocr8` is *grayscale* so it would
silently destroy a Color scan, and the device writes the PDF so we'd lose
metadata control. **Never route page images through Ghostscript.** (gs remains
correct for the 600 dpi *renders* pylepto consumes — different job.)
`tests/test_meta_ocr.py::test_ghostscript_pdfocr_is_absent_here` fails loudly if
a future gs gains the devices, so the decision is revisited on purpose.
fitz/PyMuPDF: use for **reading/verification**; pikepdf for **mutation**.
- `scandrill/tools.py` — integration seams. Env-var discovery (`PDFDRILL_HOME`,
  `PYLEPTO_HOME`, `BLOBTRACKER_HOME`). `analyze_side()` and
  `fuse_sheet()` wire BlobTracker's real `blobcc` + `deskew` (imported via
  sys.path — it's a flat script collection, not a package; cached per process).
  **`fuse_sheet()` delegates to the real `deskew.fuse_duplex`** — do not
  reimplement it: it confidence-weights two agreeing sides, derives a sparse side
  from the strong one, and flags contradictions. Also `rotate_image()` (applies
  the fused angle), `run_pdfdrill()` (read-only; sets `PDFDRILL_NO_PREFLIGHT=1`),
  `pdfdrill_sidecar()`.
  **pylepto is NOT wired into any pipeline path** — skew is BlobTracker-only
  (blobcc fast path → Hough fallback → fuse_duplex). The pylepto-arbiter seam was
  proposed, never used, and has been removed rather than left as dead code; see
  `docs/TOPOLOGY-VS-RASTER.md` for where it would plug in. The `deskew` **binary**
  is likewise unused: it re-detects the angle itself, which would discard the
  fused duplex angle and re-measure the sparse back we refused to measure.
- `scandrill/config.py` + `scandrill.toml` — **the fixed rig**: ADF Duplex @ 300
  dpi, deskew always. Scanner options are never probed/negotiated; only the device
  is resolved. Every tuning constant scattered across scanp.sh/scand.py has exactly
  one home here, each carrying its provenance. **The toml overrides the dataclass**,
  so a stale value there disables a feature with no error — `tests/test_config.py`
  asserts the two agree.
- `scandrill/producers/adf.py` — I-D) ADF producer. Reuses `scanp.sh`'s *recipe*
  (flags, A4 crop, thresholds, duplex pairing) but **not** its file management:
  raw never deleted, blanks recorded as `removed_blank` (never `rm`'d), skew
  measured/recorded rather than silently baked in. `--from-dir` replays an
  existing `raw_%d.png` batch so everything is testable without paper.
  `measure_skew()` runs ONE blobcc pass per side (blank ink-area check + skew
  fast path share it, as in `scand.py:analyze_side`), then fuses per sheet.
  `apply_deskew()` rotates into `proc/`, repoints `Page.src`, keeps `raw_src`.

## Skew policy (ADF assumed — do not revisit without asking)

- **Deskew always.** ADF scans are always skewed; it is not opt-in.
- **Measure FRONT pages only; the back takes `−front`.** pylepto records this
  under "Project Decisions (user-set, do not revisit)" — backs are too sparsely
  filled to measure reliably. `Config.measure_backs = False`. The back is measured
  *only* as a fallback when the front yielded no usable angle (blank/sparse front,
  printed back) — otherwise that sheet could never be corrected.
- **Never calculate skew on a half-empty page.** Ink below `skew_min_ink_area`
  (but above `empty_min_ink_area`) ⇒ `method="sparse"`, angle `None`, estimate
  skipped entirely. A sparse page yields a confident-looking but wrong angle.
- Rotate with `tools.rotate_image()` (PIL), **not** the `deskew` binary: that
  tool re-detects the angle itself, which would discard the fused duplex angle
  and re-measure the sparse back we deliberately refused to measure.
- `scandrill/producers/upload.py` + `scandrill/server.py` — **I-B) drag & drop**,
  stdlib-only. Two modes, because a browser drop gives you one of two things:
  *upload* (bytes → `<job>/raw/`) or *reference* (`text/uri-list` of `file://`
  paths → manifest entries pointing at the originals, **no copy**). Reference
  mode is allowlisted (`--allow-root`), mirroring the bridge's `safeResolve`.
  Both take attacker-influenced names — a multipart `filename` can be
  `../../etc/passwd`, a dropped URI can name any path — so `safe_filename()` and
  `under_root()` (which resolves *both* sides, defeating symlink escapes) are the
  point of that module. Server binds **loopback by default**.
- `scandrill/handoff.py` — **stage III**. Merges provenance into pdfdrill's own
  sidecar under one `scandrill` key and runs read-only analysis. Two hard-won
  rules live here: go through **pdfdrill's own `Sidecar` class** (it only seeds
  its default skeleton when the file is absent, so a sidecar we author first
  leaves it with no `pdf`/`facts`/`evidence` keys), and get the path from its own
  `blob_dir_for` (**not** always `<pdf>.drill.json` — the library layout uses
  `<stem>/<stem>.drill.json`).
- `scandrill/cli.py` — `ingest` / `assemble` / `build` / `devices` / `adf` /
  `serve` / `handoff` / `tools`.

## Why the drop zone is not in drillui_bridge.ts (yet)

`tools/DRILLUI.md` states there is exactly ONE canonical copy of
`drillui_bridge.ts`, and pdfdrill integration is explicitly a *later* step — so
editing another repo's canonical file is not this project's call yet. The route
shape (`POST /job/<job>/pages`, `POST /job/<job>/paths`, `GET
/job/<job>/manifest`) deliberately matches what a Bun handler would expose, and
all the logic lives in `producers/upload.py`, so mounting it into the bridge
later means calling the same entry points (the bridge already spawns Python for
`drillui_chat.py`). The bridge already has POST routes (`/open`, `/edit`) and
`safeResolve`, so it is a small addition when the time comes.
Unverified: whether the target desktop actually emits `text/uri-list` on drag —
varies by DE, needs a 2-minute check on Solus. Upload mode works regardless.

## ⚠ The OCR/route interaction (measured, not theorised)

Same real scan, same pages, only `--ocr` differing:

| PDF | `pdfdrill route` says |
|---|---|
| without `--ocr` | `scanned → Gemma 4 [keyed]` ✅ |
| with `--ocr` | `born-digital → pdfminer/text-layer` ❌ |

`route` infers born-digital from *the presence of a text layer*, so **our own OCR
graft makes a scan look born-digital** and sends pdfdrill to pdfminer — which
merely re-reads our plain tesseract text instead of running the vision lane that
reads equations (SKILL rule 4: never accept a 0-equation model of a math paper).

So: **hand pdfdrill the PDF built WITHOUT `--ocr`.** `--ocr` is for a
human-searchable deliverable. `Manifest.ocr` records the graft, it travels into
the sidecar, and `handoff.route_warnings()` shouts when the misroute happens.
This is the sharpest example of the project rule cutting both ways: OCR must only
ever *prepare a better PDF*, and here it made a worse one for the consumer.

## Image-tool boundary (see docs/TOPOLOGY-VS-RASTER.md)

pylepto and BlobTracker are **not** redundant — they are sequential layers, and
Leptonica cannot absorb BlobTracker. Rule: *if the question needs pixels again
it's Leptonica's; if it can be answered from run-length coordinate sets it's
BlobTracker's.* After the one CC pass, topology is O(runs) with no image resident
— which is why `blobtopo.holes()` (counting holes), `glyph_map`/`glyph_runs`
(single-glyph coordinate sets), `near_groups` (diacritics: i-dots, ä/ö/ü) and
`rows`/`columns` belong there. Status: BlobTracker is **staged, not yet migrated**
— no `src/pdfdrill/blobtrack.py` exists, but `blobtrack.py:15` names it as its
destination. pylepto is likewise a pdfdrill incubator.

## Key external references

- `~/WKprivate/Scanned/scanp.sh` — tested ADF-duplex producer (scan + blank +
  deskew + naming). Reuse as the D) producer, don't re-implement.
- `~/MX/PDFDRILL` — target pipeline. Relevant subcommands: `route --run`, `ocr`,
  `autosegment`/`segment`/`ordered`, `continuity`, `pageside`, `folder`. Read
  `src/pdfdrill/skill/SKILL.md` before writing integration code; `pdfdrill
  preflight --ack` gates build/extract commands.
- `~/pylepto` (Leptonica bindings) and `~/BlobTracker` (`blobcc`, `cropmark`,
  `qrscan`, `deskew`) — parallel-dev image tools moving into pdfdrill.

## Gotchas

- Lossless test asserts JPEG streams embed **verbatim** (byte-identical) and PNG
  pages round-trip **pixel-identical** — don't "optimize" the assembly path in a
  way that re-encodes. This holds through deskew AND the OCR graft; both are
  covered by tests that compare raw stream bytes before/after.
- pikepdf metadata kwarg is `set_pikepdf_as_editor` (not `_as_xmp`); pass `False`
  or pikepdf stamps *itself* as the producer, clobbering ours.
- Test fixtures: PIL's default font is ~10 px and tesseract genuinely misreads
  digits at that size (8→6) — that's the fixture being unrealistic, not a bug.
  Render with a scalable face (`DejaVuSans.ttf` @ 64 px) for OCR tests.
- Supported input resolutions (pylepto convention): 300 dpi scanner output, 600
  dpi Ghostscript renders. Skew confidence < 3.0 is untrustworthy.
- **Never hardcode the scanner device.** In `airscan:eN:` the `eN` is a
  discovery-order index that drifts: `scanp.sh` says `e1`, `scand.py` says `e0`,
  and `e0` is what enumerates today. Use `resolve_device()`; record the resolved
  string in `origin`. Backend preference `airscan: > escl: > hpaio:` (escl is
  IP-pinned and breaks on DHCP change). `scanimage -L` needs ~45 s — a short
  timeout silently returns only the first device.
- Sign conventions: BlobTracker **and** Leptonica use positive = counter-clockwise
  and agree; ImageMagick `-rotate` is positive-**clockwise** (pass as-is to IM,
  negate for PIL/cv2). Duplex rule, agreed by all three tools:
  `angle(back) == −angle(front)`; a weak side is derived from the strong one.
- Rotation resamples every pixel — **not** lossless. So `raw/` is always retained
  untouched and the angle recorded: the correction stays auditable and
  re-derivable. Skipped below `min_skew_deg` (a no-op beats a needless resample)
  and refused above `max_skew_deg` (scand.py won't trust corrections that large).
- **Sign is the easiest thing to get wrong** and a reversed sign *doubles* the
  skew while still looking like it worked. IM/`rotate_image` correction is
  positive-**clockwise**; PIL's positive is counter-clockwise, so `rotate_image`
  negates on the way in. `test_deskew_sign_is_correct_end_to_end` re-measures the
  output and asserts the residual is ~0 — verified on a real scan: +0.460° → +0.020°.
- blobcc's core is pure Python: a 300 dpi A4 side is ~8.5 MPx. The skew pass runs
  on a downscaled copy (`Config.skew_max_px`) — the **angle is scale-invariant**,
  but px-denominated thresholds (`min_rule_px`, `min_area`, `empty_min_ink_area`,
  `empty_border_px`) must be scaled with it. Measured: 8.5 MPx side → ~0.5 s.
- Mask the scan borders before measuring (`empty_border_px`): the ADF edge shadow
  is ink-dark and would otherwise dominate both ink area and rule blobs.
- Security: `~/WKprivate/Scanned/ocr.sh` has hardcoded MathPix keys — move to
  `.env` and rotate before sharing.

## CodeGraph

A CodeGraph MCP server (`codegraph_*`) indexes this repo. Prefer it for
structural questions once code grows; use grep/Read for literal text.
