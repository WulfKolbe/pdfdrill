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

## Phase 1 — coverage audit · BUILT, and it found a blocker

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

47.78% inside reproduces the plan's 47.4%. **The missed count does not: the
plan expects 35, and the pipeline can produce at most 2.**

### The blocker — the 35 rules never leave inkdrill

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

**What would unblock it (inkdrill side, one of):** emit a `rule` line when a
rule belongs to no emitted object; or attach `ink.rules[]` to the page record
in that case. Either makes the rules addressable without changing the
consumer — `ink_coverage.ink_boxes` takes a `kinds` argument and would need
one more name.

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

## Phase 4–5 — not started

3 table structure from ink · 4 rule weights · 5 the two-layer `inspect`
surface. Phase 5 gates the visibility of 1–4 and has no inkdrill dependency.

Note for Phase 4: on the pages measured here `ink.rules` was empty everywhere
(`rules=0` on all 6 diagram objects, and no rules at all on the booktabs page).
Phase 4 depends on the same emit gap Phase 1 hit.
