# Plan — parallel MathPix + pdfminer.six reconciliation

Status: plan (grounded on arXiv 2607.02234). Goal: run both extraction routes and
produce ONE correct model that keeps pdfminer's structural richness + geometry
while correcting its garbled math with MathPix's clean LaTeX. Region-matched,
per-aspect best-of.

## Grounding — what each route actually produces (2607.02234)

**pdfminer.six / DRILLPDFse route** (`source: pdfminer`):
- WINS: rich structure the MathPix route lacks — YAML front-matter (title, abstract
  as description, per-type counts), resolved `[CITATION: <citekey>]`, `\Figref{}`,
  `[FORMULA n]` / `[En]` transclusions, `\emph{}`, section headings; AND geometry in
  PDF points → `inspect --embed` is fully self-contained (crops cut from the inline
  raster, 0 cdn refs). This is the GitHub-Pages-demo route.
- LOSES: the MATH is badly garbled AT THE SOURCE (already broken in lines.json, so
  the fix is DRILLPDFse-side):
  1. char-by-char spacing — subscripts/words split: `_{O P S D}`, `l o g`;
  2. text↔math interleaving — prose captured into the equation region
     (`e n \mathcal{L}c e_{o}-_{u}o_{r s}n l=y t D e a...` = "ence only teacher");
  3. region over-capture — figure axis labels emitted as equations
     (`1 0 0_{7 0}^{O P S D-S t a n d a r d}...`);
  4. truncation — unbalanced braces (`P_{P M I` unclosed).
  The user's "last 2 characters leak into the math" is the mild end of #2/#3
  (region boundary too greedy).

**MathPix route**: clean per-equation LaTeX, but less structure and live
`cdn.mathpix.com` crop refs (not self-containable — pixel coords, remote image).

## The reconciliation model (pdfdrill already has the substrate)

pdfdrill's docmodel already supports competing provenances: `Realization` carries
`provenance` / `score` / `region`; `compare.html` renders LaTeX | KaTeX | image per
provenance; `latex` overlays gold LaTeX onto equation slots by similarity; `score`
computes cross-provenance agreement. This plan USES that substrate — no new store.

Per-ASPECT best-of policy (the core rule): for each reconciled object,
- **math body (latex)** ← MathPix (clean) when a region-matched MathPix equation
  exists; else keep pdfminer's (flagged low-confidence).
- **geometry / region** ← pdfminer (PDF points → self-contained inspect). NEVER
  adopt MathPix pixel coords into the app (coordinate systems don't mix; conversion
  is test/compare-time only — the established rule).
- **structure** (citations, figrefs, transclusions, front-matter, sections, emph)
  ← pdfminer (MathPix lacks these). Preserve verbatim.

## Phases

**P1 — dual-route build + region match.** `pdfdrill reconcile <pdf>` (new): ensure
a pdfminer model (structure+geometry) AND a MathPix lines.json exist (build the
missing one; MathPix is the paid step — never auto-run without a key, report if
absent). Match each pdfminer Equation to the MathPix equation covering the same
page-region: normalize BOTH to page-fraction [0,1] (pdfminer points ÷ page-pts;
MathPix pixels ÷ MathPix page-px) — comparison-only conversion — and pair by IoU /
containment (reuse `pdfimg_locate`'s IoU + `image_model`'s containment fusion).

**P2 — attach + adopt.** For each matched pair, attach the MathPix LaTeX as a
`provenance="mathpix"` Realization on the pdfminer Equation, and adopt it as the
authoritative `latex` (keeping `latex_pdfminer` as provenance) while leaving the
region/geometry and all structural props untouched. Unmatched pdfminer equations
keep their (flagged) latex; unmatched MathPix equations are surfaced (pdfminer
missed them — the reverse gap).

**P3 — math-garble QC (feeds DRILLPDFse).** A `mathcheck`-style detector over the
pdfminer math, so the errors are VISIBLE and correctable at the source:
`_is_char_spaced` (single-letter runs separated by spaces in a sub/superscript),
`_has_prose_interleave` (>N alpha tokens length-1 outside braces), `_over_captured`
(region width ≫ rendered math OR figure-caption sibling), `_truncated` (unbalanced
`{}` / `\left`-`\right`). Report counts + samples; each becomes a DRILLPDFse
extraction bug with a concrete case. (The extraction FIX is DRILLPDFse-side; the
reconciliation substitutes MathPix meanwhile.)

**P4 — inspect generator hardening (untested paths + the char leak).** The user
flagged the inspect HTML generator as untested and equations leaking trailing
chars. (a) Add generator tests over `build_inspector_html` (the payload/elements
shape, the client crop-rect math, the reflow) — currently only `build_from_paths`
is tested. (b) The trailing-char leak — NARROWED: the client crop (`cropFromPage`,
docinspect.py:683-690) uses the region FAITHFULLY, no padding/rounding
(`drawImage(im, b.x*sx, b.y*sy, b.w*sx, b.h*sy, …)`). So the leak is REGION-side,
one of: (i) the pdfminer equation region in lines.json is 2 chars too wide
(DRILLPDFse boundary), or (ii) `object_geometry` unions one line too many because
the Equation's realization RANGE [start,end] over-reaches by a line (pdfdrill
ingestion). Instrument one known 2607 equation (compare its region to the rendered
math extent) to pick (i) vs (ii); fix the owning side. (c) Keep the geometry-less
honest message (already shipped).

**P5 — projection keeps both.** `md`/`tiddlers`/`report` render the RECONCILED
model: MathPix math where adopted, pdfminer structure everywhere. Verify on
2607.02234 that citations/figrefs/transclusions survive AND the equations are the
clean MathPix forms.

## Ownership split

- pdfdrill: P1 (reconcile cmd + region match), P2 (attach/adopt), P3 (QC detector +
  report), P4 (inspect generator tests + fix the generator-side leak if it's there),
  P5 (projection).
- DRILLPDFse: the math EXTRACTION fixes (char-spacing joiner, prose/math separation,
  equation region tightening, brace balancing) — driven by P3's concrete cases.

## Non-goals / deferred

Embedding-based math matching (SPECTER2/math-embed) — region IoU suffices here.
Self-containing the MathPix route's own crops (local re-cut from the page raster) —
separate, only if paid-route demos are wanted; the pdfminer route already gives the
self-contained demo.

## First implementation step

P4(a)+P4(b) — the inspect generator tests + the char-leak, because it's fully
pdfdrill-side, unblocks the live demo the user already published, and is small.
Then P1–P3 (the reconcile command) as the substantive dual-route work.
