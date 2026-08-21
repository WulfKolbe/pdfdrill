# Handover — state of play

Written for a session with no history here (any provider). Facts are measured,
with the command that measured them. If a path has moved, trust the repository
over this file.

Last verified 2026-08-16: repo @ `555d656` on `eqblobs-and-gzip-tex`, pushed to
`origin` (github.com/WulfKolbe/pdfdrill — verified with `git ls-remote`; `main`
and `master` sit at `1812e3f`). Working tree clean.

    PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider
    -> 2048 passed, 0 failed, 0 skipped (measured 2026-08-16; the 8 old
       test_resume_sh failures were tests pinning the pre-edit resume.sh
       contract — rewritten to pin the user's hardcoded one-liner)

**A skipped test is not a pass.** The old five-session skip story is in §4.

**2026-08-16 session note (damage control + reset prep):** the user reported
work landing under `/tmp/claude-1000/-home-wkolbe-MX-PDFDRILL` instead of
GitHub. Inspected BEFORE deleting: those dirs held NO git repo and NO commits
(only empty session scratchpads + one task log); every branch was already on
GitHub at the local HEAD. The /tmp dirs and `/tmp/drillui-session.log` were
then removed. Lesson kept as a rule: **verify `git ls-remote origin` after any
push claim; never let commits exist only in a scratch worktree.** CLAUDE.md was
compacted the same day (was 3271 lines loaded into every session ≈ the user's
"75% of input tokens"); the full historical text is preserved verbatim at
`docs/CLAUDE-FULL.md`.

---

## 1. Working rules that were learned by defect

Each of these cost real time or real data in this project.

1. **Measure the premise before building on it.** The mathgold gold set moved
   from 87 equations to 21,230 (different prop) on measurement; T1 had no
   producer at all.
2. **State the population beside every number.** 21,240 vs 59 for "the mathgold
   population" were both right and measured different things (structure vs
   structure+placement). See `docs/mathgold-population.txt`.
3. **A guarantee in a docstring is not a guarantee.** Run a branch-mutation
   sweep (each `if` forced True/False); outcomes: killed / survived /
   incompetent / equivalent.
4. **Run mutation sweeps with `PYTHONDONTWRITEBYTECODE=1`.** A same-length `cp`
   restore matches the stale `.pyc` by size AND mtime; a test failed against
   correct source and a working fix was nearly reverted. `git diff --stat`
   after every write, too.
5. **Never return a plausible default for an unknown.** Raise or return an
   explicit unresolved marker (`mathgold.slt.Unresolved`) — never a sentinel
   string (`"UNKNOWN" == "UNKNOWN"`). **Re-learned the hard way 2026-08-21:**
   `parse_latex_slt` collapses `\begin{aligned}` to ONE node labelled
   `UNRESOLVED_aligned`, so two unrelated multi-line equations produced
   byte-identical signatures and `slt_edit_distance` returned 0 without
   comparing contents. 662 of 1,488 corpus rows (44.5%) called "structurally
   identical" were this, and it moved a measured noise floor from 7 to 22 —
   a number handed to another session that would have hidden real findings.
   `crossref.formula_signature` now returns None for a degenerate signature;
   a signature that cannot distinguish two expressions must never reach a
   comparison. Writing the rule down does not inoculate you against it.
6. **Presence is not adequacy.** Four bugs shaped as "a fact/file/output/twin
   exists"; each needed a detector that reads the actual store.
7. **Verify the written file, not the object in memory.** Two "in-memory right,
   file wrong" defects passed 1745 tests. Persisting commands should assert via
   `tests/test_model_write_roundtrip.py::roundtrip` (a meta-test pins how many
   do).
8. **Absence has to be read out of the file, not inferred from one empty key.**
   (Commit `1892313`: "lines 0" was reported as "rules never leave inkdrill"
   while the just-generated file held all four rules under
   `page["ink"]["rules"]`.)
9. **Do not ask what a command can answer.** Reversible → do it and record it.
   Preference that changes what gets built → ask.
10. **When deciding without the user:** take the reversible option and record
    the decision, the rejected alternative, and what would change your mind.
11. **A masked success reads exactly like a masked failure.** A summary
    regex that missed singular 'Output written (1 page)' reported a good
    compile as '0 pages' (2026-08-19); the inkdrill session was bitten twice
    by exit-code-masking pipes. Any success/failure summarizer must be tested
    on BOTH a real success and a real failure — a parser that can only see
    one of them sees neither.
12. **An unexplained delta is a FINDING, not an observation.** A generator
    change grew the corpus 941 -> 1,080 pages (+15%) with identical equation
    counts; both sessions filed it as "benign, indices shifted" instead of
    asking why 15% and not 1%. It was a real defect (a `\penalty0` at the
    start of a `p{}` cell is TAKEN, giving every backslash-initial cell an
    empty first line). Ask the magnitude question: a number nobody can derive
    is a bug nobody has found yet.
13. **Verify layout cost, not only correctness.** `f7d5568` was accepted on
    "equations render + probe passes" and shipped a +38% page regression.
    Generator acceptance now measures page count before/after on a fixed
    document alongside the column probe. A cost you never measured is a cost
    your consumer measures for you.

14. **Re-measure a symptom against the CURRENT artifact before diagnosing
    it.** A "117 rows vs 23 equations" symptom was diagnosed by both sessions
    — mechanism proposed, code read, fix designed — before anyone re-ran it;
    the number came from a build three regenerations old and the symptom no
    longer existed (the same document now reads 19 rows vs 23). In a pipeline
    that regenerates, an observation is evidence about the artifact it was
    taken from, not about today's. Diagnosing stale evidence produces
    confident, wrong fixes.
15. **A prediction about CONTENT is not a prediction about PIXELS.** I
    predicted "0 differing Rendered cells" from the fact that the emitted
    LaTeX is identical for a migrated row. Falsified: 34 differed, because 6
    rows had reflowed one page earlier and therefore rasterised at a
    different sub-pixel offset. The content claim was right and the cell
    claim was wrong, and they are not the same claim. State which layer a
    prediction is about, or it cannot be scored.
16. **An unchanged input column is a free control — keep one.** The consumer's
    diff showed 6 SCAN cells differing, and the scan column is an untouched
    JPEG that no migration of mine can reach. That is what separated "the ink
    changed" from "the row moved"; without it both hypotheses fit the 34
    Rendered cells equally. Nobody designed it as a control — it was there
    because the report happens to carry the source beside the derivative.

---

## 2. Environment facts that are not obvious

**Preflight.** Build/extract commands are blocked until `pdfdrill preflight
--ack <TOKEN>`, per working directory. Automation sets `PDFDRILL_NO_PREFLIGHT=1`.

**LgEval — invoked, never vendored.**

    repo    gitlab.com/dprl/lgeval        (github.com/DPRL/LgEval is 404)
    commit  9831a3c                       (HEAD c94f6dd imports lgeval.msg_debug,
                                           which the repository does not ship)
    path    ~/.local/share/lgeval         (must be importable AS `lgeval`)
    invoke  source tools/lgeval_env.sh; lgeval_score out.lg gold.lg

The github.com/michaelyin mirror is Python 2 and will not run.

**Spell / hyphenation dictionaries.** `/usr/share/hunspell` is English only.
German `de_DE.aff/.dic` + `hyph_de_DE.dic` exist ONLY inside the flatpak
KDE runtime. `spylls` is NOT installed. Measured: `dictionary_status()` →
de:'dic' en:'enchant'; the `dic` floor has no affix/compound rules, so German
joins via the soft heuristic (`DehyphResult.reason` says which).
`HUNSPELL_DICT_DIR` → flatpak path + `pip install spylls` would light up the
affix path; neither is done.

**`resume.sh`** is now the user's own one-liner: it resumes the HARDCODED
session id `ae99387a-8fcf-4b96-b9d9-5dc00cc6f8da` with
`--dangerously-skip-permissions`. This pin is deliberate (user edit,
2026-08-16, after a `--continue` loop trapped them). When that session dies,
the id must be edited by hand — `claude --resume` (no id) lists sessions to
pick from. `.last-session-id` is gitignored.

---

## 3. Open work

### T4 deliverable 3 — the floor (unstarted; the unblocking item)

Deliverables 1-2 done: `src/mathgold/slt.py` parses author LaTeX into a Symbol
Layout Tree and round-trips `.lg` (3000 uniform samples, seed 0: 99.8% parsed,
lossless round-trip; 64% single-expression).

The floor takes pdfminer characters+positions, applies the crudest relation
rules (baseline overlap ⇒ Right; raised+smaller ⇒ Sup), emits `.lg`, scores
against gold with LgEval. **Population is settled: 59 equations over 2
documents** (kolbe2018hubbard 54, 2510.11170v2 5) — `provenance == "tex"` AND
region+page. The 21,230 source-built equations have zero geometry and cannot
feed a positional floor. Report as anecdotal at n=59; report BOTH rows
(single-expression subset, full set with environments as `Unresolved`); never
split `align` into rows to enlarge the denominator.

### T2 — table rule weights: DONE through commit `1812e3f`

The mechanism landed across `4499468..1812e3f` (inkdrill phases 1–4):
- `page["ink"]["rules"]` contract gap closed (`ink_coverage.page_rules`,
  `include_rules=True`, `ink_tables.attach_rules` — a MathPix table rectangle
  claims ownerless booktabs rules). Phase 1 reproduces the plan exactly
  (2409.18839 p8: 35 missed components, 33 of them rules).
- Ranking is **by ORDER, never absolute width** (quantisation error does not
  shrink with dpi: +24.2/+5.4/+12.9/+5.4 % at 400/600/800/1200). Inflation
  guard +25%. `rank_rules` takes the file's declared `render_dpi`, reports
  margin_pt AND margin_px, warns under 2 px; if classification matters, render
  rules at **800 dpi** even when everything else runs 400.
- Validated on real paper 2409.18839 p9 at 400 and 800 dpi.
Tests: `tests/test_ink_rules.py` (15). Remaining: nothing blocking; a
hand-made `ink.rules[]` is no longer needed (inkdrill emits them).
Gotcha kept: `table_lines` takes a region **id**, not a `Region` — pass
`regs[0].id`.

### bh2 (2nd Heim book) report + the vision/inkdrill loop (2026-08-17)

`~/pdfdrill-library/bh2/`: MathPix gave md + tex.zip + lines.json (400pp,
12,266 lines). `tools/make_report_tex.py` generates the LaTeX formula report
(report.tex/pdf: A3 landscape, boxed, pixel-exact scan crops via `--px2mm`,
columns Identifier|Page|Source|Rendered|Image). **The tex.zip's `images/` are
exactly the regions MathPix could NOT OCR** — for bh2 exactly ONE (p400,
1078×1019px), consistent across zip/md/model (`bh2_DIA_0001`, empty
latex_code). `--texzip <dir>` feeds them into the report's "Unrecovered image
regions" section locally (no CDN). The reconstruction route for such regions
is **`pdfdrill vision`** (the GPT-4o large-prompt command; keyless → delegates
to the running agent), and an LLM's returned LaTeX can now be **verified
against the real ink with inkdrill** (compile the LaTeX, compare ink) — the
loop is noted but not yet automated.

### BH3FR is the FORMULA REGISTER — the cross-book identity anchor (2026-08-18)

`~/pdfdrill-library/BH3FR/` (149pp, 324 numbered equations + 217 inline
formulas, MathPix'd) is a REGISTER: per the user, every formula of BH1org and
bh2 should be findable in it, and it is to serve as the SOURCE OF SYNONYMS AND
ACRONYMS for all the Heim books. That makes it the natural anchor for
cross-book formula identity. BUILT as P10 `pdfdrill crossref` (2026-08-18):
ONE index over (bibkey, kind, id, signature, evidence); formula signatures are
the SLT .lg form (mathgold.slt — canonicalizes latex spelling), opaque to the
index; ranking = exact match else line-Jaccard. Store
~/pdfdrill-library/crossref.json holds 13,433 signatures (4 books, 99.86%
parse rate). MEASURED: 70% of bh2's and 62% of BH1org's display equations
resolve into the register (228/136 exact); the unmatched remainder is the OCR-
divergence QC list (crossref-map-bh2-BH3FR.txt). Synonym/acronym extraction
FROM the register is the open follow-up.

### P13 corpus — 50 arXiv docs on MathPix geometry (2026-08-18, complete)

All 50 P13 documents (list: ~/pdfdrill-library/P13-final-reports.txt) hold
genuine MathPix lines.json (paid batch, 24 min, 0 API failures; old
pdfminer/tesseract geometry preserved as *.lines.pdfminer.bak.json), rebuilt
models (model --force; the mathpix route), and content-verified report.pdf
files with pixel-exact equation crops — the inkdrill input set. Outlier
1511.08771 (379K objects, 91,450 inline formulas, 13,754 unrecovered regions)
needed its own long-cap pipeline; 809-page report, 1 residual error.

Two defects this batch taught, now fixed with tests: (1) MUTATING commands
(eqnums) lack the stale-guard and re-save a stale model with a fresh mtime —
batches must run `model --force` first; the general stale-guard for mutating
commands is an OPEN follow-up. (2) A batch freshness check on MTIMES called
the broken outputs fresh — 29 impostors; verification must read CONTENT
(cdn equations in the model + crops on disk). Rule 6 applies to batches.

### bh2 defect roll-up — two instruments, DISTINCT defect classes (2026-08-19)

Keep these separate in any roll-up; conflating them hides the fix route:
- **Will not compile alone** (P14 `standalone`, this session): bh2_EQ0147
  (stray \end{itemize}), bh2_EQ0167 (\left/\right nesting),
  BH1org_OCR_EQ0021 (bad math environment delimiter) — malformed LaTeX;
  fix = re-OCR/escalate the region. Corpus renders: bh2 340/342,
  BH1org 238/239, BH3FR 323/323 (the register compiles CLEAN alone),
  WDorg4 78/78 — PNGs in <blob_dir>/standalone/.
- **No conversion at all** (inkdrill compare, peer session): bh2_EQ0082,
  bh2_EQ0123 — MathPix produced no LaTeX; fix = vision route.
- **Wrong conversion** (inkdrill compare, peer session): bh2_EQ0105,
  bh2_EQ0131, bh2_EQ0273 — compiles fine, renders the WRONG math; only
  ink-vs-render comparison catches these (the class the P11 SLT distance
  cannot see when the register also lacks the formula).
Cross-session source: inkdrill-0d, 2026-08-19. The inkdrill harness writes
per-doc `report.compare.tsv` into each library folder when its run completes.

**Cross-session verification contract (2026-08-19, mutual):** regenerated
reports are never handed to the inkdrill session without a local pass of THEIR
probe first (reproduce it from ~/inkdrill: pngio.auto_mask +
__main__._table_cells, expect 5 columns on the equations pages); they never
report a generator defect without first ruling out instrument fault.

**Probe at >= 200 dpi.** inkdrill measured (2026-08-20, 0802.3344) that a scan
crop sits ~0.9mm below its rule at EVERY dpi — the "touching" seen in a viewer
is downsampling — but below 200 dpi cells stop being holes topologically (3
merge at 72/96, 1 at 150, none at 200+). Measured consequence for OUR probe:
the COLUMN-COUNT check is dpi-insensitive (bh2/BH3FR/WDorg4/BH1org all give an
identical lattice at 96/150/200/300, because median-span filling repairs a
fragmented slot), so past acceptance verdicts at r150 stand — but per-CELL
measurements below 200 dpi report merges that do not exist at working
resolution. Run acceptance at 300.
This ended a three-round ping-pong whose three real mechanisms are in commit
bdbd5a2 (overfull padding reserve, mixed-section pages, version-suffixed
identifiers overprinting the Page column).

### trailing_punct — the separation, and the ORDER it must be done in (2026-08-20)

**Design (user).** The TiddlyWiki arrangement is the model: the character
lives in the `text` field and the `<$latex>` widget holds only mathematics.
`trailing_punct` in the docmodel is that same separation made portable — the
math object's `latex` holds mathematics only, the swept-up sentence mark moves
to `trailing_punct`, and **the compare function sees NEITHER side's copy**
(not the LaTeX side's, not the ink/scan side's): pure math is compared to pure
math.

**Scale (out/024.txt).** 2,113 objects carry a genuine top-level trailing mark
— 39.8% of all display equations, against 0.15% of inline formulas. So this is
not a rounding-error cleanup; it touches two of every five display equations.

**MIGRATION PROTOCOL (agreed with inkdrill, 2026-08-20).** 025 is
implemented (`pdfdrill trailingpunct`, commit 14cb02d) and NO library
document has been mutated. Agreed sequence, resumable after a reset:

    1. inkdrill's in-flight compare exits, distribution reported
    2. pdfdrill migrates the FOUR BOOKS only (59 marks: bh2 17+2,
       BH1org_OCR 24+1, BH3FR 5+0, WDorg4 6+4) + re-project + regenerate
    3. inkdrill verifies per-cell component counts UNCHANGED on bh2
    4. only then the 49-document corpus (2,054 marks)

Step 3 is the gate: the report sets the mark AFTER the math box
(`\FitMath{$...$},`) precisely so the ink of both columns is unchanged,
which lets the consumer attribute any delta to the migration rather than
to a layout change. If the books show a per-cell delta, STOP.

**COMPLETE (2026-08-20, commit a0ff8a9).** 2,113 marks separated — 59 in the
books, 2,054 across the 49 corpus documents — exactly the dry-run prediction.
Corpus 942 pages against the 941/942 baseline. Consumer verified per-cell
parity on bh2: 10,432 of 10,434 cells identical, the 2 explained (colons in a
LaTeX-source column the compare never reads).

MEASURED CAVEAT — "no layout cost" is true at page-count level and NOT at
row-placement level. On 0902.0431 (673 marks) 6 of 4,386 rows sit one page
EARLIER after the migration (all delta -1; zero rows appear or disappear on
either side; bh2's 19 marks shifted nothing). Removing the mark from inside
the math box makes a cell marginally shorter, so a row that sat just past a
page boundary now fits before it. Harmless for ink comparison — a row is the
same row, one page earlier — but any PAGE-INDEXED artifact built against a
pre-migration report is off by one for those rows.

**VERIFIED END TO END (2026-08-20).** Consumer re-ran the 50-document
compare against the migrated corpus: 4,335 rows over 49 of 49 documents,
IDENTICAL row and document counts to pre-migration. Class movement, on a
4,335-row population: clean +4, noise -8, weak +1, stable +5, component -2,
findings 1,095 -> 1,099 (25.4%). Largest class delta 0.4%; the component
channel their findings are ranked on moved 2 rows of 283. The 20 rows that
changed class are the reflow residue already characterised — rows that moved
a page rasterise marginally differently and nudge across a noise boundary —
not an ink effect. Evidence: the pre/post pair of compare runs, plus the
per-cell A/Bs on bh2 (10,432/10,434 identical) and 0902.0431 (8,796 cells,
0 one-sided, 51 differing, none above the component noise ceiling).
Their findings file: results/compare-P13-arxiv-reports-<stamp>.tsv.

**Atomicity is not required** — `normalize_latex` drops a trailing mark, so
a separated value and an unseparated one compare EQUAL. A reset mid-migration
cannot produce a divergence storm; the corpus may sit half-migrated
indefinitely without harm.

**ORDER, and why it is not negotiable.** 028 runs BEFORE anything is stripped;
025 (the LaTeX-side move) waits for it. Strip the LaTeX side while the ink side
still carries the character and the two sides disagree on ~2,113 equations for
that whole run — the compare output is then not "mostly right", it is
UNUSABLE, and unusable in a way that looks like a real finding storm. Nothing
strips until 028 is confirmed complete.

### Retraction task — at U0, contract table written, U1 not started

`pdfdrill model --force` drops derived layers without retracting facts/evidence
(objects 301→261, Reference 40→0, while `BIBLIOGRAPHY_BUILT` survives and
`status` reports nothing). Recoverable (`pdfdrill bibliography` restores) — a
bookkeeping bug, not data loss. A parallel session landed `bc76c36`; reconcile
before redoing.

---

## 4. Known skips — none

`tests/test_layer_detect.py` skipped for five sessions because its 1706.03762
fixtures lived only in a scratchpad path containing a session id. Committed,
gzipped, at `tests/fixtures/layer_detect/` (103+25 KB; the "~15 MB" estimate
that kept them out was never measured). A scratchpad copy still wins when
present via `PDFDRILL_LAYER_FIXTURES`; verified the suite passes with that
variable pointing at a nonexistent path. To regenerate: build 1706.03762, run
geometry/bibliography/expandmath/svg/tiddlers, copy `model_BEFORE.json`;
`model --force`; copy `model_AFTER.json` (must keep 65 objects with a region).

## 5. Assumptions still unverified

- German compounds untested WITH spylls (not installed): the floor was shown to
  fail; spylls was not shown to succeed.
- Whether `docops/mutators/dehyphenate.py` consults hyphenation PATTERNS at
  all, or only the lexicon, was not checked.
- Nothing has touched the **tesseract or pdfminer routes**, where the user says
  the errors originate.
- `spellqc.classify` is `(speller, left, right)`; a language string in third
  position raises a confusing `AttributeError`. Not fixed.
- 20 raw model writes were converted to atomic `save_model` (silent
  `default=str` coercion → raised exception); 0 existing repr fossils found,
  but no test exercises every command's write path.
