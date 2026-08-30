# State of each workstream

## Running now

**295** — corpus region pass, ~800 of 1,346. Builds a region report per
document and compiles each region standalone. Produces *region compiles*, not
ink. Resumable; has died three times from memory pressure and now checkpoints
per document.

**322** — doubted-rows ink pass, ~170 of 196. Measures equation-level ink for
documents holding at least one equation below confidence 0.5. Library
`report.ink.json` count was 20 before this pass, 88 and climbing during.

Neither should be interrupted. Both commit per document.

## Published

Eleven QC reports at `pdfdrill.github.io/reports/`, each with `report.pdf`,
the `.md`, `inspect.html` and `report.ink.json`. 6,800 measured rows over
4,468 report pages.

Two more documents are prepared for publication and were the subject of the
last MathPix mail: `1510.06699` and `2103.01507`.

## Blocked or awaiting a decision

**The figure/annotation work is superseded where the author's source exists.**
`~/Downloads/2004.05631v1` holds 95 figures, each already
`\documentclass{standalone}` with the preamble inlined. Compile-from-source
reaches 95 of 95 — no model call, no crop pairing, no ink comparison. That is
the main route; the crop-pairing route below applies only where no source
exists.

**The crop pairing needs hand editing.** `report.tex` now carries a fifth
AUTHOR SOURCE column shipping `\authorsrc{...}` rendering the crop, so an
unedited row shows the crop twice. A person types the author's figure filename
over it; `pdfdrill figpairs` harvests it into `<stem>.figpairs.json`. Without
the editing the measurable population is 4; with it, 62.

**`inkconvert`'s legend rule is a known defect, deliberately unpatched.** It
treats a row as the legend when both five-tuples are all-zero, which holds
only for the 6-column table. On a 5-column table the legend's `\multicolumn`
covers the source cell and the row is not all-zero. 83 conversions rest on the
current rule.

**`reporttex` does not declare `inkconvert` in `requires`** although it reads
and adopts `report.ink.json`. The planner has therefore never offered to
produce ink before building a report.

**`1511.08771` cannot be loaded at all** — a 4.6 GB model. It has defeated the
oversized-formula quarantine, the prescript census and the declared-column
scan. Worth deciding whether it becomes a permanent named exclusion.

## Deferred

**Source listings.** `code` is 44,689 lines across 205 documents, now read
into `CodeListing` objects. 41 documents carry `lstlisting` in the e-print
against 205 with `code` lines from the OCR. Wulf will supply his own listing
preamble; whole modules as single files, with a derived interface layer
(Modula-2 definition-module shape) alongside.

**The `\mathbb{0}` gap.** `bbm10` has no zero, so it drops silently in three
documents.

## Never measured

**Whether a compiled region renders what is on the page.** Naming a tex.zip
file says which file. Compiling it says the LaTeX is valid. Neither says the
figure is right — and with macros already expanded, a macro that expanded
*wrong* rather than *missing* is exactly what only the pixel comparison would
catch.
