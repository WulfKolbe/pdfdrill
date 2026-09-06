# HANDOVER

Current state, current blocker, next task. Nothing else — the per-task
evidence lives in `out/NNN.txt` and `~/pdfdrill-library/out/NNN/`, and the
rules learned by defect are in **`docs/HANDOVER-RULES.md`**.

Last updated 2026-09-06, after 634.

---

## Where the 21 published documents stand

**20 of 21 are published and current on the NEW surface.** Site commit
`b8b71e1`. Verify with:

    python3 tools/publishcheck.py --list ~/pdfdrill-library/out/documents.json

It reads 20 identical / 1 not published (penev_A) today. Run it before
believing anything below.

**The surface changed in 634** (spec `docs/superpowers/specs/2026-09-06-
evidence-residuals-design.md`, evidence `out/634.txt`). Per document the
site carries five files:

    evidence-equation.pdf   every display equation, six columns, unbounded
    evidence-formula.pdf    every inline formula; Page/Conf./Image are the
                            HOST LINE's, and the file says so
    evidence-table.pdf      every table, region rendered from the PDF
    evidence-image.pdf      every image region
    residuals.pdf           the action list: Corrected, Unresolved, Flagged,
                            Low confidence, Doubted — worst first, 10 pages

Evidence is for lookup, residuals for reading. The site copies are
Ghostscript /ebook derivatives kept under `<doc>/published/` (the originals
total 947 MB; the site cap is ~1 GB); `publishcheck` compares against
`published/` when it exists. `report.pdf` is retired from the site.

    pdfdrill evidence <pdf> --all-kinds --pdf
    pdfdrill residuals <pdf> --pdf
    pdfdrill publishready <pdf>

`report`, `breport`, `inkreport` are aliases; `reporttex` is superseded for
reading and kept as the ink chain's measure build. The reports read the
Document (`src/pdfdrill/reports/from_document.py`), never tiddlers, and take
identifiers from `tiddlywiki.math_titles` / `region_titles`.

Residuals on those 20 are **measured on display equations only**. Inline
formula rows are not measured; the residuals header states when the
equations were measured and against which model.

### The one still out

| document | gate | why |
|---|---|---|
| penev_A | ink, timestamp, glyphs | no `report.ink.json` (the `.REFUSED` quarantine, 603); one dropped glyph in evidence-formula.pdf |

The old stamp gate (checksum of the measure build) is gone: `publishready`
now asks whether the ink's recorded model sha/mtime match the model on
disk, and whether every equation row shown carries an ink row (straddlers
excepted). A layout change never invalidates a measurement again.

---

## The measurement chain, as it now works

    reporttex --cellrect   phase 1 (the MEASURE build, still report.pdf):
                           full listing, legend off, bullets off. Emits
                           pdfdrill-rows.json.
    inkdrill compare       per page, 300 vs 600 dpi
    inkmeasure.measure     claims each lattice row by the rect that CONTAINS it
    inkconvert             pairs by identifier; report.ink.json carries
                           measured_against {built_at, model_sha256, model_mtime}
    residuals              reads the ink as it stands; --measure runs the
                           chain above first
    publishready           artefacts, glyphs (+ remaining xelatex errors),
                           ink, timestamp, coverage

Two invariants worth keeping:

- **`zeroScan` must be 0** on the measure build (it is, 20 of 20 measured).
- **The ink's `model_sha256` equals the model's.** That is the timestamp
  gate; a rebuilt model is the only thing that invalidates a measurement.

---

## Current blocker

**Nothing is blocking the 20.**

1. **penev_A** — re-measure it (`residuals --measure --pdf`); that is the
   whole fix. Its one dropped glyph in evidence-formula.pdf is the second.

---

## Next task

Agreed next steps, in order:

- **010 — Reference stub at first citation** (running as of 2026-09-06):
  a Reference is created at a citekey's first Citation and filled by
  bibliography/bibsource/bibfetch. Report `tasks/010.report.md`.
- **Inline formula measurement**, and with it moving the measure build
  from `report.pdf` to `evidence-equation.pdf`. 37,624 formula rows across
  the 21 have never been measured.
- **629, measured and unapplied.** A depth-walk environment stripper clears
  134 of 134 tab-mark refusals; permitting `$` inside `\text{}` clears 56.
- **Retire the aliases** once nothing scripts against `report`/`breport`/
  `inkreport`.
- **Corrected pairs show a dash in the Scan column** although the crop
  exists (pre-existing; `findings_tex.scan()`).

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
