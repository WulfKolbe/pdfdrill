# Handover — state of play

Written for a session with no history here. Facts are measured, with the command
that measured them. If a path has moved, trust the repository over this file.

Last verified: repo @ `efe35ff`, `main` == `master` == `eqblobs-and-gzip-tex` ==
`origin/*`, working tree clean.

    PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider
    -> 1969 passed, 5 skipped

**A skipped test is not a pass.** See "Known skips" below.

---

## 1. Working rules that were learned by defect

Each of these cost real time or real data in this project.

1. **Measure the premise before building on it.** Two units were rescoped by a
   measurement taken before the plan was written: the mathgold gold set moved
   from 87 equations to 21,230 (different prop), and T1 was found to have no
   producer at all.
2. **State the population beside every number.** Two commits recorded 21,240 and
   59 for "the mathgold population". Both were right and measured different
   things (structure vs structure+placement). See `docs/mathgold-population.txt`.
3. **A guarantee in a docstring is not a guarantee.** Run a branch-mutation
   sweep: set each `if` to True and to False, run the suite, investigate what
   survives. Survivors have four outcomes — killed, survived, incompetent
   (module no longer imports), equivalent (provably identical).
4. **Run mutation sweeps with `PYTHONDONTWRITEBYTECODE=1`.** A same-length edit
   (`base_head` -> `base_tail`) restored by `cp` matches the stale `.pyc` by size
   AND mtime. This produced a test failing against correct source, and a working
   fix was nearly reverted. `git diff --stat` after every write catches the
   related case; a `cp` restore produces no diff at all, so do both.
5. **Never return a plausible default for an unknown.** Raise, or return an
   explicit unresolved marker — never a sentinel string, because
   `"UNKNOWN" == "UNKNOWN"` makes two unidentified things equal. See
   `mathgold.slt.Unresolved`.
6. **Presence is not adequacy.** Four separate bugs took this shape: a fact set,
   a file existing, a route's own output existing, and a `_source` twin
   existing. Each needed a detector that reads the actual store.
7. **Verify the written file, not the object in memory.** Two defects were
   "in-memory right, file wrong" and 1745 tests caught neither. Persisting
   commands should assert through `tests/test_model_write_roundtrip.py::roundtrip`
   (currently used by 1 of 41 such commands — the meta-test pins that number).
8. **Do not ask what a command can answer.** Reversible? do it and record it.
   Only a matter of preference that changes what gets built? then ask.
9. **When deciding without the user:** take the reversible option and record the
   decision, the rejected alternative, and what would change your mind.

---

## 2. Environment facts that are not obvious

**Preflight.** Build/extract commands are blocked until `pdfdrill preflight --ack
<TOKEN>`, per working directory. Automation sets `PDFDRILL_NO_PREFLIGHT=1`.

**LgEval — invoked, never vendored.**

    repo    gitlab.com/dprl/lgeval        (github.com/DPRL/LgEval is 404)
    commit  9831a3c                       (HEAD c94f6dd imports lgeval.msg_debug,
                                           which the repository does not ship)
    path    ~/.local/share/lgeval         (must be importable AS `lgeval`)
    invoke  source tools/lgeval_env.sh; lgeval_score out.lg gold.lg

The github.com/michaelyin mirror is Python 2 and will not run.

**Spell / hyphenation dictionaries.** `/usr/share/hunspell` is English only.
German `de_DE.aff/.dic` and `hyph_de_DE.dic` exist ONLY inside a flatpak runtime
(`/var/lib/flatpak/runtime/org.kde.Platform/.../share/{hunspell,hyphen}/`).
`spylls` is NOT installed. Measured consequence:

    dictionary_status() -> de:'dic'  en:'enchant'  fr/es/it:'dic'  nl:'none'
    ok('Sphaerentrinitaet') -> False        (the `dic` floor is a bare word set:
    ok('Versicherung')      -> False         no COMPOUNDFLAG, no affix rules)

De-hyphenation still joins correctly for German, but by the soft heuristic
("lowercase continuation"), not by lexicon evidence — `DehyphResult.reason` says
which. `HUNSPELL_DICT_DIR` pointing at the flatpak path plus `pip install spylls`
would light up the affix-aware path with no C dependency. Neither is done.

**`resume.sh`** continues the most recent session. Pinning is opt-in
(`PDFDRILL_SESSION=<id>` or `--session <id>`) and a pin that fails exits 3 rather
than starting a fresh session.

---

## 3. Open work

### T4 deliverable 3 — the floor (unstarted; the unblocking item)

Deliverables 1-2 are done: `src/mathgold/slt.py` parses author LaTeX into a
Symbol Layout Tree and round-trips it through `.lg`. Measured over the corpus,
3000 uniform samples at seed 0: **99.8% parsed, .lg round-trip lossless on all
of them**, 64% single-expression / 36% containing an environment.

The floor takes pdfminer characters and positions, applies the crudest relation
rules (baseline overlap => Right, raised and smaller => Sup), emits `.lg`, and
scores against the gold with LgEval.

**Population is settled: 59 equations over 2 documents** (kolbe2018hubbard 54,
2510.11170v2 5) — the equations with `provenance == "tex"` AND a region+page.
The 21,230 source-built equations have gold structure but ZERO geometry, so they
cannot be scored by a floor that reads positions. Report the floor as anecdotal
at n=59. Enlarging it means attaching geometry to source-built models.

Report BOTH rows, never one: single-expression subset, and the full set with
environments held out as `Unresolved`. Do NOT split `align` blocks into rows to
enlarge the denominator — the alignment points are real structure.

### T2 — table rule weights (mechanism only)

`inkdrill/emit.py` exists at `f03b617` and writes `lines.json`, so T1 is
unblocked and done. `ink.rules[]` is NOT yet populated (inkdrill step 4), so
there is no rule-width data to rank. Build the ranking against a hand-made
`ink.rules[]`; cluster within one table and take the heavier cluster, confirm by
position — never an absolute width threshold (absolute value runs ~12% high).

`ink_regions` returns `Region` objects but `table_lines` takes a region **id** —
pass `regs[0].id`, or get `TypeError: unhashable type: 'Region'`.

### Retraction task — at U0, contract table written, U1 not started

`pdfdrill model --force` drops derived layers without retracting the facts and
evidence that claim they exist. Reproduced: objects 301->261, Reference 40->0,
alignments 76->0, streams 3->1, while `BIBLIOGRAPHY_BUILT` and
`bibliography_entries: 40` survive and `status` reports nothing. **Recoverable**
— `pdfdrill bibliography` restores all 40 — so it is a bookkeeping bug, not data
loss. A parallel session landed `bc76c36` for this; reconcile before redoing it.

---

## 4. Known skips — none

The suite runs **1974 passed, 0 skipped**.

`tests/test_layer_detect.py` skipped for five sessions because its 1706.03762
before/after fixtures lived only in a scratchpad path CONTAINING A SESSION ID.
They are now committed, gzipped, at `tests/fixtures/layer_detect/` — 103 KB +
25 KB. The estimate that kept them out ("~15 MB") was never measured.

A scratchpad copy still wins when present, and `PDFDRILL_LAYER_FIXTURES` points
at one, so a regenerated pair can be tried without touching the repo. Verified
by running the suite with that variable set to a nonexistent path: still 1974
passed, 0 skipped.

To regenerate: build 1706.03762, run geometry/bibliography/expandmath/svg/tiddlers,
copy the model as `model_BEFORE.json`; `model --force`; copy as `model_AFTER.json`.
The AFTER state must keep 65 objects carrying a region — that is the case the
geometry detector must not be fooled by.

## 5. Assumptions still unverified

- The dead-session proof for `resume.sh` used a NONEXISTENT id, not a genuinely
  crashed one. The harness returns the same "No conversation found", exit 1.
- German compound support is untested WITH spylls, since spylls is not installed.
  The floor was shown to fail; spylls was not shown to succeed.
- Whether `docops/mutators/dehyphenate.py` consults hyphenation PATTERNS at all,
  or only the lexicon, was not checked.
- Nothing in this project has touched the **Tesseract or pdfminer routes**, which
  is where the user says the errors originate.
- `spellqc.classify` is `(speller, left, right)`. Called with a language string
  in third position it raises `AttributeError: 'str' object has no attribute
  'available'` — a confusing internal error rather than a clear one. Not fixed.
- 20 raw model writes were converted to the atomic `save_model`. That converts a
  silent `default=str` coercion into a raised exception; a library-wide scan found
  0 existing repr fossils, but no test exercises every command's write path.
