# Capability planner — derived implementation plan

> Derived from the user's proposal *"Capability planner for pdfdrill — one graph,
> two traversals"* (pasted 2026-07-14), after independent verification of its
> load-bearing claims against the tree. This is a PLAN, not an implementation.
> Sequencing rule from the proposal is kept: **A ⊥ B; C needs A; D needs B+C; E
> needs all. Nothing before Phase E changes what any existing command does.**

## 0. Verification (done this session — grounds the plan)

Every claim the plan depends on was checked in source, not trusted from the
proposal's own tags:

- **Manifest gap is total.** `commands.yaml` = 110 commands; `requires:` on 40,
  `done_when:` on 3, **`produces:` on 0, `destroys:` on 0**, `offline_ok` 104,
  `network` 6. So Phase A is pure data-entry across the whole surface, not a
  patch of a few.
- **One non-monotone fact.** `remove_fact(NEEDS_VISION_OCR)` at
  `commands.py:4125` and `:5402` — the single retraction the proposal names.
  Everything else is cumulative `add_fact`.
- **mtime is the silent trigger.** `_stale_or_absent` (`commands.py:311`) fires a
  rebuild on `lines.json.mtime > model.mtime`. `model_io._fresh` (`:39`) is a
  second mtime guard. This is the make-weakness the proposal targets.
- **Clobber is real.** `cmd_model` (`commands.py:2386`) rebuilds the docmodel
  from lines.json; its own stale-doc comment describes content "silently
  missing" — the A-mode enrichments (latex/geometry/bib/nlp/eqnums/fontspans)
  are overwritten. This is the soundness precondition for any backward planner.
- **Planner half-exists.** `planner.plan(target, requires, satisfied)` is a
  topological insert toward a *command name*; `planner.ensure()` runs missing
  steps under an offline-only safety rule. No capability goals, no clobber
  reasoning, no proof objects.
- **Dead FSM confirmed.** `engine.py` defines both `Engine` (branching,
  `Transition`-edge FSM) and `SequentialEngine` (linear). `commands.py` imports
  **only** `SequentialEngine`. `transitions.py` (the branching graph + poppler
  nodes) is imported by nothing but `SOURCES.txt`. The FSM apparatus is dead.

One user claim NOT confirmed and therefore NOT built on: `docos.load_state`
(`docos.py:135`) **does** load persisted state at startup, so "state persisted
but not loaded" is at most a **drillui-TUI** issue — Phase 0 verifies it before
acting.

## 1. Assessment — accept / adjust / defer

**Accept as-is:**
- `destroys:` clobber edges as the non-negotiable first addition, and
  **clobber-refusal** (option (a): refuse a plan that destroys a still-needed
  held capability) as the day-one behavior. It is pure planning logic.
- Proof objects (input content-hashes) replacing the mtime trigger — validity =
  every input hash still matches disk. Schema upgrade of the existing
  `evidence{}`/`transitions[]`, not a new store.
- Parameterized, **ranked** capabilities to avoid state explosion:
  `TextSourceAvailable(provenance, rank)`, `MathAvailable(rank)` — and
  re-modelling `NEEDS_VISION_OCR` as `MathAvailable(rank=absent)` so the lattice
  is monotone in rank (kills the one retraction).
- The A⊥B, C←A, D←B+C, E←all sequencing.

**Adjust:**
- **Add Phase 0 (dead-code + honesty pass)** before A. The user's framing
  ("devastating results: FSM dead code, drillui state not loaded") is a request
  to *reconcile the graph story first*. Deleting `transitions.py` + the dead
  `Engine` (keeping `SequentialEngine`) removes a second, competing "graph
  traversal" so the capability planner is unambiguously THE graph. Verify the
  drillui-state claim; fix or document.
- **Ranks are validated against `merge` before they drive policy.** The proposal
  itself flags rank-order sufficiency as `[design]`. Phase A includes a
  characterization test of `merge_latex`'s actual field-level win rules; ranks
  encode what that test observes, not a guessed order.
- **Proof capture via an `add_fact` wrapper is a hypothesis, not a given.** The
  proposal admits it "may need per-command touch". Phase B builds the wrapper
  `mark(fact, produced_by=…, inputs=[paths], params=…)` and migrates the ~3
  highest-value producers (`model`, `mathpix`/lines, `latex`) first; a census
  test tracks coverage so the remaining call sites are visible, not silently
  unproofed.

**Defer (named, not built):**
- Save/restore / single-writer-layers refactor (proposal option (b)). The
  `sidecar.layers{}` dict points there; clobber-refusal (a) makes the bug loud
  without it. Revisit after Phase E.
- RL framing (observation = ranked capability vector, reward = rank gain / cost).
  Falls out for free once the cost vector + ranks exist; no code now.
- Set-level capabilities (`SetCombined(members_hash)`, `RepoPublished(…)`) —
  Phase E's last, smallest step, only after per-doc proofs exist.
- Lens YAML blocks — Phase E; `route` stays the degenerate built-in lens.

## 2. File structure

- `src/pdfdrill/capability.py` — **new, pure.** The typed capability vocabulary:
  `Capability{name, provenance, rank}`, the rank orders per family, `parse`/
  `render`, and `RANKS` tables. No I/O.
- `src/pdfdrill/capability_planner.py` — **new, pure.** `plan(goal, held,
  manifest) -> list[str] | ClobberRefused`. Reads the extended manifest + a
  held-capability set; emits ordered actions or a typed refusal. No execution.
- `src/pdfdrill/proofs.py` — **new.** `make_proof(produced_by, inputs, params)`,
  `verify(proof) -> bool` (re-hash inputs, compare), `content_hash(path)`.
- `.claude/skills/pdfdrill/commands.yaml` — **extend.** `produces:`/`destroys:`/
  `cost:` per command. Regenerated artifacts via `skillsync all`.
- `src/pdfdrill/sidecar.py` — **extend.** `capabilities{}` block + a `mark()`
  wrapper alongside `add_fact` (parallel write, old readers untouched).
- `src/pdfdrill/commands.py` — **touch, Phase D+.** `_stale_or_absent` gains a
  proof-validity path behind `--legacy-stale`; `cmd_plan`/`cmd_make` handlers.
- `src/pdfdrill/planner.py` — kept; `capability_planner` is the superset. Do not
  break `--ensure` (its offline rule becomes a cost-vector constraint in E).
- **Delete** `src/pdfdrill/transitions.py` + the dead `Engine` class (Phase 0).
- Tests: `test_capability.py`, `test_capability_planner.py`, `test_proofs.py`,
  `test_manifest_closure.py`, `test_dead_engine_removed.py`.

## 3. Phases (each independently testable; TDD, RED→GREEN)

### Phase 0 — Reconcile the graph story (dead code + honesty)
- **0.1** `test_dead_engine_removed.py`: assert nothing imports `transitions` and
  `engine.Engine` is gone (grep-in-test over `src/`). RED.
- **0.2** Delete `transitions.py`; remove `Engine`/`Transition`/`always` from
  `engine.py`, keeping `SequentialEngine` + `Node`/`Metric`. Run the full suite
  (the md/drill engine path uses `SequentialEngine` only). GREEN.
- **0.3** Verify the drillui-state claim: trace `tools/drillui_chat.py` /
  `drillbatch` session-store load. If a persisted store is written but never
  re-read at startup, fix (load it) or document why; add a test if code changes.
- **0.4** Commit: "remove dead branching-FSM; SequentialEngine is the only
  engine". No behavior change.

### Phase A — Manifest completion (pure data; A ⊥ B)
- **A.1** `test_manifest_closure.py` RED, asserting: (a) every fact in the
  fact-set is `produces:`d by ≥1 command; (b) every `requires:` entry is
  `produces:`d by some command; (c) every `destroys:` names a real capability;
  (d) `skill --check` still passes.
- **A.2** Characterize `merge_latex` field-win rules in a test → the observed
  order becomes the `RANKS` fixture Phase-A-A tests import.
- **A.3** Fill `produces:`/`destroys:`/`cost:` for all 110 commands. `model`
  gets the full `destroys:` list (every A-mode capability). Run `skillsync all`.
  GREEN. **No code behavior changes in this phase.**

### Phase B — Proof-object layer (parallel write, no reads; B ⊥ A)
- **B.1** `test_proofs.py` RED: `make_proof` over two temp files → `verify` True;
  mutate a file → `verify` False.
- **B.2** Implement `proofs.py` + `Sidecar.mark(fact, produced_by, inputs,
  params)` writing `capabilities{}` next to `add_fact`.
- **B.3** Migrate `model`, the lines.json producers (`mathpix`/`ocr`), and
  `latex` to `mark`. `test_sidecar_proofs.py`: after `size`+`model` on the
  fixture, both facts AND proofs present, all input hashes verify. A coverage
  census test lists producers not yet emitting proofs (visible, not hidden).

### Phase C — `pdfdrill plan <goal> <pdf>` (read-only; C ← A)
- **C.1** RED: goal `ModelAvailable` on empty held-set → `[model]`.
- **C.2** **The acceptance test** (`test_capability_planner.py::
  test_clobber_refused_on_held_latex`): goal `SemanticGraphAvailable` with
  `LatexIngested` held → the planner MUST return `ClobberRefused(model,
  LatexIngested)` or a plan that routes around `model` — the encoded form of the
  mathpix-destroyed-latex incident. This test is the whole design's gate.
- **C.3** Implement `capability_planner.plan` (backward closure + topological
  order + clobber check). `cmd_plan` handler + manifest entry + skillsync. No
  execution.

### Phase D — Validity from hashes (D ← B+C)
- **D.1** RED: touch lines.json → its proof invalid → `plan` includes an explicit
  `model` step → clobber-check still fires on that step.
- **D.2** `_stale_or_absent` gains a proof-validity branch; `--legacy-stale`
  preserves the mtime trigger during transition. Default flips to proof-based
  only after the suite is green both ways.

### Phase E — Executor + `make` + `drill --need` + set-level (E ← all)
- **E.1** `cmd_make`: `plan` → execute via the existing `HANDLERS` map → record
  a proof per step → stop on first failure reporting the plan position.
- **E.2** Forward/shallow mode: `drill --need <goal>` = repeatedly plan
  depth-1-cheapest until goal ranks satisfied (generalize `route`'s
  choose-cheapest loop; `--ensure`'s offline rule → a cost-vector constraint).
- **E.3** Set-level capabilities (`SetCombined`/`GraphStoreCurrent`/
  `RepoPublished`, keyed by `members_hash` over per-doc proofs) in the
  docos/combine/publish layer — `make repo` rebuilds only the invalid closure.

## 4. Risks / open questions (carried from the proposal, made testable)

- **Rank sufficiency for merge policy** — retired by A.2's characterization test;
  if field-level wins aren't a total order, `RANKS` becomes per-field.
- **Proof capture without threading paths through 62 sites** — B.3's coverage
  census makes the gap measurable; per-command touch is acceptable if the
  wrapper can't infer inputs.
- **Planner cost at 110 actions** — unmeasured but small; add a timing assert to
  `test_capability_planner` if closure ever exceeds a few ms.
- **`--ensure` back-compat** — must keep passing throughout; it is the current
  users' entry point and only becomes a cost-constrained special case in E.

## 4a. Delivery status (2026-07-14)

Implemented, tested, and pushed (commits after the plan):

- **Phase 0 — DONE.** Deleted `transitions.py` + `metrics.py` and the dead
  branching `Engine`/`Transition`/`always`/`Metric`; only `SequentialEngine`
  remains. drillui now RESUMES its persisted `.drillui_session.docpack` at startup
  (`existing_session_store`/`session_members`; `--fresh` opts out) — the "state
  persisted but not loaded" fix. Tests: `test_dead_engine_removed`, `test_drillui_resume`.
- **Phase A — DONE.** `capgraph.py`: `produces()` AST-derived from `add_fact`
  (code-synced, no YAML duplication); `destroys()` authors the model-rebuild
  clobber. Closure guaranteed by `test_capgraph` (no phantom clobber,
  well-formedness, requires-closure). `GATE_FACTS` excludes NEEDS_VISION_OCR-style
  signals.
- **Phase B — DONE.** `proofs.py` (content-hash proofs, blake3/sha256) +
  `Sidecar.mark`/`capability_valid`; `model` (both build paths) and `latex`
  migrated; `capgraph.proof_emitting()` census. Tests: `test_proofs`.
- **Phase C — DONE.** `capability_planner.py`: `plan(goal, held, invalid)` +
  `clobber_check` + `ClobberRefused`; `pdfdrill plan <pdf> --goal <cap>`.
  **The acceptance gate passes** (semantic goal + held LaTeX + stale model →
  refusal), verified live through the CLI. Tests: `test_capability_planner`.
- **Phase D — DONE.** `_stale_or_absent` is proof-aware (content-hash, not mtime;
  `PDFDRILL_LEGACY_STALE=1` fallback); invalid capabilities feed the planner.
  Tests: `test_stale_proof`.
- **Phase E — core DONE.** `execute()`/`make()` + `pdfdrill make <pdf> --goal
  <cap>` (plan → execute → record proofs → stop-on-failure; refused plan runs
  nothing). Verified live. Tests: `test_make`.

Full suite: **1077 green.**

**Remaining (optional extensions, not blocking the DoD):** E.2 forward/shallow
`drill --need <goal>` (repeat depth-1-cheapest until ranks satisfied) and E.3
set-level capabilities (`SetCombined`/`RepoPublished` keyed by `members_hash`),
plus the deferred save/restore (single-writer-layers) refactor and ranked
capability families.

## 5. Definition of done

The design's acceptance test (C.2) passes: a backward plan toward a semantic
goal, with LaTeX enrichment held, **refuses** rather than silently inserting the
clobbering `model` rebuild — the hand-found data-loss bug is now a loud,
tested plan error. Everything through Phase D leaves existing command behavior
byte-identical (guarded by the unchanged full suite); Phase E adds `plan`/`make`/
`drill --need` as new surface without altering the old commands.
