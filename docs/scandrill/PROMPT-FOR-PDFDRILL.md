# Integration brief — hand this to a Claude Code session in `~/MX/PDFDRILL`

Copy everything below the line into a fresh Claude Code session started in
`~/MX/PDFDRILL`. It is written for that session, not for a human.

---

## Task: integrate SCANDRILL (`~/SCANDRILL`) into pdfdrill

You are working in `~/MX/PDFDRILL`. A sibling project, **SCANDRILL**
(`~/SCANDRILL`), is the image/scan **ingestion → optimal PDF** front-end for this
pipeline. It is finished and tested (121 tests, green). Your job is to integrate
it — not to rewrite it.

**Before writing any integration code:** read `src/pdfdrill/skill/SKILL.md` to its
last line (per this repo's own rule), then run
`pdfdrill preflight --ack <TOKEN>` with the token printed on that last line to
unlock build/extract commands.

> The token is **deliberately not reproduced here.** It is a checksum of SKILL.md
> and changes whenever the file does — it was `DRILL-ba78c697` on 2026-07-15 and
> `DRILL-665bb1d6` by the next morning (commit `cad59c5`). Copying a token from a
> second-hand document would attest to a file you never read, which is exactly what
> the gate exists to prevent. Read the file; take the token from it.

Also read `~/SCANDRILL/CLAUDE.md` and `~/SCANDRILL/docs/`.

### What SCANDRILL is

Four ingestion producers — CLI `find`, drillui drag/drop, camera (not built yet),
ADF scanner — converge on ONE canonical artifact: a job dir of ordered page images
plus an **`ingest.json`** sidecar. Processing stages are pure transforms of that
manifest; the PDF is a **lossless** projection of it. Then it hands off to pdfdrill.

```
scandrill/manifest.py    ingest.json schema (Manifest/Page). NOT "manifest.json" —
                         that name is taken by pdfdrill's pyramid viewer.
scandrill/ingest.py      shared producer machinery (hash/stat/dims/blank/order)
scandrill/producers/adf.py     I-D) ADF via scanimage; reuses scanp.sh's recipe
scandrill/producers/upload.py  I-B) drag&drop: upload + path-reference modes
scandrill/server.py      the drop-zone HTTP server (stdlib)
scandrill/assemble.py    img2pdf (lossless) → meta.stamp → optional ocr graft
scandrill/meta.py        DocMeta: /Lang, XMP + DocInfo, page labels
scandrill/ocr.py         invisible text layer, image untouched
scandrill/handoff.py     III) merge provenance into pdfdrill's sidecar
scandrill/tools.py       every external-tool call contract
scandrill/config.py      the fixed rig: ADF Duplex @ 300 dpi, deskew always
```

Run it: `PYTHONPATH=~/SCANDRILL python3 -m scandrill.cli --help`
(`ingest|assemble|build|devices|adf|serve|handoff|tools`).

### The gap SCANDRILL fills

**pdfdrill has no image→PDF step.** It is PDF-*in*. Its deps carry `pypdf` but not
`img2pdf`. SCANDRILL's `assemble.py` is the genuinely new code; everything else it
does is orchestration of things that already existed (scanp.sh, blobcc, tesseract).

---

## The integration work, in priority order

### 1. Land BlobTracker (it already names its destination)

`~/BlobTracker/blobtrack.py:15` says: *"Destination:
`~/MX/PDFDRILL/src/pdfdrill/blobtrack.py`"*. It is **not yet here** — verified: no
`src/pdfdrill/blobtrack.py`, no `blob*`/`topo*`/`lepto*` module anywhere in `src/`.

Move `blobtrack.py` + `blobtopo.py` in. They are stdlib-only (numpy/Pillow are
optional accelerators). Keep that property.

**Do not treat BlobTracker as redundant with pylepto/Leptonica.** They are
sequential layers, not competitors — see `~/SCANDRILL/docs/TOPOLOGY-VS-RASTER.md`:

> If answering the question requires looking at pixels again, it's Leptonica's.
> If it can be answered from run-length coordinate sets, it's BlobTracker's.

Leptonica costs `O(pixels)` *per question* with the image resident. BlobTracker
does ONE pass, then every question is `O(runs)` with no image at all — which is why
`blobtopo.holes()` (counting holes = `len(holes(b))`), `glyph_map`/`glyph_runs`
(single-glyph coordinate sets), `near_groups` (diacritics: i-dots, ä/ö/ü) and
`rows`/`columns` belong there and cannot be absorbed by Leptonica.

Once landed, SCANDRILL's `tools.py` seam should collapse to importing pdfdrill
instead of `sys.path`-inserting `~/BlobTracker`.

### 2. Add the image→PDF command (or depend on SCANDRILL)

Either vendor `assemble.py`+`meta.py` as `pdfdrill build-pdf <img_dir>`, or make
SCANDRILL a dependency. Non-negotiable properties, each covered by a test in
`~/SCANDRILL/tests/`:

- **JPEG embeds byte-identical** (`/DCTDecode` verbatim), **PNG pixel-identical**
  (`/FlateDecode`). `img2pdf` never re-encodes. Do not "optimise" this path.
- Metadata goes in **both** DocInfo *and* XMP or readers disagree; `dc:creator`
  is a list; pass `set_pikepdf_as_editor=False` or pikepdf stamps itself as
  Producer.
- Catalog `/Lang` + `/PageLabels`.

### 3. Fix the OCR/route interaction (a real bug — still present as of 2026-07-16)

Same real scan, same pages, only `--ocr` differing. **Re-verified against current
`HEAD` after `cad59c5`, with the `scandrill` sidecar block present — still wrong:**

| PDF | `pdfdrill route` says |
|---|---|
| without OCR | `scanned → Gemma 4 [keyed]` ✅ |
| with OCR | `born-digital → pdfminer/text-layer` ❌ |

`route` infers born-digital from *the presence of a text layer*, so **any OCR text
layer makes a scan look born-digital** and sends pdfdrill to pdfminer — which
re-reads a plain tesseract text layer instead of running a keyed/vision lane.

Note this is precisely the trap the **rewritten SKILL rule 4** warns about
(`cad59c5`): a keyless text source *"cannot produce LaTeX by construction"*, and
the presence of text — like a non-zero equation count — *"is not evidence of
captured math."* `route` currently draws exactly that false inference from a text
layer's mere existence. Fixing `route` closes the loop the SKILL rewrite opened.

SCANDRILL already records the provenance in the sidecar so you can fix this here:

```json
{ "scandrill": { "ocr": {"applied": true, "engine": "tesseract",
                         "lang": "deu", "pages": 1},
                 "pages": [ {"origin": {"kind": "adf", ...}, ...} ] } }
```

**Suggested fix:** have `route` consult `scandrill.ocr.applied` and
`scandrill.pages[].origin.kind ∈ {adf, camera}` before concluding born-digital. A
text layer + a scanner origin = an OCR'd scan, not a born-digital document.

**Related — decide who owns OCR for scans.** `cad59c5` re-scoped `pdfdrill ocr` as
*"MathPix-free OCR aimed at **COMMERCIAL documents** (scans, letters, tables, form
fields)"* with typed lines, per-line `conf`, `pt` regions, OSD auto-upright and
barcodes. That is **exactly SCANDRILL's use case**, and it is strictly richer than
SCANDRILL's `--ocr`, which grafts a plain invisible tesseract text layer for
*human* searchability and produces no typed lines at all. So they are not
competitors and should not be merged:

- `pdfdrill ocr` → produces `lines.json` **for the model**. Owns OCR-for-analysis.
- SCANDRILL `--ocr` → produces a **searchable deliverable** for a person. Opt-in,
  and (per §3) **must not** be used on a PDF you are about to hand to pdfdrill.

If `route` learns to read `scandrill.ocr`, a third option opens: let SCANDRILL's
graft be recognised and *superseded* by `pdfdrill ocr` rather than mistaken for
born-digital text.

### 4. The sidecar merge contract (verified, both directions)

`Sidecar._load()` reads the whole dict and `save()` writes it back, so unknown
top-level keys round-trip. That is what makes the namespaced `scandrill` key safe.
**Two traps found the hard way — preserve both behaviours:**

- **`_load()` only seeds the default skeleton when the file is ABSENT.** A sidecar
  authored by another tool first leaves pdfdrill with no `pdf`/`facts`/`evidence`
  keys at all. SCANDRILL therefore writes through *pdfdrill's own `Sidecar` class*.
  If you refactor, keep `_load()` tolerant of a pre-existing foreign file.
- **The sidecar is not always `<pdf>.drill.json`.** `blob_dir_for()` resolves the
  self-contained layout (`<stem>/<stem>.drill.json`). SCANDRILL calls that function
  rather than replicating the rule. Don't break its signature.

### 5. drillui: host the drop zone

`~/SCANDRILL/scandrill/server.py` implements I-B standalone *because*
`tools/DRILLUI.md` says there is exactly ONE canonical copy of
`drillui_bridge.ts` — editing it was not SCANDRILL's call. It is now yours.

Route shape already matches what a Bun handler would expose:

```
GET  /job/<job>/manifest    the live ingest.json
POST /job/<job>/pages       multipart → <job>/raw/ + manifest entries
POST /job/<job>/paths       text/uri-list → reference entries (allowlisted)
GET  /job/<job>/thumb/<seq> page preview
```

The bridge already has POST routes (`/open`, `/edit`), `safeResolve`, static
serving, a WS, and spawns Python (`drillui_chat.py`) — so mounting this is small:
add the routes, call SCANDRILL's `producers/upload.py` entry points, push manifest
updates over the existing socket so the page list is a render of `ingest.json`.

**Security — do not reimplement casually.** A multipart `filename` is arbitrary
client input (`../../.ssh/authorized_keys`) and a dropped URI can name any path.
`upload.safe_filename()` and `upload.under_root()` (which resolves *both* sides,
defeating symlink escape) exist for that; there are ~15 tests. Reference mode must
stay allowlist-gated and the server loopback-bound by default.

**Unverified:** whether the target desktop actually emits `text/uri-list` on drag
(varies by DE — needs a 2-minute check on Solus). Upload mode works regardless.

---

## Facts established by measurement (don't re-derive; don't contradict)

- **Ghostscript `pdfocr8/24/32` are NOT in this build** (`Unknown device: pdfocr8`;
  gs 10.07.1 ships only `pdfimage8/24/32`, `pdfwrite`). They need gs compiled with
  Tesseract. Moot anyway: they **rasterize** the page (a decode→re-encode round
  trip on an image that is already the scanner's exact output), `pdfocr8` is
  *grayscale* and would destroy a Color scan, and the device writes the PDF so
  metadata control is lost. **Never route page images through Ghostscript.** (gs
  stays correct for the 600 dpi *renders* pylepto consumes — different job.)
- **Tesseract's own PDF writer is lossless** (JPEG passes through verbatim,
  measured) but writes the whole PDF, so it costs metadata control. SCANDRILL uses
  `tesseract -c textonly_pdf=1` (invisible text, **no image**) + `pikepdf
  Page.add_overlay` — image streams stay byte-identical.
- **Scanner device IDs drift.** In `airscan:eN:` the `eN` is a discovery-order
  index: `scanp.sh` hardcodes `e1`, `scand.py` hardcodes `e0`, and `e0` is what
  enumerates today. This printer exposes 4 backends at once (`hpaio:` ×2, `escl:`,
  `airscan:`). Resolve at runtime; prefer `airscan: > escl: > hpaio:` (escl is
  IP-pinned and breaks on DHCP change). `scanimage -L` needs **~45 s** — a short
  timeout silently returns only the first device.
- **Skew, per the user's standing decision** (recorded in `~/pylepto/CLAUDE.md`
  under "Project Decisions — do not revisit"): measure **front pages only**; the
  back takes the **negated front angle**. Never compute skew on a half-empty page.
  All three tools agree `angle(back) == −angle(front)`.
- **Sign convention:** BlobTracker and Leptonica both use positive =
  counter-clockwise. ImageMagick `-rotate` is positive-**clockwise**. A reversed
  sign *doubles* the skew while still looking like it worked — SCANDRILL's test
  re-measures the output and asserts residual ≈ 0 (verified real scan: +0.460° →
  +0.020°).
- **`deskew.fuse_duplex` is better than any reimplementation** — it
  confidence-weights two agreeing sides, derives a sparse side from the strong one,
  and flags contradictions. Delegate to it.
- **Don't use the `deskew` binary to apply a known angle**: it re-detects the angle
  itself, discarding the fused duplex value.
- **pylepto is NOT currently wired** into any SCANDRILL pipeline path. Skew is
  BlobTracker-only. Its validated detectors (skew sweep, halftone/figure regions,
  table rules, segmentation) remain integration targets; `pylepto/CLAUDE.md` says
  it is explicitly an incubator for this repo. Note pylepto's conventions: 300 dpi
  scanner / 600 dpi Ghostscript only; skew confidence < 3.0 is untrustworthy.

## Rules SCANDRILL follows that you should preserve

1. **pdfdrill's OCR/analysis exists only to prepare a better PDF** — never as the
   deliverable. SCANDRILL calls only read-only commands and hard-blocks
   build/extract ones (`handoff.BUILD_COMMANDS`), because `run_pdfdrill` sets
   `PDFDRILL_NO_PREFLIGHT=1` and would otherwise walk through the preflight gate.
2. **Nothing is destroyed.** `scanp.sh` `rm`s raw scans and blank pages; SCANDRILL
   keeps raw, records blanks as `removed_*` (never deletes), and records skew
   rather than baking it in — because pdfdrill must be able to account for removed
   pages.
3. **Rotation is the only pixel-touching step**, it is recorded, and `raw/` is
   retained. Assembly never resamples.
4. **The PDF is a projection of `ingest.json`.** Anything not re-derivable from the
   manifest doesn't belong in assembly.

## Known-good verification

```bash
cd ~/SCANDRILL && PYTHONPATH=$PWD python3 -m pytest tests/ -q     # 121 passed
PYTHONPATH=$PWD python3 -m scandrill.cli tools                    # tool wiring
```

Full pipeline on a real scan:
```bash
python3 -m scandrill.cli adf --job J --from-dir <raw_dir>   # ingest+deskew
python3 -m scandrill.cli assemble J.ingest.json -o J.pdf --job-dir <raw_dir> \
        --title T --author A --lang de-DE                   # add --ocr only for humans
python3 -m scandrill.cli handoff J.ingest.json --pdf J.pdf --analyze size,route
```

## Do NOT

- Route page images through Ghostscript, or "optimise" the img2pdf path.
- Hand pdfdrill an `--ocr` PDF and trust `route` (see §3).
- Hardcode `airscan:eN:` or `<pdf>.drill.json`.
- Reimplement `fuse_duplex`, `safe_filename`, or `under_root`.
- Delete `*.drill.json`, or make `Sidecar._load()` drop unknown keys.
- `curl`/`wget`/`tar` a PDF or e-print (SKILL rule 1).

## Housekeeping (unrelated to this integration, but outstanding)

`~/WKprivate/Scanned/ocr.sh` has **hardcoded MathPix `app_id`/`app_key` in
plaintext** (lines 12–13, 35–37). Move to `.env` and rotate.
