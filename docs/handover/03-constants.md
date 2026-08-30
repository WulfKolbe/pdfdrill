# Measured constants

Every number here was paid for. Do not re-derive one by reasoning; look it up
or re-measure it deliberately.

## Noise floors

**Render-vs-scan: p50 39, p90 141 components** on structurally-clean confident
equations.

**inkdrill's floor of 7 belongs to a rasteriser comparison** — one render
through two rasterisers. Applying it to render-vs-scan would flag seven
equations in eight, and 119 showed those flags are typography.

**Spacing, normalised by median glyph width: the cut is ~0.45 glyph widths.**
Bimodal — main mode 0.10–0.20, trough 0.40–0.50, second mode 1.00–1.25, then a
hard right edge, which is what a fixed-width space produces. Normalised by
median *gap* it does not separate at all.

## Corpus shape

~1,350 drilled documents. ~95,470 equations carrying a confidence value:

| band | count | share |
|---|---|---|
| < 0.1 | 429 | 0.45% |
| 0.1–0.5 | 2,802 | 2.93% |
| 0.5–0.9 | 12,084 | 12.66% |
| ≥ 0.9 | 80,155 | 83.96% |

3,998,456 `lines.json` line objects across 37 types.

## What the LLM route can and cannot do

**Variant C** (image + MathPix's own prior) helps **only below confidence 0.1**,
median −8. Nothing above 0.9. Nothing in 0.1–0.5.

**A bare transcribe prompt makes things worse** (+146). **A notation hint alone
is worst** (+196) and was retired after 39 rows across two bands.

**The proposer is the bottleneck, not the gate.** Grok's EQ0515 proposal took
the ink 91 → 0 — an exact topological match, 156 components and 36 holes on
both sides, between images of *different* sizes. minimax-m3 on the same row
moved it 91 → 91 and echoed its neighbour back byte-identically.

**An empty reply from a token budget is not a refusal.** minimax-m3 spends
completion tokens reasoning before emitting: 4,000 returned nothing where
16,000 answered in 82 characters.

## Annotation recovery

Given a base image, its crop, and a **stated** position, the model reproduces
the author's TikZ:

| placement | n | ink distances | median |
|---|---|---|---|
| around | 4 | 2, 6, 10, 22 | 10 |
| overlapping | 3 | 72, 180, 216 | 180 |

Eighteenfold, and the populations do not touch. A stated direction helps
decisively; an overlapping annotation is not recoverable from the images alone.

**Placement split, measured from compiled PDFs**: around 106, overlapping 62 —
37% overlapping. Computing extents from `scale=`/`width=` arithmetic instead
gave 59%, because too large an extent pulls siblings inside it and
**manufactures overlap**.

## Structural checks

**Declared column count** finds 961 values across 177 documents whose row
disagrees with its own `\begin{array}` preamble. **Numeric uniformity is silent
on 773 of them (80.4%)** — it needs ≥60% bare-number cells, it compares rows to
each other so a table short by the same amount on every row is uniform and
wrong, and it needs two rows to have an opinion.

**`\right.` with no visible closer**: 4,310 occurrences, 1,921 opened by
`\left(` — the suspicious class, since a parenthesis is rarely one-sided.

**CJK internal tokens**: 26 in 335,043 values.

**Arity mismatch** (a relation symbol carrying a sub/superscript): 20 hits
across 1,345 documents, 14 misreads and 6 legitimate.

**Frequency check** (same position, rare spelling against common): **negative at
corpus scale** — 37,505 hits dominated by ordinary mathematics such as
`\lambda` against `\alpha` as indices. It works on `2010.14265` only because
that document has one dominant relation.

## Geometry facts

**The tex.zip filename is the region**:
`<process-id>-<page>_<height>_<width>_<top_left_y>_<top_left_x>.jpg`, verified
at 20,276 of 20,287 exact. The older collision-numbered format does not exist
in this corpus.

**Of 38,102 diagram/chart/table lines**: 20,355 carry both a crop URL and a
region, 17,747 a region but no URL, **zero a URL without a region**.

**Inline formulas have no region of their own** — 107,222 of 108,594 can only
inherit the parent line's box, and 82.7% share that line with another formula.
MathPix text lines carry no character-level geometry, so no narrowing exists.

**`\mathbb{<digit>}`**: `amssymb`'s `\mathbb` is msbm, covering A–Z, and the
digit slots hold negated relations. `\mathbb{1}` → ⊮, `\mathbb{0}` → ⊬,
`\mathbb{2}` → ⊭. 758 occurrences across 44 documents; **0 of 758 was
transcribing a real turnstile**. `bbm10` carries digits 1 2 7 8 9; `dsrom10`
carries only 1, which is why the dsfont swap was retired.
