# I-D) ADF ingestion via scanp / scanimage

`scanp.sh` already contains most of the steps needed — but it is a *terminal*
script (scan → PDF-ready files, everything else discarded), while SCANDRILL needs
a *producer* (scan → manifest entries, nothing discarded). So:

> **Reuse scanp.sh's recipe. Do not reuse its file management.**

The recipe is the asset: the exact `scanimage` flags, the thresholds, the
`is_empty` check, the deskew invocation, the duplex pairing. The `rm`s are not.

## What scanp.sh destroys that SCANDRILL needs

| scanp.sh line | What it does | Why it breaks the manifest |
|---|---|---|
| `rm -f "$front"` / `rm -f "$back"` | deletes the raw scan after deskew | raw provenance is gone; `sha256` can never be recomputed, and deskew is **not** reversible |
| `rm -f "$front"` on both-blank sheets | deletes blank pages entirely | **violates the stage-III contract** — pdfdrill must be able to account for removed pages. They must survive as `status: removed_blank`, never be deleted |
| `deskew -o ...` writes over the kept name | bakes a lossy resample into the only surviving copy | the angle is never recorded; a downstream tool can't know the page was rotated, by how much, or with what confidence |
| one `ts` per sheet, `_front`/`_back` suffix | sheet identity is *implicit* in a shared timestamp | two sheets scanned in the same second collide; sheet/side belongs in the manifest as data, not in the filename |
| `mapfile … sort -V` after the run | ordering recovered from filenames post-hoc | fine, but loses the ADF emission order that `--batch-print` could give directly |

None of this is a criticism of scanp.sh — it is exactly right for its job
(produce deskewed pages, drop the junk). It is the wrong shape for an ingestion
front-end, which must be **non-destructive and fully recorded**.

## Device discovery — a real bug to fix, not inherit

The scripts hardcode the device, and **they disagree**:

- `~/WKprivate/Scanned/scanp.sh` → `airscan:e1:HP OfficeJet Pro 8730 [FAED2B]`
- `~/BlobTracker/scand.py` / `scanp.sh` → `airscan:e0:HP OfficeJet Pro 8730 [FAED2B]`

Both cannot be right. Live `scanimage -L` (verified 2026-07-15, ~45 s — a short
timeout returns only the first device) shows the printer exposing **four backends
at once**:

```
hpaio:/net/HP_OfficeJet_Pro_8730?ip=192.168.178.120        HPLIP
hpaio:/net/officejet_pro_8730?ip=…&queue=false             HPLIP (duplicate)
escl:https://192.168.178.120:443                           sane-escl, "platen,adf scanner"
airscan:e0:HP OfficeJet Pro 8730 [FAED2B]                  sane-airscan, eSCL
```

**So `airscan:e0` is correct today and `scanp.sh`'s `airscan:e1` is stale.**
That is not a typo in one script — it is direct evidence of the failure mode:
in `airscan:eN:…` the `eN` is a **discovery-order index** assigned as the eSCL
backend finds devices over mDNS, so it drifts across machines, reboots, and
network states. `scand.py` and `scanp.sh` were each right *when written*.

**Proposal:** never hardcode. Resolve at runtime (implemented in
`producers/adf.py:resolve_device`):
1. explicit `--device` argument (always wins, never enumerates),
2. `SCANDRILL_DEVICE` env var,
3. `scanimage -L`, filtered by a model substring and ranked by backend
   preference: **`airscan:` > `escl:` > `hpaio:` > unknown**,
4. fail loudly rather than guess.

Why that ranking: `airscan:` is what the tested scripts target; `escl:` speaks the
same eSCL protocol but is **IP-pinned** (`escl:https://192.168.178.120:443`) and
so breaks on a DHCP lease change; `hpaio:` (HPLIP) is the last resort. Live check:
the resolver now returns `airscan:e0:HP OfficeJet Pro 8730 [FAED2B]`.

Record the *resolved* device string in each page's `origin` — so a job stays
reproducible after the index shuffles.

Caveats probed and settled:
- **ADF source name** — resolved, not a risk: `scanimage -d <dev> --help` reports
  `['Flatbed', 'ADF', 'ADF Duplex']`, so scanp.sh's `--source "ADF Duplex"` is
  valid on this device. The producer still probes rather than assumes.
- **Binary noise on stdout** — appeared only with a too-short timeout (partial
  output); with ~45 s all four devices parse cleanly. The parser decodes with
  `errors="replace"` and regex-scans for ``device `…'`` lines regardless, so it
  survives either way. Allow a generous timeout: mDNS discovery is slow.

## The producer design

```
scanimage (scanp.sh flags)  →  raw/   (never touched again)
        ↓ pair sides into sheets (scand.py convention)
   per side: blank check + skew measure     (RECORD, don't act)
        ↓ fuse_duplex per sheet  (angle(back) == −angle(front))
   optional: deskew → proc/     (raw retained; skew_applied=true)
        ↓
   ingest.json   ← blanks kept as removed_blank
```

**Sheet/side model** (from `scand.py`, single-pass duplex):
`page1 = sheet1-front, page2 = sheet1-back, page3 = sheet2-front, …`; an odd
trailing page is a front with no back. Each page records
`origin = {kind: "adf", device, sheet: N, side: "front"|"back", batch_index}`.

**Proven flags to carry over verbatim** (from scanp.sh):
```
--source "ADF Duplex" --mode Color --resolution 300 --format png
--batch="raw_%d.png"  -l 0 -t 0 -x 210 -y 290        # A4 crop, mm
```
Thresholds: `EMPTY_THRESHOLD=0.999`, `SHAVE_BORDER=40`, `MAX_SKEW=8`, `MIN_SKEW=0.2`.

**Blank policy change:** scanp.sh drops a sheet only when *both* sides are blank.
SCANDRILL records **per side** (`removed_blank`) and lets assembly decide — a blank
back with a printed front must still be accountable to pdfdrill. Keep both
`blank_mean` and (when BlobTracker is wired) `blank_blobs`, per
[TOPOLOGY-VS-RASTER.md](TOPOLOGY-VS-RASTER.md).

**Skew policy:** measure and record (`skew_deg`, `skew_conf`, `skew_source`);
apply only on request (`--deskew`), writing to `proc/` and setting
`skew_applied`. Rotation resamples every pixel — it is **not** lossless, so it
must be an opt-in, recorded, reversible-by-reference decision, never silent.
`--batch-print` is *not* used by the tested script (it globs `sort -V` after the
run); keep the tested path and treat streaming as a later opt-in.

## Testability without paper in the feeder

A live ADF run needs hardware and paper, so the producer takes a
**`--from-dir`** mode: skip `scanimage`, ingest an existing directory of
`raw_%d.png` exactly as if the scanner had produced it. This makes the sheet
pairing, blank policy, duplex fusion, and manifest shape testable offline and in
CI, with the live path differing only in who wrote the files.

## Build order
1. `producers/adf.py`: device resolution + `--from-dir` pairing/blank/manifest — testable now.
2. Live `scanimage` path behind the resolved device.
3. Skew measure via BlobTracker/pylepto seams + `fuse_duplex`.
4. Opt-in `--deskew` into `proc/`.
