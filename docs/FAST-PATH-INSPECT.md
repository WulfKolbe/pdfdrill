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
| `model` (born-digital, arXiv) | ~0.3 s from LaTeX source | the chain now ENDS at the free lanes; the 60 s tesseract fallthrough was removed with the engine (905k) |
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

## Ghostscript: parallelise by PAGE RANGE, not by threads

gs is single-threaded per render job, so on a scan the cores only get used by
running several gs processes over DISJOINT page ranges. Measured on a 282-page
scanned book, 32 pages at 400 DPI:

```
1 process, no threads      8.7s
1 process, threads=16      8.4s   (3% — threading does nothing here)
 4 processes               2.5s   3.5x
 8 processes               1.6s   5.3x
16 processes               1.4s   6.3x
```

`rasterize` shards the requested pages across `render_plan(pages)[0]`
processes (`plan_shards`), which took a real 32-page render from 8.7 s to 2.2 s.

**The trap:** gs restarts its `%d` output counter at 1 for EVERY invocation, so
parallel ranges sharing one `-sOutputFile=out/%03d.png` template overwrite each
other — verified: two jobs of four pages left FOUR files instead of eight, with
no error. Each shard therefore renders into its own directory and the files are
moved to their true page numbers afterwards.

**Second trap:** a shard becomes one `-dFirstPage..-dLastPage` range, so a shard
spanning a gap renders the pages in between. Requesting 3, 7, 11 across two
workers produced six files; the page numbers were correct, which is what made it
easy to miss. `plan_shards` splits on contiguous runs first and only then
balances.

## Ghostscript: threads need banding (the smaller lever)

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

They are a PAIR. `pdf_reading.gs_render_args(threads)` is the single place that
sets both, used by all three gs call sites, which previously duplicated the
invocation with none of them threaded.

**The thread count is not independent of the process count** (2026-10-27). It
used to be: `RENDER_THREADS = max(8, min(cpu_count, 16))` beside
`RENDER_WORKERS = max(1, min(cpu_count, 16))`, which multiply to 256 rendering
threads on 16 cores for ONE `rasterize` call — measured once at 241 gs
processes and load average 137. `render_plan(pages)` now returns both halves
from one budget, `workers * threads <= len(os.sched_getaffinity(0))`, spending
it on processes first because sharding is the 6.3x lever above and threads
~20%. `os.sched_getaffinity` rather than `os.cpu_count` so that a `taskset`
pin is obeyed. `PDFDRILL_GS_WORKERS` / `PDFDRILL_GS_THREADS` lower the budget
and can never raise it.

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
