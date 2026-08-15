# inkdrill → pdfdrill integration

MathPix reports what it **found**. Ink reports what is **there**. The
difference is the product.

Direction of the contract, and it does not bend: **inkdrill emits a
MathPix-shaped `lines.json`; pdfdrill consumes it.** pdfdrill never imports
inkdrill — that would couple a stdlib-only package to a dependency-bearing one
and reverse the direction. Where pdfdrill needs a rule inkdrill also has, the
rule is restated on the pdfdrill side **and put under test**, because a
re-implementation that drifted silently would make a genuine disagreement
between the two tools indistinguishable from a difference of definition.

---

## The contract gap — `page["ink"]["rules"]`

**Read this before the phase notes below; it corrects two of them.**

inkdrill carries a rule on the line it falls inside, and a rule that falls
inside NOTHING on the **page record**, at `page["ink"]["rules"]`. That key was
not in the interface contract, so this consumer read only the per-line arrays
and saw every rule except the ones with no owner — which on a booktabs page is
**all of them**, because booktabs emits no object for a rule to attach to.

That is a contract gap, and the fix on this side is one key:
`ink_coverage.page_rules` / `all_rules`, folded into `ink_boxes` via
`include_rules=True`, and claimed by a table's rectangle in `ink_tables`.

**The defect on my side was smaller and worse.** I ran a compiled booktabs
fixture through inkdrill, saw `lines 0`, and reported "the rules never leave
inkdrill" — while the page record of the file I had just generated held all
four. Absence has to be read out of the file, not inferred from one key being
empty. Both `docs` statements below that said Phase 1 and Phase 4 were blocked
were wrong for that reason and are corrected in place.

(inkdrill's side, per the same audit: say `page["ink"]["rules"]` in reports
rather than `free_rules` — the internal name sent this consumer looking for a
key that does not exist.)

---

## Phase 1 — coverage audit · BUILT

`pdfdrill inkcoverage <pdf> --ink <inkdrill.lines.json> [--page N]`
(`src/pdfdrill/ink_coverage.py`, `tests/test_ink_coverage.py`, 10 tests).

Partitions every ink component against the MathPix regions already in the
model: `inside` / `missed` / `straddling` / `overlapping`, plus regions with no
ink. **Members, not means** — the residual classes carry their member ids into
the sidecar under `ink_coverage`, because the per-page spread is the finding
and the aggregate buries it.

Two rules earn their keep:

- **Containment, not centres.** INSIDE requires the component's box to lie
  wholly within one region; any other intersection is STRADDLING. That is the
  case that clips the limits off a tall sum whose region was fitted to the body
  of the line — centres would call it comfortably inside and report nothing.
- **Containers are dropped.** `table` / `table_row` / `table_column` enclose
  their own cells, so every cell's ink falls inside two regions and lands in
  `overlapping`, which describes MathPix's nesting rather than the page.

Units travel with the data or the call fails: inkdrill declares
`ocr.units == "pt"` derived from the PNG's `pHYs`, and `ink_boxes` refuses
anything else. A pixel-space file read as points is a scale error that looks
exactly like a coverage finding.

### Measured, 2409.18839 page 8

Pipeline: `gs -r400 -sDEVICE=png16m` → `python3 -m inkdrill p8.png --glyphs
--page-number 8` → `pdfdrill inkcoverage`.

| | keeping containers | containers dropped |
|---|---|---|
| regions | 101 | 79 |
| inside | 36.25% | **47.78%** |
| overlapping | 63.72% | 52.10% |
| missed | 0 | **2** |
| straddling | 1 | 2 |
| region with no ink | 0 | 0 |

47.78% inside reproduces the plan's 47.4%. The missed count did not — see
below; that was the contract gap, not the page.

### RESOLVED — the 35 rules were on the page record

*Superseded. Kept because the reasoning below is what a `lines`-only reading
looks like from the inside, and it was wrong.*

With `page["ink"]["rules"]` read, page 8 reports exactly the plan's number:

```
page 8: 3246 ink components vs 79 regions — inside 48.55%, MISSED 35,
        straddling 2, overlapping 1633, empty regions 0
```

**MISSED 35, of which 33 are rules** — `379.3 × 1.08 pt` at the top,
`379.3 × 0.72` interior, `388.4 × 0.72` (the footnote separator), plus the
vertical separators. 379.3 pt = 2107 px at 400 dpi, matching the plan to the
pixel.

### What the lines-only reading concluded (wrong)

The plan's headline finding is that the 35 missed components on this page are
every table rule plus the footnote separator. They are real: `pdfplumber`
reports **35 vector lines** on page 8, the horizontal ones 379.19 pt wide —
exactly 2107 px at 400 dpi, matching the plan's measurement to the pixel.

They are absent from inkdrill's output, and the mechanism is documented
behaviour rather than a bug:

- `emit.page_lines` — *"Rules are never lines of their own. Each is attached to
  the innermost emitted object containing it."*
- `emit._glyphs_only` — `if is_rule(region): continue`.

On this page inkdrill emits **0 lines without `--glyphs`**: a booktabs table
draws disjoint rules, so there is no hole lattice, so nothing is a `table` or a
`diagram`. With no emitted object to attach to, the rules are filtered out of
the glyph path and nothing carries them. With `--glyphs` the file holds 3357
glyph lines and **zero `ink.rules`**, and no component on the page is wider
than 11.2 pt.

So Phase 1's "no new inkdrill emit" holds for `inside`/`straddling` but not for
the finding it was written around. The plan's 35 must have come from
`coverage.check` run **inside** inkdrill against raw `sweep` components, which
is a different input from the emitted `lines.json`.

The second guess was right and the rules were already at
`page["ink"]["rules"]`. What was missing was a consumer that read it.

---

## Phase 2 — read inside `diagram` · premise VERIFIED, not built

Measured on 2510.11170v2 page 1, same pipeline.

MathPix returns **one `diagram`, 242.2 × 317.7 pt, `text: ""`** — a schematic
and four plots collapsed to one opaque rectangle. The caption below it is
transcribed perfectly; MathPix reads up to the figure boundary and stops.

Inside that same rectangle inkdrill finds **911 ink components**, and it also
emits **6 `diagram` objects**, four of which are:

```
91.08 x 59.40 pt at (340.6, 363.6)      91.08 x 59.40 pt at (447.3, 363.6)
91.08 x 59.40 pt at (340.6, 432.2)      91.08 x 59.40 pt at (447.3, 432.2)
```

Four plot frames, identical to the pixel, in a 2×2 grid — the plan's
91.1 × 59.4 pt reproduced exactly. 911 objects where the model has 1.

Unlike Phase 1's rules, **nothing is blocked here**: the components and the
frames are both in the emitted `lines.json` already. What remains is pdfdrill
work — rasterize each `diagram` region, run inkdrill on it, and attach the
result as `ink.*` children so the region stays opaque to consumers that want
it opaque.

---

## B1–B4 — the merged tree, its residuals, and the collapsed inspector

`pdfdrill inktree <pdf> --ink <lines.json> [--page N]`
(`src/pdfdrill/ink_tree.py`, `tests/test_ink_tree.py`, 9 tests).

**B1.** Each blob attaches to its **deepest** containing region, as a FLAT list
with a `parent` reference — physical nesting does not survive a round trip, a
parent reference does. Each node carries `parent_type`, so "which of these are
body text" is one field.

**Container regions are KEPT here** and dropped by `inkcoverage`. Same two
inputs, opposite treatment, because they answer different questions: coverage
measures how much of the page MathPix saw (nesting would double-count), the
tree needs the nesting to have a depth at all.

**B2.** Three residual classes, none droppable, and the counts reconcile to the
component total (asserted, not assumed). A **straddler is never given a
parent** — a blob crossing a boundary is evidence the *boundary* is wrong, and
assigning it destroys exactly that evidence. A **tie** carries its candidate
regions rather than being settled by whichever the sort put first.

### Measured

| | 2409.18839 p8 | 2510.11170v2 p1 |
|---|---|---|
| blobs / regions | 3357 / 101 | 3668 / 72 |
| attached | 3355 | 3668 |
| orphan / straddler / tie | 0 / 1 / 1 | 0 / 0 / 0 |
| reconciles | ✓ | ✓ |
| by parent | **text 2736**, simple_cell 386, figure_label 102, footnote 80 | text 2720, **diagram 911**, page_info 37 |

`text 2736` is your number exactly. The single tie is a real one: a blob
contained by both `table_column#6` and `table_row#10`, neither inside the
other — no deepest exists, so none is invented.

**B3** falls out of B1 with nothing extra: `diagram#52` carries **911
children** while remaining one opaque region to any consumer that reads
regions. Orphans are 0 on both pages *because* the rules never leave inkdrill —
when that emit gap closes, the 35 rules should appear here as orphans.

**B4.** `pdfdrill inspect` renders the tree when `inktree` has run: region rows
by default, children only on expand, residuals always visible above them.
Verified on the real page by booting the shipped script against the DOM shim —
**101 region rows, 0 blob rows on open, 92 after expanding one**, with
`straddler 1 / tie 1` shown without a click. The panel is **absent**, not
empty, when no ink was merged: "no ink found" and "inkdrill never ran" must not
render the same.

One defect found by that check and fixed: the residual line counted the
rectangle array, so a tree stored before rects were recorded displayed
`straddler 0` for a page that has one — a zero meaning "unknown", which is the
failure the audit exists to catch. The count now comes from `residual_counts`.

The canvas layer was not needed and was not built.

---

## Phase 3 — table structure from ink · BUILT

`pdfdrill inktables <pdf> --ink <lines.json> [--page N]`
(`src/pdfdrill/ink_tables.py`, `tests/test_ink_tables.py`, 9 tests).

The module is glue and deliberately thin. inkdrill's `simple_cell` lines carry
`cell_row`/`cell_column`/spans on purpose, so they go through the **existing**
`table_structure.cells_from_mathpix` unchanged; the verdicts come from the
**existing** `ink_crosscheck.crosscheck_tables` and the warnings from the
**existing** `table_structure.check`. No third `cells_from_*`, and a test
asserts the reuse rather than trusting it — two readers would make a scoring
difference indistinguishable from a format difference.

The one thing this module must get right alone is the coordinate space: the
docmodel holds MathPix pixels, inkdrill declares points, and comparing them raw
gives IoU 0 for a table both tools found — a units bug wearing the costume of a
finding.

### Connected grid — Infineon p19

inkdrill emits **52 `simple_cell` + 1 `table`**, `ink.holes = 52, rows 13,
columns 4`. The existing reader takes them unchanged:

```
cells_from_mathpix -> 52 cells, 13 rows x 4 cols
column widths pt    45.0 / 42.7 / 99.5 / 278.3
row heights pt      37.8 / 23.8 / 38.0 / 23.9 / 23.9 / 23.9 / 37.8 / 23.8 ...
```

The alternation is the rows whose text wraps to two lines.

The adjudication is more interesting than "disagreement":

```
page 19: 2 model table(s) vs 1 ink table(s); holes [52]
    only in model  6x4 (24 cells)
    same grid 13x4, cell population differs: model 44 vs ink 52   iou 0.996
      slots only the ink has (8): (1,1) (1,3) (2,1) (6,1) (7,1) (8,1) (8,3) (12,1)
```

Both tools say **13×4 over the same rectangle** (IoU 0.996). MathPix emits 44
cells, **all of which have text**; the 8 it omits are exactly the **empty**
slots. inkdrill covers all 52 because a hole is a hole. So the two are
**complementary, not contradictory** — MathPix supplies the text for 44, the
ink supplies the 8 empties, and a LaTeX round trip needs all 52 because an
empty cell is still an `&`.

Printing that as a grid disagreement would read as a defect in one tool, so
`slot_diff` names the slots and the report separates "same grid, different
population" from a real row/column difference.

### Disjoint rules — 2409.18839 p8

```
page 8: 2 model table(s) vs 0 ink table(s); no hole lattice
    only in model  4x2 (8 cells)   — no hole lattice on this page
    only in model  12x2 (24 cells) — no hole lattice on this page
```

`no_lattice` says inkdrill was **silent**, which is not the same as inkdrill
disagreeing. The discriminator is one number and it travels into the report:
52 holes versus 0 is not a marginal call. Recovering these cells needs
collinear rule grouping, which is blocked on the same emit gap as Phase 1 —
the rules never leave inkdrill.

---

## The inspector surface, after three UI fixes

**1. The panel opens on the page being viewed.** It opened on the first page
that carried ink, so a reader on page 11 was shown page 8's 101 regions and had
to touch the selector to see the 5 that belong to the page in front of them.
`gotoPage` is now wrapped, because clicking an element or jumping to a page
moves `curPage` without the selector ever firing.

**2. A collapsed row carries a count and a SHAPE, not extents.**
`2×4 pt, 4×7 pt, 4×7 pt` says nothing folded or unfolded. inkdrill already
emits `holes` and `area` per component, so the summary is a projection of data
we have:

```
▸ figure_label  61 blobs, median 5×5.2 pt   figure_label#108
▸ diagram  11551 blobs, median 0.4×0.7 pt   diagram#0
```

Expanding gives one summary block, not one row per blob:
`11551 blobs · median 0.4×0.7 pt · largest 132.7×532.6 pt · 0 holes · 1439395 px ink`.

Because the extents are no longer rendered, they are no longer **shipped**: the
per-blob rectangle arrays left the payload and the 4-page inspector went from
**2380 KB to 1067 KB**. Individual extents belong to a third level, which
nothing asks for yet; when it is wanted they come back behind a fetch rather
than in every page load.

**3. A table region renders its grid.** `inktables` had already resolved 13×4
with the column widths, and the panel was showing anonymous rectangles.

```
table  0 blobs · grid 13×4   table#40
    grid 13 rows × 4 cols  (52 holes)
    column widths pt  45.0 / 42.7 / 99.5 / 278.3
    row heights pt    37.8 / 23.8 / 38.0 / 23.9 / 23.9 / 23.9 / 37.8 / 23.8 ...
```

The table shows `0 blobs` because its glyphs attach to the deeper `simple_cell`
regions — the deepest-parent rule working as intended, and the grid is what
that row is for.

### The standing test — 2409.18839 page 11

A document about document extraction, containing pictures of documents. Nothing
else in the corpus puts this much under one region, so it stays the collapse
test.

| page | blobs | rows shown | blob rows on open |
|---|---|---|---|
| 8 | 3357 | 101 | 0 |
| 9 | 2337 | 125 | 0 |
| **11** | **11708** | **5** | **0** |

No filter, no canvas, no virtualization — the default depth is 1.

Two defects found while measuring this: running `inktree --page 8` then
`--page 11` **replaced** the stored tree instead of merging, so a per-page
workflow silently discarded every earlier page; and the grid was keyed to a
synthetic `table#i` that matched no region, so it never reached the row it
belonged to (now matched by geometry, IoU ≥ 0.3).

---

## Phase 4 — rule weights · BUILT and WORKING ON REAL PAPERS

`src/pdfdrill/ink_rules.py`, `tests/test_ink_rules.py` (9 tests), wired into
`inktables` scoped to a table.

**Correction first.** I previously reported `ink.rules` empty everywhere. That
was measured on p8, p9, h1 and inf19 and over-generalised: **2409.18839 page 11
carries 45 real rules**, on 5 `diagram`, 7 `glyph` and 2 `table` carriers. Rules
ARE emitted — when they fall inside an emitted object.

**The booktabs case is NOT blocked.** I reported it was, having run a compiled
booktabs fixture, seen `lines 0`, and not opened the page record — which held
all four rules. With `page["ink"]["rules"]` read, and the MODEL's table
rectangle claiming the rules inside it (`ink_tables.attach_rules` — a booktabs
page emits no ink table, so only pdfdrill holds both halves), Phase 4 runs on
real papers.

### Verified against ground truth — 2409.18839 page 9

Both tables, from ink alone:

```
toprule 1.080 pt, cmidrule 0.540, cmidrule 0.540, midrule 0.720, bottomrule 1.080
```

pdfplumber's vector rules for the same table: `\toprule` 0.9017 pt over
346.4 pt, **two rules of 0.3006 pt spanning only 95.6 pt** (`\cmidrule`), a
full-width `\midrule` 0.5006, `\bottomrule` 0.9017. **Five of five correct.**

The `\cmidrule` distinction came out of this comparison: the first version
called all three interior rules `\midrule`, which draws a line across the
whole table. The discriminator is the LENGTH, and it was sitting in the record
unused — a rule spanning under 90% of the table's widest rule is partial.
Measured spans are 0.28 / 0.30 / 0.24 against 1.00 for every full-width rule,
so nothing sits near the boundary.

### How noisy the measurement actually is

On the compiled fixture, inkdrill's `width_pt` against pdflatex's truth:

| rule | true | measured | |
|---|---|---|---|
| `\toprule` | 0.7970 | 0.9000 | +12.9% |
| `\midrule` | 0.4980 | 0.5400 | +8.4% |
| `\midrule` | 0.4980 | **0.7200** | **+44.6%** |
| `\bottomrule` | 0.7970 | 1.0800 | +35.5% |

The two IDENTICAL `\midrule`s measured **33% apart**. The classification is
still right because only the ORDER is used — min(heavy) 0.90 > max(light) 0.72
— but the margin is **0.18 pt, exactly one pixel at 400 dpi**, against the
plan's claimed 2 px. On this fixture the separation is half what the plan
states.

### The classifier

inkdrill emits `width_pt` and never a name, because the call needs table
context. The absolute width runs ~12% high (rasteriser coverage) and the ratio
is unstable under quantisation (1.50 / 1.33 / 1.67 / 1.40 / 1.67 against a
nominal 1.60), so **the ordering decides, never the value**. A test inflates
every width by 12% and asserts not one name moves.

Ground truth, a compiled booktabs table read with pdfplumber:

```
y 125.20   0.7970 pt   class 1  ->  \toprule
y 142.31   0.4980 pt   class 0  ->  \midrule
y 171.22   0.4980 pt   class 0  ->  \midrule
y 188.33   0.7970 pt   class 1  ->  \bottomrule      ratio 1.60
```

Position **confirms** the weight rather than being overruled by it: a heavy
interior rule is a group separator, and naming it `toprule` would move it to
the top of the reconstructed table.

Rule 5 throughout — where the evidence does not separate, nothing is named and
the reason travels. Over the 45 real rules on page 11, **33 are unnamed**:

| reason | n |
|---|---|
| one weight class | 20 |
| vertical rule (a `\|` separator, not booktabs) | 5 |
| too few rules to rank | 5 |
| heaviest class but not at an edge | 3 |

A table ruled entirely with `\hline` has one weight class and therefore **no
weight evidence at all**; naming its first rule `toprule` on position alone
would be a guess wearing a measurement's clothes.

**Scoping matters and is why this is wired into `inktables`, not run per
carrier.** Applied to a diagram's rules the same ranking names UI bars inside a
screenshot `toprule` — mechanically consistent, and about a thing that is not a
table. Table-scoped, page 11's two table carriers report honestly: `1 measured,
none named (vertical rule)` and `2 measured, none named (too few; vertical)`.

**Not done:** the LaTeX round trip. `svg.py` still injects `booktabs` on
sight of `\toprule` without knowing which rule was drawn; nothing consumes
`rules[].kind` yet.

## Phase 5 — not started

3 table structure from ink · 4 rule weights · 5 the two-layer `inspect`
surface. Phase 5 gates the visibility of 1–4 and has no inkdrill dependency.

Note for Phase 4: on the pages measured here `ink.rules` was empty everywhere
(`rules=0` on all 6 diagram objects, and no rules at all on the booktabs page).
Phase 4 depends on the same emit gap Phase 1 hit.
