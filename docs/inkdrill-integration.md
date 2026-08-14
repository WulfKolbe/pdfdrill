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

## Phase 3–5 — not started

3 table structure from ink · 4 rule weights · 5 the two-layer `inspect`
surface. Phase 5 gates the visibility of 1–4 and has no inkdrill dependency.

Note for Phase 4: on the pages measured here `ink.rules` was empty everywhere
(`rules=0` on all 6 diagram objects, and no rules at all on the booktabs page).
Phase 4 depends on the same emit gap Phase 1 hit.
