# The reader ladder — three rungs, cheapest first

Set by the owner on 2026-11-02, after auditing `d09.md` (Avetissian,
*Relativistic Nonlinear Electrodynamics*, 514 pages, pdf2mmd2's reading
projected by `pdfdrill md`) and finding several errors per line from the first
content page on. Their words:

> Please organize some minimal tests of the first page after the front matter
> before creating a report that finds several errors per line from start to
> end. … Only if the number of errors is below 1/page it makes sense to compare
> with mathpix. I have seen the complete code to compare to Mathpix page by
> page, if this test had be used, I did not to inspect such a bad result …
> I am not need on check on this low level!

## The rule

**No report is written about a reading before the rung below it passes.**

| rung | instrument | cost | gate |
|---|---|---|---|
| **1** | `pdfdrill mdcheck <pdf>` — structure of the Markdown projection | free, no reference, no render | **< 1 error on the worst page** |
| **2** | one page against a Gemma4 reading | one metered page | agreement on that page |
| **3** | `pdfdrill linescmp <pdf> --reference <mathpix.lines.json>` — page by page | free when the reading is already bought | the full review |

Rung 3 was already written, is free, and its own summary calls it *"the
acceptance test for a reader"*. It was not run. That is why a 514-page document
was read by hand, and it is the whole reason this file exists: the instruments
were not missing, the order was.

## What rung 1 measures, and why its denominator is the page

`mdcheck` needs only the `.md` and the reading. Four classes, each taken from
d09 section 1.1:

- **E3 math-as-heading** — `## p = p + e E(τ)dτ, (1.5)`. A display equation
  emitted as a heading, so the mathematics is neither isolated nor delimited.
- **E1 level-inversion** — `### 1.1 Classical Dynamics of a Particle in the
  Field` followed by `## of Strong Plane Electromagnetic Wave`: the
  continuation of a title one level *shallower* than the title it continues.
- **E4 continuation-heading** — a heading opening with a lowercase connective
  (`of`, `with`, `and`) is a wrapped line, not a heading.
- **E2 heading-run** — a second heading at the *same* level with no prose
  between: one title broken across lines. A *deeper* heading with no prose is
  correct nesting and is not counted.

**One line, one error.** The classes overlap — a fragmented title is usually a
run and an inversion and a continuation — so each offending line is counted
once under its strongest class (E3 > E1 > E4 > E2). Otherwise the rate counts
one defect three times and the threshold means nothing.

**The verdict turns on the WORST page, never the document mean.** The first
version of this gate divided all errors by all pages: d09 scored 272/514 =
0.529/page and printed *"PASSES the owner's < 1/page gate"* about the exact
projection the owner had just condemned. A 514-page monograph is mostly
references and back matter with no headings, so a mean hides a catastrophic
first content page behind four hundred quiet ones. Without a reading to
attribute errors to pages, `mdcheck` returns **no verdict** rather than a
passing one.

## The d09 baseline, 2026-11-02

```
254 error(s) over 514 page(s), mean 0.494/page
  E3 math-as-heading 128   E1 level-inversion 86
  E2 heading-run      30   E4 continuation-heading 10
Worst: 7 error(s) on page 1 — FAILS the < 1/page gate
135 findings could not be attributed to a page (the projection rewrites text,
so a heading need not match a reading line verbatim); they count in the total
and NOT in the worst-page number.
```

Section 1.1, the page the owner audited, as `mdcheck` reports it:

```
L189  E1-level-inversion       # Interaction of a Charged Particle
L191  E4-continuation-heading  # with Strong Plane Electromagnetic
L193  E2-heading-run           # Wave in Vacuum
L201  E1-level-inversion       ## of Strong Plane Electromagnetic Wave
L211  E3-math-as-heading       ## p = p + e E(τ)dτ, (1.5)
L225  E3-math-as-heading       ## E = − ; H = rotA; divA = 0, (1.6)
…
```

Every line the owner found by reading, found mechanically, free, in under a
second.

## The distribution, measured 2026-11-02, five QED books

Set the bar from this, not from the extremes. pdf2mmd2's readings at branch
`heading-types` `bdd0f44`, each projected by `pdfdrill model` → `md`, checked
with `mdcheck`:

| book | pages | clean | 1 err | 2 err | 3+ | unplaced | errors | rate | worst | E1 | E2 | E3 | E4 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| d03 Gauge 5th V1 | 382 | 379 | 2 | 1 | 0 | 1 | 5 | 0.013 | 2 | 0 | 3 | 1 | 1 |
| d04 Gauge 4th V1 | 444 | 438 | 5 | 1 | 0 | 3 | 10 | 0.023 | 2 | 1 | 5 | 3 | 1 |
| d05 Gauge 4th V2 | 512 | 503 | 8 | 1 | 0 | 0 | 10 | 0.020 | 2 | 1 | 8 | 0 | 1 |
| d08 Quantenmechanik IV | 347 | 344 | 3 | 0 | 0 | 0 | 3 | 0.009 | 1 | 0 | 3 | 0 | 0 |
| d09 Avetissian | 514 | 510 | 3 | 1 | 0 | 0 | 5 | 0.010 | 2 | 0 | 3 | 0 | 2 |

What it says:

- **3 to 9 pages of 347–514 carry any error at all** — 98.3 % to 99.5 % of
  pages are clean.
- **No page anywhere carries three.** Each book with a worst of 2 has exactly
  ONE such page; every other error is a scattered singleton. There is no
  cluster left to find.
- **E2 (heading runs) is 22 of the 33 placed findings**, so what remains is
  overwhelmingly one class: a title still broken across lines. E3, the class
  that destroys mathematics and started this audit, is down to 4 — and some of
  those were a false positive of the gate's own (a numbered exercise heading
  citing an equation).
- For contrast, the same gate on the same document projected from the PDF's
  **text layer** rather than the reading: 254 errors, 0.494/page, worst page 6.
  Any bar must still fail that, which is why the rate alone cannot be the bar.

The trend on d09, one line per fix: **254 → 31 → 6 → 5**.

`mdcheck` prints this distribution itself, so the bar can be applied without a
side script.

## Whose defect is it

The gate is deliberately blind to that, which is what lets either side use it.
But the attribution is known and both halves are real:

- **A reader that emits one `section_header` per VISUAL line**, without joining
  a wrapped title, makes E2, E1 and E4 inevitable downstream. That is
  pdf2mmd2's half, and the fix is to join a title before typing it.
- **A projector that renders a `section_header` whose text is an equation as a
  heading**, and that assigns a continuation line a shallower level than the
  heading it continues, is pdfdrill's half (`md`).

Neither half is fixed by this gate. The gate stops the result being discovered
by the owner.

## Self-enforcement

`mdcheck` is a registered layer in `commands.yaml` with `requires: [md]`, so
`pdfdrill steps mdcheck <pdf>` shows the chain and `--ensure` builds the
projection it needs. It is not a script anybody has to remember: it is
reachable from the planner and from `status`, which is the difference audit A4
already drew between a capability and a tool.

The threshold is the owner's and is not to be relaxed to make a document pass.
A document that fails rung 1 is reported as failing rung 1 — not escalated to a
paid comparison, and not written up line by line.
