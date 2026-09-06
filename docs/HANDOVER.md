# HANDOVER

Current state, current blocker, next task. Nothing else — the per-task
evidence lives in `out/NNN.txt` and `~/pdfdrill-library/out/NNN/`, and the
rules learned by defect are in **`docs/HANDOVER-RULES.md`**.

Last updated 2026-09-06, after 633.

---

## Where the 21 published documents stand

**17 of 21 are published and current.** Site commit `383ae31`. Verify with:

    python3 tools/publishcheck.py --list ~/pdfdrill-library/out/documents.json

Exit 0 only when every document on the site is the build on disk. It reads
17 identical / 4 stale today. Run it before believing anything below.

Residuals on those 17 are **measured on display equations only**. Inline
formula rows are not measured — the selection for them is not built. The
index says so.

### The four still stale

| document | gate | why |
|---|---|---|
| 0902.0431 | stamp | 6 of 13 shown rows straddle a page break (46% > 25%) |
| gilmore-lie-groups | stamp | 5 of 15 (33% > 25%) |
| kohlhase-omdoc | residuals | p90 component ratio 3.92, over the 3.0 max |
| penev_A | ink, stamp, artefacts | no `report.ink.json`; `.REFUSED` quarantined |

The first two are a **threshold question, not a defect**: banding leaves a
small denominator, so a handful of unmeasurable rows is a large share.
`UNMEASURED_MAX` (0.25) and `UNMEASURED_MIN` (4) are in `report_tex.py` and
both are printed on the report page.

---

## The measurement chain, as it now works

    reporttex --cellrect   phase 1: full listing, unbounded, legend off,
                           bullets off. Emits pdfdrill-rows.json — one rect
                           per row, in bp, y up.
    inkdrill compare       per page, 300 vs 600 dpi
    inkmeasure.measure     claims each lattice row by the rect that CONTAINS
                           it. No header rule, no legend rule — an unclaimed
                           row is dropped because nothing claims it.
    inkconvert             pairs by the identifier the TSV now carries
    reporttex              phase 2: findings shape, legend on, bullets on
    publishready           five gates

Two invariants worth keeping:

- **`zeroScan` must be 0.** It counts data rows whose Scan cell measured
  empty. It is 0 on 21 of 21 and it is the column that would have caught the
  625 defect in a day instead of three.
- **`ma_ok` must be true.** The ink's `measured_against.sha256` equals the
  measure build's. 20 of 21 (penev_A has no ink).

---

## Current blocker

**Nothing is blocking the 17.** They are published and current.

For the remaining four, in the order I would take them:

1. **penev_A** — one document, no ink. Its `report.ink.json` was renamed
   `.REFUSED` against a build that no longer exists. Re-measure it; that is
   the whole fix.
2. **0902.0431 and gilmore** — decide whether `UNMEASURED_MAX` should scale
   with the denominator, or whether these two should publish with the count
   stated. Both are defensible; neither is a code defect.
3. **kohlhase** — p90 3.92 against a 3.0 max, on 1 bullet. Look at whether a
   ratio over one row means anything before changing the constant.

---

## Next task

None outstanding. The queue below is real but unstarted, and none of it is on
the critical path to publishing:

- **Inline formula measurement.** 37,624 formula rows across the 21 have
  never been measured on anything. `equations_table()` returns only the
  "Display equations" table; the manifest names the formulas table with
  identifiers and they resolve on 19 of 21 (fong-spivak-invitation and
  -seven-sketches miss ~96%, undiagnosed). Scale: +942 pages, roughly
  +2 hours on top of the equations.
- **629, measured and unapplied.** A depth-walk environment stripper clears
  134 of 134 tab-mark refusals; permitting `$` inside `\text{}` clears 56.
  Both were held while 627 ran and were never applied.
- **DIA rows take the wrong field.** `rows_for` reads `latex` before
  `latex_code`, and for a Diagram `latex` holds the TiddlyWiki `<$image>`
  widget, so the real source is never rendered (`out/616.txt`).
- **inkdrill's R column** was the 625 defect and is fixed on our side; the
  histogram work in `out/623.txt` is the evidence if it recurs.

---

## Two things that cost the most time here

**Report first, build second.** Every defect that cost a full run came from
specifying against data nobody had read. The environment map in 628 fired on
zero rows of 660,504. Three predictions about the R column were all wrong;
the cause was a `\\` in `crop_cell`.

**A number computed across build generations is not a measurement.** 575 put
a build stamp in every model for this reason. The same class recurred as a
manifest describing a build that no longer existed — hence
`measured_against.sha256` on `pdfdrill-rows.json`, and `publishcheck` for the
site.
