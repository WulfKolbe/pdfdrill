# HANDOVER

Read this first. The 18 working rules, each learned by a defect, and the
non-obvious environment facts (LgEval pin, preflight, dictionaries) moved to
**`docs/HANDOVER-RULES.md`** — unchanged, still canonical, just no longer in
the way of the state of play.

## Working surface

**PDFDRILL** — quality control of PDF→LaTeX OCR. `src/pdfdrill/` (flat CLI,
`.drill/` sidecar), `src/docmodel/` (typed `Document`), `src/docops/`
(mutators + projectors). **133 commands** in `.claude/skills/pdfdrill/commands.yaml`,
matching `cli.HANDLERS` exactly. **2,104 tests** (`PYTHONDONTWRITEBYTECODE=1
python3 -m pytest tests/ -q -p no:cacheprovider` — the env var is not optional).

Branch `eqblobs-and-gzip-tex`; `main`/`master` are behind it. Corpus is 49 arXiv
documents in `~/pdfdrill-library`, rostered in `P13-arxiv-reports.txt` (which
lists 50 — see open item 1). Analysis output is `out/NNN.txt`, one per task.

## Measured constants — each with the population it came from

Quoting one of these without its population produces a different number that
looks like the same one.

| Constant | Value | Population |
|---|---|---|
| SLT distance-zero | 497 (37.4%) | 1,328 comparable pairs, 20 docs with BOTH e-print and MathPix; median 2 |
| Demoted rows | 51 (49 EQ-only) | 49-doc corpus, 10 docs; `0902.0431` alone holds 31 |
| Ink noise floor | 6 | p95 of 208 expressions through two rasterizers (consumer's `noisefloor.py`) |
| Render≠scan at high confidence | 725 (21.4%) | 3,392 equations with ink≥6, confidence≥0.9, not demoted |
| Confidence flag | 19 (0.4%) | 4,338 of 4,342 equations carry a value; threshold 0.1; median exactly 1.000, p05 0.515 |
| Shading detector | ≥0.50 mid-grey | shaded crops 0.884–0.942, all others ≤0.225; 3 of 4,342 crops, all `1211.3375` |
| trailing_punct A/B parity | 2 differing of 10,434 cells | `bh2` PRE vs POST, last two report columns; PRE reconstructed from `latex_prepunct` after the original build was deleted and it reproduced the first run cell for cell |
| Sign-filter precision | 7 of 11 | unshaded, both symbol deltas negative, symbol half ≥15 → 7 content / 2 artifact / 2 typography |

`confidence_rate` is **not** a usable flag: it never drops below 0.9306
corpus-wide, and `EQ0516` scores 0.9921 while being 60% wrong.

The sign filter is the useful instrument: it needs no author LaTeX, no gold and
no e-print, so it reaches the ~99% of documents where no comparison is possible.

## Open items

1. **Roster.** `1511.08771` is listed in `P13-arxiv-reports.txt` (50 entries)
   but excluded at use by every consumer (corpus runs 49). Leave it listed and
   filter, or drop the line so the roster means the operative corpus. **Both
   sessions read this file — the user's call, unilateral edit diverges us.**
2. **Temp-dir leak, ongoing.** 1,763 `tempfile.mkdtemp` directories accumulated
   in ~5 days; whoever calls it never removes them. Swept once (075); it will
   refill.
3. **Silent glyph loss in standalone renders.** xelatex drops U+21D2 and CJK/
   Devanagari with a *warning*, so the compile fixpoint's `^! ` regex never
   demotes the row. 5 equations corpus-wide, 4 of them junk readings; needs a
   fallback font or a pre-compile map to `\Rightarrow`.
4. **117 uninspected rows** of the sign filter (128 both-negative, 11 inspected).
5. **Equation-number pairing** on `1306.1660` p6: numbers do not increase with
   y, `(63)`/`(69)` absent from the model. Nearest-y pairing is unreliable there.
6. **Doc fixes from out/076:** CLAUDE.md says 125 commands (133), HANDOVER-RULES
   says 1745 tests (2,104), four layer docs point at modules that moved to
   `src/pdfdrill/nodes/`.
7. **Consumer's findings file is one regeneration stale** — the 42 rows 058
   recovered are not in it. Their cadence, not ours.

## Known failure classes — what actually costs time here

- **An instrument correct on its sample and wrong on the corpus.** Three
  identifier regexes in two days, each verified against a sample that lacked
  the disambiguating case (`~\eqnum{}`, `\allowbreak{}`). Check the residue
  bucket: 93 rows landing in "other" is a broken pattern announcing itself.
- **A comparison that structurally cannot show a difference, returning the
  answer you hoped for.** `parse_latex_slt` collapsed `\begin{aligned}` to one
  `UNRESOLVED` node, so unrelated equations scored distance 0 — a retracted
  floor and 44.5% of a result. Same family: rebuilding the trailing_punct A/B
  pair by re-projecting would have produced two IDENTICAL builds, because
  `latex_prepunct` lives in the docmodel and never reaches the tiddlers
  `reporttex` reads; the diff would have reported 0 differing cells and looked
  like a pass. The consumer could not have told that apart from a real one.
  Reconstruct from the field that actually holds the old state, not from the
  pipeline that dropped it.
- **Masked success.** A warning is not an error; a summary counter is not the
  artifact. `reporttex` reports 5 demoted while the .tex files show 51 — the 46
  generation-time rejections no compile counter can see.
- **Population mismatch dressed as agreement.** Two subtractions of 21 made
  93→72→51 arithmetically consistent for unrelated reasons. Reconcile term by
  term, never by landing on the same total.
- **Provenance confusion.** `<stem>.tex.zip` is MathPix's own reconstruction,
  named by the `image_id`; comparing against it compares MathPix with itself.
  Guarded now (`author_source.py`), but the e-print may be a bare gzipped
  `.tex`, not a tar.
- **Attributing to the data what the tooling did.** I recorded that MathPix
  dropped three `⇒`; the LaTeX had them and our renderer could not set the
  glyph. A picture shows what was drawn, not what was read.
- **Declaring a scope and not enforcing it.** 075 deleted 36 directories 074
  had ruled out of scope, because the cutoff constant read 2025 not 2026 and
  the counter that would have caught it printed 0 and went unread.

Three of these — the residue bucket reading 0, the `(page,row)` key, the
skipped-count reading 0 — are one failure: **trusting a check's summary over
its data**. The check ran, the aggregate agreed with the expectation, and
nobody looked at the rows. A zero in a class you have just declared non-empty
is not a result, it is a symptom.
