# The fastest path to an inspect page

Timings measured on this machine (16 cores), arXiv 2209.00445v3 (16 pages),
gs 400 DPI. Everything here is what the code actually does today, not a plan.

## The short answer

```bash
pdfdrill inspect <pdf> --ensure --pages 1-4 --dpi 120
```

`--ensure` builds only what is missing (`model` → `geometry` → `inspect`) and
prints ONE line. `--pages` is the single biggest lever: the inspector embeds a
downscaled JPEG per page, so a page range is the difference between a 300 KB
file and a 14 MB one.

## Where the time actually goes

| stage | cost | notes |
|---|---|---|
| `model` (born-digital, arXiv) | ~0.3 s from LaTeX source | 60 s if it falls to tesseract OCR |
| pdfminer text extraction | ~19 s per 335-page book | ~1.5 s for a 16-page paper |
| `geometry` (object regions) | < 1 s | text-matching against the lines |
| gs rasterize, 6 pages @400 DPI | 2.8 s | the dominant cost once pages are involved |
| inspector HTML assembly | < 1 s | |

So on a paper the whole chain is a few seconds; on a book the rasterizer and the
text extraction dominate, and BOTH scale with the page count you ask for.

## Levers, in the order they pay off

1. **`--pages N-M`** — restricts the elements tree AND the embedded images. A
   whole-book inspector is a 14 MB HTML that chokes a reverse proxy.
2. **`--dpi 120`** (the default for the embedded page JPEGs) — this is the
   INSPECTOR's display resolution, independent of the 400 DPI floor the OCR and
   vision routes need. Raising it buys nothing on screen.
3. **`--no-images`** — boxes-only. The tree, the inspector pane and the copy
   actions all still work; you lose only the page bitmap behind the boxes.
4. **Reuse.** `inspect` is idempotent: with the model and geometry current it
   only re-renders. `--force` re-renders everything and is rarely what you want.

## Ghostscript: threads need banding

gs is the only rasterizer (`RASTER_MIN_DPI = 400`) and sits on the critical path
of inspect, OCR, vision and eqblobs. `-dNumRenderingThreads` alone does almost
nothing, because by default the whole page fits ONE band and the threads have
nothing to divide. Measured, 6 pages at 400 DPI:

```
default (one band, no threads)        3.44s
-dNumRenderingThreads=8 alone         3.17s   (~8%, near noise)
banded (-dMaxBitmap=8M) + threads=8   2.76s   (20%)
banded alone (threads unset)          3.45s   (nothing)
```

They are a PAIR. `pdf_reading.gs_render_args()` is the single place that sets
both (`RENDER_THREADS = max(8, min(cpu_count, 16))`), used by all three gs call
sites, which previously duplicated the invocation with none of them threaded.

## What the inspector needs from the model

`inspect` draws a box per object from `props["region"]`. A model built from
LaTeX source has NO geometry until `geometry` attaches it — that is why
`inspect` declares `geometry` as a prerequisite (`done_when: model:geometry`,
which asks the MODEL whether objects carry regions rather than whether a
command once ran).

Current coverage is partial and worth knowing before reading an empty-looking
page: on 2209.00445v3, 72 of 287 objects carry a region. 134 of the misses are
Formula/Citation objects, which have no text of their own to match — see
`docs/layers/L5-docobjects.md` for the model shape and
`merge_page_geometry` for the matching.

## Batch

For many documents, one process per document beats one loop: measured 151 s/doc
serial versus ~20 s/doc wall on 4 workers, because model building and projection
are CPU-bound and per-document. Cap each worker's address space — with the page
streaming fix a document peaks well under 2 GB, so a cap turns a pathological
file into one failed document instead of a machine-wide OOM.
