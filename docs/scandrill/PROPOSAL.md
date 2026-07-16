# SCANDRILL ingestion — proposal grounded in existing code

Survey of `~/WKprivate/Scanned` (scan scripts) and `~/MX/PDFDRILL` (the target
project) before proposing. The single biggest correction to the earlier
chatbot proposal:

> **Most of stages II and III already exist inside pdfdrill — but they operate on
> a PDF, not on loose images.** SCANDRILL's real, narrow job is the *front half*
> the chatbot under-weighted: turn ordered images into ONE lossless PDF + a
> sidecar, then hand that PDF to pdfdrill, which already knows how to segment,
> deskew-classify, detect page sequence, pick an OCR lane, and model it.

So: **don't rebuild II/III. Build the image→PDF bridge and reuse pdfdrill.**

---

## What already exists (reuse, do not reinvent)

### `~/WKprivate/Scanned/scanp.sh` — the whole D) path already works
A tested ADF-duplex scan script. It already does, in ~70 lines of bash:
- **Scan (I-D):** `scanimage -d "airscan:e1:HP OfficeJet Pro 8730 …" --source "ADF Duplex" --mode Color --resolution 300 --format png --batch="raw_%d.png" -l 0 -t 0 -x 210 -y 290`
- **Blank detection (II-C):** `convert … -shave 40x40 -colorspace Gray -format "%[fx:mean]"` and drops the sheet if mean > `0.999`.
- **Skew correction (II-B):** a compiled `./deskew` binary — `deskew -o out.png -b FFFFFF -a 8 -l 0.2 in.png` (max 8°, min 0.2°). Falls back to `cp` if it fails.
- **Naming (II-A):** one timestamp per physical sheet → `scan_YYYYMMDDHHMMSS_front.png` / `_back.png`.
- Duplex pairing (front[i], back[i+1]) with whole-sheet drop when both blank.

**Implication:** blank detection, skew, naming, and ADF are *solved primitives*.
SCANDRILL should call `scanp.sh` (or a light refactor of it) as its D) producer,
not re-implement any of it.

**Parallel-dev image tools (will be integrated into pdfdrill; SCANDRILL calls them):**
- **`~/BlobTracker`** — `blobcc` (connected components), `blobtrack`, `blobtopo`,
  `cropmark.py`, `qrscan.py`, and the `deskew` binary (byte-identical to the one
  in `Scanned/`). So `blobcc`/BlobTracker *does* exist — as a separate repo, not
  yet in pdfdrill. (Corrects an earlier note that said it didn't exist.)
- **`~/pylepto`** — Leptonica ctypes bindings with *validated* detectors: skew
  (`pixFindSkewSweepAndSearch`, front-page-only, conf<3.0 = untrustworthy),
  figure/halftone regions, page segmentation, table-rule recovery. The
  "incubator" that feeds pdfdrill; run at 300 dpi (scanner) or 600 dpi (Ghostscript).

These are reached through `scandrill/tools.py` adapters — the `deskew` binary
works today; pylepto skew is a provisional seam until pdfdrill exposes it.

### pdfdrill already covers most of II/III — on a PDF
Relevant existing subcommands (`~/MX/PDFDRILL/pdfdrill --help`):
- `folder <dir>` / `ls <dir> --images` — **folder ingestion already exists** (I-A over PDFs).
- `route <pdf> --run` — auto-picks the OCR lane: born-digital→pdfminer, scanned≤20p→Gemma-4, larger→MathPix.
- `ocr <pdf> --lang eng+equ` — **Tesseract → MathPix-compatible `lines.json`** (the Tesseract path the user named).
- `segment` / `ordered` / `autosegment` — partition a scanned bundle into ordered documents by sender + continuity number + DataMatrix tracking codes.
- `continuity` — margin OCR for "Seite N von M" sequence markers; attaches `seq` to Page objects.
- `pageside` — recto/verso classification.
- `rasterize` / `extractimages` / `images` / `tsv --ocr` / `qr` / `entities`.
- `pyramid` + `imageserve` — builds a deep-zoom tile pyramid and serves it (OpenSeadragon `/viewer.html`).

### drillui_bridge.ts already has the web-server scaffolding (I-B/I-C)
`~/MX/PDFDRILL/tools/drillui_bridge.ts` (Bun, 820 lines) already:
- Serves static files + a WebSocket, spawns Python per connection.
- Has **POST endpoints** (`/open`, `/edit`) and imports `writeFileSync` — so adding `POST /upload` (multipart) is a small, well-precedented change, **not** a restructure. (Confirms the chatbot's "can it host another route" assumption: yes, it already hosts several.)
- Has a lazy **image server** (`imageserve`) on a second port, proxied for `/cropped`, `/tiles`, `/viewer.html`.
- Already uses a file literally named `manifest.json` for the pyramid viewer.

---

## Contract 0 — the ingestion manifest (revised)

Keep the chatbot's idea of one canonical job artifact, with two corrections:

1. **Do NOT name it `manifest.json`** — that name is already taken by pdfdrill's
   pyramid viewer. Call it **`ingest.json`** (or `job.json`).
2. The manifest is the *ingress* record; pdfdrill's `.drill.json` sidecar
   (keys: `facts, evidence, pdfinfo, images_layer, layers, transitions, …`) is
   the *downstream* model. SCANDRILL's `ingest.json` must **merge into**, never
   clobber, that sidecar at stage III (the user's own standing finding: some
   commands overwrote rather than merged).

```json
{
  "job": "scan_20260715_143012",
  "created": "2026-07-15T14:30:12+02:00",
  "lang": "de-DE",
  "pdf": "scan_20260715_143012.pdf",
  "pages": [
    { "seq": 1, "src": "raw/scan_20260715143012_front.png",
      "origin": {"kind": "adf", "device": "airscan:e1:HP OfficeJet Pro 8730 [FAED2B]"},
      "sha256": "…", "mtime": 1752582612.4,
      "skew_deg": 1.7, "skew_applied": true, "blank_mean": 0.41,
      "status": "kept" }         // pending | kept | removed_blank | removed_user
  ]
}
```
Removed pages stay with a `removed_*` status (never deleted) → satisfies the
stage-III "pdfdrill must know removed pages" requirement for free.

---

## I) Ingestion — four producers, grounded

**A) CLI find (ordering).** Two NUL-safe modes; feed a tiny `ingest_add.py` that
hashes/stats/appends:
```bash
# by mtime
find "$SRC" -name "$MASK" -printf '%T@\t%p\0' | sort -zn | cut -z -f2-
# by name, version-aware (scan_2 < scan_10)
find "$SRC" -name "$MASK" -print0 | sort -zV
```
Note pdfdrill's `folder`/`ls` already does the PDF-folder case; SCANDRILL's A) is
the *image*-folder analogue that produces `ingest.json`.

**B) drillui drag & drop.** Two modes on the existing bridge:
- *Path-reference* (bridge owns the files): accept `text/uri-list` (`file://…`),
  validate against an allowlisted root (the bridge already has `safeResolve`
  root-safety for `/artifact`/`/open`), add manifest entries pointing at
  originals — zero copy.
- *Upload*: add `POST /job/:id/pages` (multipart, `req.formData()`, `Bun.write`)
  next to the existing `/open`/`/edit` POST handlers. Push manifest updates over
  the existing WebSocket so the page list is a render of `ingest.json`.

**C) Camera.** `getUserMedia → <video> → OffscreenCanvas → POST` to the same
upload endpoint (camera is just another producer). Realtime unwarp as a plug-in
contract, algorithm supplied later:
```ts
unwarp(frame: ImageData, params: UnwarpParams): ImageData   // Worker/WASM or WebGL shader
```
Store both raw and unwarped; manifest records which is `src`.

**D) scanimage / ADF.** **Reuse `scanp.sh`.** One correction to the chatbot: the
tested script uses `--batch="raw_%d.png"` and then **globs `sort -V` after the
run** — it does **not** use `--batch-print`/stdout-tail. So pick one:
- *Match the tested script:* run `scanp.sh $JOB/raw`, then ingest the resulting
  `scan_*_front/back.png` files (blank+skew+naming already applied). Simplest,
  lowest risk.
- *Streaming thumbnails:* add `--batch-print` to a copy of the script and have
  the bridge tail stdout (one filename per line → one manifest entry). Only if
  live per-page feedback matters; verify `--batch-print` works against the
  airscan backend first (currently unverified).

---

## II) Processing — mostly delegate

- **A) Naming + PDF metadata:** naming already done by scanp.sh. For the PDF,
  set `/Lang` (`de-DE`), Title/Producer, page labels via **`pikepdf`** after
  assembly. `lang` defaults from the job, per-page override in `ingest.json`.
- **B) Skew:** already applied by `deskew` in scanp.sh. Record `skew_deg` in the
  manifest for provenance. **Arbitrary-angle rotation is lossy** (resamples) —
  scanp.sh already accepts that tradeoff; if you want lossless, record the angle
  and let pdfdrill/OCR consume it, applying only 90° multiples via PDF `/Rotate`.
- **C) Blank:** already done by scanp.sh (ImageMagick mean > 0.999). If you need
  it *outside* the ADF path (folder/upload/camera), lift the same `is_empty()`
  check into `ingest_add.py`.
- **D) Lossless embedding — the one genuinely NEW piece.** pdfdrill has **no
  images→PDF assembly** (it is PDF-in; deps have `pypdf` but **not `img2pdf`**).
  Add `img2pdf` (pass-through: JPEG→DCTDecode, PNG→FlateDecode, no re-encode) →
  filter `ingest.json` to `kept` pages in `seq` order → `img2pdf` → `pikepdf`
  pass for `/Lang`, labels, `/Rotate`. This is SCANDRILL's core deliverable.

---

## III) Handoff to pdfdrill

Deliver the pair `scan_<ts>.pdf` + `scan_<ts>.ingest.json`. Then pdfdrill's
existing machinery takes over:
```bash
pdfdrill autosegment scan_<ts>.pdf   # ordered vs shuffled → segment/ordered
pdfdrill route scan_<ts>.pdf --run   # picks tesseract/gemma/mathpix lane
pdfdrill model scan_<ts>.pdf         # unified docmodel from lines.json
```
Merge `ingest.json` page-provenance **into** the `.drill.json` sidecar (origin
device, hashes, skew, blank scores, removed pages) rather than letting a later
`ocr`/`model`/`mathpix` run clobber it. Per the repo's standing rule, read
`src/pdfdrill/skill/SKILL.md` before writing integration code (and `pdfdrill
preflight --ack` is a hard gate on build/extract commands).

---

## Corrected assumptions from the earlier proposal

| Chatbot assumption | Finding |
|---|---|
| Port `blobcc`/`Bobtracker` for skew | Don't port — `~/BlobTracker` already has `blobcc` + the `deskew` binary, and `~/pylepto` has validated Leptonica skew. Call them; they're moving into pdfdrill. |
| ADF producer emits filenames on stdout (`--batch-print`); tail stdout | scanp.sh uses `--batch=` + post-run `sort -V` glob, not stdout. Match that or opt into `--batch-print` (unverified on airscan). |
| Bridge may need restructuring for an HTTP route | No — it already serves `/open`,`/edit` POST + static + WS; add `/upload` alongside. |
| Manifest named `manifest.json` | Collides with pdfdrill's pyramid `viewer/manifest.json`. Use `ingest.json`. |
| Stages II/III are new build | Largely exist in pdfdrill (`segment`/`ordered`/`continuity`/`pageside`/`route`/`ocr`). New work = images→PDF (`img2pdf`+`pikepdf`) + the ingest UI. |
| `text/uri-list` on drag varies by DE | Still true — verify on the target desktop (Solus). |

## Security note (not part of the design)
`~/WKprivate/Scanned/ocr.sh` has **hardcoded MathPix `app_id`/`app_key` in
plaintext** (lines 12–13, 35–37). Move them to env/`.env` (pdfdrill's `.env`
already holds keys) and rotate them, since this file may be shared.

---

## Suggested build order (smallest first)
1. `ingest.json` schema + `ingest_add.py` (hash/stat/append; lift `is_empty` from scanp.sh) — offline, no UI.
2. `img2pdf` + `pikepdf` assembly from a hand-written `ingest.json` → lossless PDF (verify by re-extracting image streams and hash-comparing).
3. D) wire `scanp.sh` as a producer (post-run glob).
4. B) bridge `POST /upload` + drop zone; WS-push the manifest.
5. A) `find`-based folder producer.
6. C) camera capture with identity `unwarp`; real unwarp last.
7. III) `autosegment`/`route`/`model` handoff + sidecar merge.
