# T-0080 item 3 — the join, as a producer that writes lines.json

One page, as asked, before any code. Written to ENGINEERING 2d (owner,
2026-10-27): "there should be strict separation between tools that generate
lines.json like data and pdfdrill… pdf2mmd2, glyphdrill and Gemma should produce
lines.json formated output and not interfere with docmodel data". Relayed by
pdfdrill-pdf2mmd2-migration, who notes the owner may correct their reading of
"strict separation" as a package-and-file boundary inside this repo rather than a
return to separate repositories. This design assumes their reading.

## The measurement this has to move

`pdfdrill model` on 1702.06385, keyless, author's LaTeX present on all 170 maths
objects (that is 59018c8e):

| lines.json beside the PDF | lines | maths objects boxed | matched + interpolated |
|---|---|---|---|
| none — pdfdrill builds its own, source `pdfminer-chars` | — | **30 of 170** | 45 + 62 |
| `pdf2mmd2 <pdf>` — the reader's default warm-up (tsv) | 1029 | **31 of 170** | 56 + 59 |
| `pdf2mmd2 <pdf> --refine` — the glyph route | 955 | **40 of 170** | 65 + 68 |

The 30 reproduces the number pdfdrill-pdf2mmd2-migration measured independently.

**Corrected 2026-10-28, re-measured through the installed `pdf2mmd2` entry
point** (step 2b): the +10 holds only with `--refine`. This page first quoted
the 40 as the reader's number without naming the flag, from a roll-up whose
`total_pages` key I had written by hand while stamping a source onto a file that
declares none; the real reader writes `source` and `pages` and nothing else. The
default warm-up reads poppler's text layer — the same ink pdfdrill already reads
for itself — and is worth **+1**. `--refine` patches the lines from the page's
own glyphs (33471 glyphs, 0 unassigned, agreement_min 0.9106, 0.6 s for 9
pages), and is worth **+10**.

**So the join still has 130 to answer for, and whoever runs the reader must pass
`--refine`.** The entry point does not pass it for them: a front door that
quietly adds a flag the caller did not type is the worse defect.

## Why 130 miss, measured not assumed

`merge_page_geometry` (commands.py:984) says what it does in its own docstring:
a `page` prop "resolved by matching its opening text against that page's text…
Text matching, not coordinates: a source object has no coordinates to match
WITH." That is right for prose and structurally wrong for mathematics. A
formula's "opening text" is LaTeX markup the author wrote; the reader's page text
is the reader's own reconstruction from glyphs. The two describe the same ink and
share almost no characters, so the match fails on nearly every formula and
succeeds on the few whose markup happens to look like text.

So this is not a threshold to loosen. It is a different comparison.

## Shape: a producer, not a merge change

Under 2d the join may not touch a docmodel. It is a third reader:

    author's e-print LaTeX  ─┐
                             ├─►  join producer  ──►  <stem>.lines.json
    pdf2mmd2's lines.json   ─┘                        (declared source)
                                                            │
                                      `pdfdrill model` reads it like any reader

Its output is a lines.json carrying **the author's exact LaTeX in the text
fields, on the reader's regions**. pdfdrill is unchanged except for admitting the
source value, and the join can be re-run, diffed and audited as a file.

## The source value, and why it is not `pdf2mmd2`

Proposed: **`pdf2mmd2-authorlatex`**.

It must differ from `pdf2mmd2`, because the two files carry the same geometry and
*different kinds of LaTeX* — the reader's reconstruction (a measurement) versus
the author's own (gold). pdfdrill's provenance pair `latex` / `latex_original`
depends on telling them apart, and a consumer handed one source value for both
cannot.

The prefix is deliberate. Both gates already admit a source by prefix —
`_is_page_pixel_source` and `_is_typed_geometry_lines` each test
`src == s or src.startswith(s + "-")` — so `pdf2mmd2-authorlatex` is admitted as
page-pixel, typed geometry with **no edit to either tuple**, while
`_is_mathpix_lines` still answers no, which is what the four money-spending call
sites ask. A fresh unrelated name would need both tuples edited and would
silently fail the geometry gate until they were.

## What it matches on

Three conditions, all required, applied in this order:

1. **Monotonic alignment, not best match.** The author's formulas are in
   document order; the reader's lines are in (page, reading) order. The join is a
   single monotonic alignment over both sequences, so a formula can never be
   placed before its predecessor's box. This is what stops a formula landing on a
   visually similar box twelve pages away — the failure mode that makes a wrong
   box worse than no box, because the inspector then shows it confidently.
2. **Token agreement after normalisation.** Both sides reduce to a token
   sequence: drop spacing and `\left`/`\right`, drop braces that do not change
   content, apply `latex_only.resolve` so the author's `\textsc{X}` and the
   reader's `\text{X}` agree (that rule landed today, `eed1a30f`), and map
   glyph-name differences through the reader's own `latexsyms`/`mathtex` tables
   rather than a table of mine. Agreement is computed on the token sequence, not
   on characters.
3. **A structural guard.** Token count within a factor, and the candidate line's
   type must be one mathematics may occupy.

## What counts as a miss, and the counts the gate wants

Three outcomes per author formula, reported separately by kind
(Formula / Equation), because they are different defects:

- **placed** — aligned and above threshold;
- **no candidate** — the alignment offered nothing on that page: a reader
  coverage problem;
- **refused** — a candidate existed and lost on agreement: a normalisation
  problem, i.e. mine.

Collapsing the last two into "miss" is what would hide which half to work on.

## Fail closed: the planted mismatched e-print

The gate's planted case is another paper's e-print against this PDF. The required
result is **0 placed, not a handful**. A per-formula threshold alone cannot give
that — in two long documents some pair always agrees. So the join also tests the
alignment **globally**: if the fraction of author formulas placed falls below a
floor, the whole document is refused and the producer writes no lines.json,
naming the mismatch. A join that quietly places 3 of 170 from the wrong paper is
worse than one that refuses, because the 3 are indistinguishable from real ones
downstream.

## The `""` loophole (2d rule 5)

`_TYPED_GEOMETRY_SOURCES = ("", "mathpix", …)` admits a lines.json that declares
no source at all. Its own docstring records why: our glyph reader's output
"satisfied `inspect`'s prerequisite only because of 168 legacy files that forgot
to declare a top-level source". The reader's current output passes the geometry
gate through exactly that hole — which is how I got the 40 above, by hand-stamping
a source onto a file that declares none.

Proposal: **refuse a source-less lines.json, and stamp the 168 rather than
grandfather them by name.** A name list rots, and those files are pdfdrill's own
output whose producer is determinable from their content. Refusal should name the
one command that stamps a file, so the failure is a next step rather than a wall.
Stamping writes beside documents in the library, so it needs the owner's word and
is **proposed, not done**. Until then the test is the one the migration peer
asked for: a lines.json produced by the new route with no declared source is
refused.

## Not in this design, deliberately

- **Pictures.** They carry no text, so no token comparison can place them; they
  need a geometric join against the reader's ink regions. Named here because it
  is the obvious next question, and it is a separate design.
- **`merge_page_geometry`'s prose matching.** Untouched. It works for what it was
  written for.
- **The 168 files themselves.** Not stamped, not listed, not moved.
