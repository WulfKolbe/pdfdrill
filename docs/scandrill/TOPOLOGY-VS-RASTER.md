# BlobTracker vs pylepto/Leptonica — status and division of labor

Answers the standing question: *"the status of BlobTracker remains unclear — I
hoped Leptonica could take over all these functions."*

**Short answer: Leptonica cannot absorb BlobTracker, and shouldn't.** They are
not competitors at the same layer — they are *sequential* layers. Leptonica works
on **pixels**; BlobTracker works on **run-length coordinate sets** produced by one
pass over those pixels. Everything BlobTracker does after that pass costs
`O(runs)` and needs no image resident at all. That is exactly why "counting holes
is easy" and why it can drill down to a single glyph's coordinate set.

## Verified status (2026-07-15)

| Fact | Evidence |
|---|---|
| BlobTracker is **not yet in pdfdrill** | no `src/pdfdrill/blobtrack.py`; no `blob*`/`topo*`/`lepto*` module anywhere in `pdfdrill/src` |
| It is **staged** for migration, destination already named | `blobtrack.py:15` — *"Destination: ~/MX/PDFDRILL/src/pdfdrill/blobtrack.py"* |
| It has **two generations** | `blobcc.py`/`blobcc.ts` (31 May, streaming, stdlib-only, TS twin must match bit-for-bit) → `blobtrack.py` + `blobtopo.py` (11 Jul, richer, explicitly PDFDRILL-targeted) |
| pylepto is likewise an **incubator** for pdfdrill | `pylepto/CLAUDE.md`: *"the incubator for image-processing helpers that get integrated into the user's pdfdrill pipeline"* |

So both repos are pre-integration staging areas for pdfdrill. SCANDRILL should
call them through `scandrill/tools.py` and expect the call sites to simplify
(not disappear) once they land in pdfdrill.

## The boundary rule

> **If answering the question requires looking at pixels again, it's Leptonica's.
> If it can be answered from run-length coordinate sets, it's BlobTracker's.**

After the single connected-component pass, prefer topology: it is `O(runs)`, not
`O(width × height)`, and the image can be freed.

| | **pylepto / Leptonica** | **BlobTracker (blobcc / blobtrack + blobtopo)** |
|---|---|---|
| Domain | raster — pixel buffers | topology — `Blob.runs` coordinate sets |
| Input | grayscale/binary image, resident | one scan pass, then no image |
| Cost model | ∝ pixels; each new question = another full-image pass | ∝ runs; unlimited questions after one pass |
| Deps | `libleptonica.so.6` via ctypes | stdlib only (numpy/Pillow optional accelerators) |
| Streaming | no — whole image | **yes** — `blobcc` emits blobs on closure, bounded memory on a line-scan stream |
| Strong at | binarization, morphology, seedfill, rank reduction, halftone/figure masks, table-rule openings, sweep-and-search skew | holes/genus, boundary loops, glyph normalization, proximity grouping, rows/columns, principal-axis skew from rule blobs |
| Weak at | answering many small structural questions (each costs a pass) | anything needing greyscale/photometric evidence |

## What BlobTracker gives that Leptonica does not (concretely)

From `blobtopo.py` — all consuming `Blob.runs`, never mutating them
(the "page-lifetime memory contract"):

- **`holes(blob)` → hole components as first-class inverse Blobs.** Counting holes
  is `len(holes(b))`. This is genus/Euler information *for free* from the
  background components of the local mask that don't touch the border. In the
  raster world this is a seedfill + Euler pass per blob.
- **`glyph_map` / `glyph_point` / `glyph_runs`** — affine-normalize a blob's bbox
  onto a `size × size` glyph square (`fit` preserves aspect, `stretch` doesn't)
  and re-emit its runs in glyph space. *This is literally "drill down to a single
  glyph coordinate set"* — a scale-invariant, comparable signature with no
  rasterization.
- **`near_pairs` / `near_groups`** — union-find over small blobs within `gap` px of
  a neighbour. This is the **diacritic problem**: the i-dot, and German ä/ö/ü
  umlauts, are separate components that must re-attach to their parent glyph.
  Bbox-gap prefilter, then exact min pixel distance.
- **`boundary_pixels` / `boundary_loops`** — outer contour + one loop per hole,
  computed from run endpoints without rasterizing.
- **`rows(blobs)` / `columns(blobs)`** — text-line and column grouping by 1-D
  interval overlap union-find. Reading order without OCR.
- **`blobcc.estimate_skew_deg`** — column-scan isolates a horizontal rule as one
  long high-aspect blob; its principal axis `θ = ½·atan2(2μ11, μ20−μ02)` *is* the
  page skew. Recovers synthetic angles to **<0.002°**, and the moments are O(1)
  per blob — skew comes free with the CC pass.
- **`blobtrack.find_trim_box`** + `cropmark.py` — trim/crop marks are a
  topological arrangement, not a texture.

## Where they overlap: skew (keep both, reconcile)

Four skew sources exist. They do **not** conflict — they have different failure
modes, so the design is measure-many, reconcile-once:

| Source | Best on | Note |
|---|---|---|
| `blobcc.estimate_skew_deg` (rule-blob principal axis) | pages with rules/tables | fast path, free with the CC pass |
| `deskew.py` Hough over glyph bottom edges | text-only pages | blobcc's fallback below `BLOB_CONF_FLOOR = 0.35` |
| pylepto `pixFindSkewSweepAndSearch` | general scans | validated; **confidence < 3.0 = untrustworthy** |
| `./deskew` binary (galfar) | applying the rotation | what scanp.sh actually calls today |

**All three tools independently agree on the duplex rule:** the two sides of one
ADF sheet went through at the same physical tilt, so `angle(back) == −angle(front)`;
a weak side is corrected from the strong side, sign-flipped
(`scand.py:fuse_duplex`, and pylepto's *"back pages get the NEGATED front angle
because they are too sparse to measure reliably"*). SCANDRILL adopts this.

### Sign-convention hazard (carry into every call site)
- BlobTracker **and** Leptonica: **positive = counter-clockwise**. They agree.
- ImageMagick `-rotate` is **positive-clockwise** → pass the angle as-is to IM,
  **negate** it for PIL/cv2 (`BlobTracker/CLAUDE.md`).
- Leptonica: "rotate **clockwise** by the reported angle to deskew."
- pylepto's sign convention is verified against the user's reference values —
  **do not flip it.**

## Proposed ownership inside SCANDRILL

| Job | Owner | Why |
|---|---|---|
| Blank detection | **BlobTracker** (blob count above noise area), mean as a cheap prefilter | topology is robust where the mean fails — see below |
| Skew measure | blobcc fast path → Hough fallback → pylepto sweep as arbiter | different failure modes |
| Skew apply | `./deskew` binary | works today, already in scanp.sh |
| Duplex fusion | `fuse_duplex` rule | all three tools agree |
| Trim box / crop marks | **BlobTracker** | topological arrangement |
| Figure / halftone regions | **pylepto** | needs greyscale photometry |
| Table rules | **pylepto** (morphological openings) + blobcc cross-check | validated 12/12 |
| Glyph coordinate sets, holes, diacritics, rows | **BlobTracker** | O(runs), no image |
| QR / DataMatrix | `qrscan.py` → pdfdrill `qr` | already exists |

### Why topology beats the mean for blank detection
`scanp.sh` uses grayscale mean > 0.999. Two known failure modes:
- **Faint pencil page** → mean stays ≈1.0 → wrongly dropped. Blob count > 0 saves it.
- **Gray-cast / dirty-platen scan** → mean < 0.999 → wrongly kept. Blob count ≈ 0
  (above a noise-area floor) correctly drops it.

Proposal: keep the mean as the O(pixels) prefilter (it's already there and cheap),
but let a blob-count check arbitrate the band near the threshold. Record **both**
`blank_mean` and `blank_blobs` in `ingest.json` so the rule can be tuned from real
data instead of guessed.
