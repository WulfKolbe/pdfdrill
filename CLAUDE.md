# CLAUDE.md

Guidance for Claude Code in this repository. This file is deliberately COMPACT —
it is loaded into every session. The full historical guidance (3,271 lines of
per-feature notes accumulated 2026-06..07) is preserved verbatim in
**`docs/CLAUDE-FULL.md`**; consult it when working on a specific subsystem, not
by default.

## Read first, every new session

**`docs/HANDOVER.md`** — one page: the working surface, the measured constants
each with the population it came from, open items, and the failure classes that
cost time here.

**`docs/HANDOVER-RULES.md`** — the 44 working rules each learned by a defect,
the non-obvious environment facts (LgEval pin, dictionaries, `resume.sh`), and
the unverified assumptions.

**The next section is not reference material — it is the shape of every task's
result.** A task here is finished when a real `pdfdrill` command in a fresh
shell has been run and its output recorded, not when the code looks right.

## Every task: scratch tests while working, acceptance only on the real command line

### Two kinds of test, and only one of them counts

**While you work: scratch tests are allowed.** Use whatever is fastest to try an idea:
`python3 -c`, a throwaway script, calling one function directly, `pytest -k` on one unit, a fake
input, a monkeypatched network call. These tests are for you. They show that a piece behaves; they
do not show that the user's command works. Keep them outside the repo, in `$TMPDIR` or
`/tmp/scratch-<task>/`. Don't commit them, and don't cite them as evidence.

**At the end: acceptance is a real command in bash.** A task counts as tested only through the
commands a user types, run as a separate process in a fresh shell:

```bash
cd "$(mktemp -d)"                                  # not the repo, not your scratch dir
env -i HOME="$HOME" PATH="$PATH" PDFDRILL_SANDBOX=1 \
  pdfdrill drill <input> ; echo "exit=$?"
```

These rules apply to the acceptance run:

1. **The installed entry point, not the module.** Call `pdfdrill …`, not `python3 -m`, not
   `PYTHONPATH=src`, and not an import of `cmd_*`. If `pdfdrill` is not on PATH, the install is part
   of what you are testing, so report that.
2. **No flags the user wasn't told to use.** If the task says `pdfdrill drill <pdf>`, run exactly
   that. A step that only works with `--force`, an environment variable or a pre-seeded file did not
   pass.
3. **Run from a fresh shell and a clean directory.** Use no state left over from scratch work: no
   cached sidecar, no `.env` you made, no exported variable. Run the keyless case under
   `PDFDRILL_SANDBOX=1`. Run the keyed case only if the owner says keys may be spent, and name the
   key.
4. **Check the output, not only the exit code.** For each acceptance command, record:
   - the command line, verbatim
   - `exit=<n>`
   - the lines of stdout that prove the claim (lane chosen, files written)
   - every file the command says it wrote, with its existence checked by `ls -l` and its content
     checked by one concrete probe (e.g. `grep -c 'data-id=' x.inspect.html`, `python3 -m
     json.tool x.lines.json >/dev/null`)
5. **Real inputs only.** Use the example inputs named in the task. Don't use a PDF you generated to
   make the test pass, unless the task asks for that.
6. **A test that can't run is NOT RUN.** If there's no network, no key or no binary, write
   `NOT RUN: <reason>`. It is not a pass, and it goes into the unverified list.

### The report

```
Scratch tests (not evidence): <one line, what you tried>
Acceptance (bash, fresh shell):
  $ pdfdrill drill files/x.pdf            exit=0   lane=born_digital   x.inspect.html 1.2 MB, 412 data-id
  $ pdfdrill drill 2402.13444             NOT RUN: arxiv.org unreachable from this machine
Unverified: <every NOT RUN, every assumption>
```

Don't write "done", "works" or "fixed". The acceptance lines are the result.

## Before building anything that reads pdfdrill output or writes a projection

Read these first, then check `pdfdrill --help` for a command that already does it:

- **`docs/TRANSCLUSION.md`** — most "content is missing" reports are transclusion
  failures and are invisible unless you know the shape.
- **`docs/layers/README.md`** — the living layer documentation. Anything dated in
  its filename is a historical snapshot and points here.
- **`docs/layers/PROPS.md`** — every DocObject prop, who writes it, who reads it,
  and the pairs where a wrong choice compiles silently (`latex` /
  `latex_original`, `latex_pretail` / `trailing_punct`, `latex_refined`).
  Generated; `docmodel.prop_contract` holds it to the corpus.

**`cmd_tiddlers` and `cmd_okf` already exist.** Both were reinvented this week —
a TiddlyWiki projection and an OKF bundle, each shipped and documented. The
pattern is the same one that hid `list_item` in 882 documents and called `code`
"dropped entirely" when 97.5% of it was already recovered: a capability exists,
is written down, and gets rebuilt anyway, because nothing in the path forces a
look. The type contract fixed that for MathPix's fields by making an unread type
fail a check; the equivalent for our own output is a reader who looks first.

## What this repo is

**PDFDRILL** = quality control of PDF→LaTeX OCR, building toward a
self-learning extraction loop. Three packages under `src/` (import root `src`):

1. **`src/pdfdrill/`** — flat CLI returning prose, state in a `.drill/` sidecar
   next to each PDF; wraps poppler/pdfplumber/ghostscript. The entry point the
   Claude.ai chatbot drives (the `pdfdrill` SKILL).
2. **`src/docmodel/`** — the unified document model: typed `Document` of
   `DocObject`s with anchor-based `Stream`s, `Realization`s, `Alignment`s,
   `Region`s. MathPix `lines.json` is the richest input; artifact suffix is
   `.docmodel.json`.
3. **`src/docops/`** — `Mutator`s + `Projector`s over a `Document` (markdown,
   tiddlers, formula report, compare table, LaTeX/beamer, plaintext…).

Also: `src/semantic/` (evidence-backed entity/relation graph + compiler),
`src/features/` (flat text extractors), `src/vocabnet/` (controlled
vocabularies, MSC/PhySH/GND…), `src/mathlayer/` (LaTeX→SymPy canonical IR),
`src/mathgold/` (Symbol Layout Trees + LgEval scoring), `src/passes/`
(enhancement pipeline), `src/pdfdrill/scandrill/` (scanner acquisition).

**Layer tower L0–L8**: canonical docs in `docs/layers/` (index `README.md`,
inter-layer semantics `TOWER.md`). When working on layer N, edit only
`docs/layers/L<N>-*.md`; never duplicate layer docs into this file.

## Running

Python 3 only. `pip install -e .` gives the `pdfdrill` console script; or:

```bash
./pdfdrill <command> <pdf>                       # wrapper, sets PYTHONPATH=src
PYTHONPATH=src python3 -m pdfdrill <command> <pdf> [args]
```

- `bash bootstrap.sh` installs missing system deps (poppler, ghostscript,
  LaTeX+dvisvgm) via apt-get; **`pdfdrill doctor`** reports tools/deps/keys
  anytime. **No OCR engine is installed or wanted** — see the lane contract.
- Build/extract commands are gated by `pdfdrill preflight --ack <TOKEN>` per
  working directory; automation sets `PDFDRILL_NO_PREFLIGHT=1`.
- `<pdf>` may be a local path, a known-host https URL, or a bare arXiv id —
  downloaded once, cached under the config `download_dir`. **Never
  curl/wget/tar a PDF or e-print yourself; pass the URL/id to pdfdrill.**

## Tests

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/ -q -p no:cacheprovider
```

`PYTHONDONTWRITEBYTECODE=1` is not optional — stale `.pyc` files have produced
tests failing against correct source (HANDOVER-RULES rule 4). **pytest itself is
the `[dev]` extra** — nothing in the documented install used to provide it (it
came in as a side effect of the pdfminer-fork script), so `pip install -e
'.[dev]'`.

**A suite number is meaningless without the install it came from.** Every count
quoted in this repo until 2026-10-21 came from a machine with every extra, and
had never been run on the install the README documents — where the suite did not
even collect (an auditing session, finding C). So say which:

| install | command | what it proves |
|---|---|---|
| **base** | `bash bootstrap.sh && pip install -e '.[dev]'` | the documented install, which is also the sandbox: base deps only (numpy, PyYAML, pdfplumber, pydantic, pypdf, the patched pdfminer). Everything extras-gated must SKIP here, never fail. |
| **full** | `pip install -e '.[dev,math,layout,scan,fontid,imageserver,speech,…]'` | the development machine. Nothing may skip for a missing module. |

`tests/test_suite_runs_on_the_documented_install.py` is the gate: a test that
imports a module the base install does not ship must declare it
(`pytest.importorskip`), or it stops collection (at module level) or fails as if
the code were broken (in a test body). Quote the two numbers together, each with
its install, or neither.

## Command surface — single source of truth

- **`.claude/skills/pdfdrill/commands.yaml`** is the SSOT (125 typed commands);
  `cli.HANDLERS` is ground truth for which exist. Everything else is generated.
- Workflow: edit `commands.yaml` → `python3 tools/skillsync.py all .` → commit.
  CI (`.github/workflows/skill-sync.yml` + `tests/test_skill_sync.py`) gates
  drift. Never hand-edit the generated help or the SKILL.md tables.
- Prerequisites are declarative (`requires:`/`done_when:`): `pdfdrill steps
  <cmd> <pdf>` shows the chain; `--ensure` auto-runs missing steps. Only
  offline-safe steps are ever auto-inserted; paid/network steps (mathpix,
  bibfetch, vision, translate) never run unasked.

## Operational rules (each learned the hard way; details in docs/CLAUDE-FULL.md)

- **Cheapest sufficient command first.** `size`/`pdfinfo`/`links`/`dests`
  before any heavy pass. `links` reads the annotation layer and finds URLs with
  no visible anchor text that every text/OCR route drops (the "killer case").
- **arXiv is free.** `model` builds from the e-print LaTeX source (fast,
  keyless). `mathpix` runs when asked — a named command is an instruction —
  and appends a one-line free-route note after the work. The MathPix-rich
  path is `mathpix <id>` → `model` → …
- **Ghostscript at ≥400 dpi is the ONLY rasterizer** (`pdf_reading.rasterize`/
  `render_page`); no pdftoppm/fitz fallback. For table-rule measurements use
  800 dpi (HANDOVER-RULES §3 T2).
- **The LANE CONTRACT is `docs/LANES.md`** — five lanes in a fixed order,
  decided by one pure function (`ocr_router.choose_route`), reported in the same
  words by `route`, `drill` and `doctor`: the PDF's own text layer (free) → the
  arXiv author's LaTeX (free) → `gemmaocr` (metered) → `mathpix` (paid) → the
  free geometry-only lane (no reading key at all). **OCR is the last resort**:
  lanes 3-5 are reached only when the document has neither a text layer of its
  own nor an author's source. Page count no longer selects a lane — the old
  ">20pp → MathPix" threshold was set when the alternative was a 50 s/page
  vision call. `pdfdrill drill <pdf>` runs the contract to an inspect.html and
  runs nothing that costs money. `PDFDRILL_SANDBOX=1` answers as the keyless
  sandbox does, on a keyed machine.
- **pdfdrill runs NO OCR ENGINE.** tesseract is out of the distribution:
  `bootstrap.sh` installs none, `doctor` looks for none, no module invokes one,
  and `tests/test_no_ocr_engine.py` fails the suite if an argv head or a
  `which()` probe for one comes back. The verb `pdfdrill ocr` is kept as a
  POINTER that names the lane. Word boxes come from `word_boxes`: the PDF's own
  text layer (boxes WITH text, in points), the page's own ink (boxes with NO
  text, in render pixels — what `fontid` always actually wanted), or nothing
  plus the lane that would change that. A reading bought from a provider is NOT
  a word-box source: `gemmaocr`/`mathpix` give LINE boxes, and a line box where
  a word box is expected is a wrong measurement, not a missing one.
- **No command buys a reading unasked.** `model` took the paid lane whenever a
  key was present; it now names it (`--mathpix` is the opt-in). The rule is the
  planner's and it had leaked one level down.
- **Scan acquisition never adds an OCR text layer** (it would misroute `route`
  to the born-digital lane).
- **Projected LaTeX compiles with xelatex**, not pdflatex (models carry raw
  Unicode). `injectlatex` = INPUT (author source → gold provenance);
  `latex`/`beamer` = OUTPUT (docmodel → .tex).
- **All model I/O goes through `model_io.save_model`/`load_model`/
  `load_docgraph`** (atomic write + packed `.docpack` sidecar + mtime staleness
  guard). Read-only commands use the ~10× faster DocGraph path.
- **A stale lines.json is never silently served** — projectors rebuild via
  `_stale_or_absent`/`_fresh_docgraph`.
- **Keyless math**: a text-only route cannot type equations; a 0-equation
  model on a math-bearing doc sets `NEEDS_VISION_OCR` and the fix is `pdfdrill
  latex` (arXiv gold, free) / `visionocr` (LLM delegation) / `gemmaocr`
  (metered) / `mathpix` (paid).
- **LLM delegation** (`llm_delegate`): no API key → route sub-tasks to the
  running Claude (CLI `claude -p`, or sandbox file handshake); image tasks are
  BATCHED (≤10/call) to amortize the ~180K-token harness tax.
- **Credentials are env-vars only** (`MATHPIX_APP_ID/KEY`, `OPENAI_API_KEY`,
  `DEEPL_API_KEY`, `PERPLEXITY_API_KEY`, `NOVITA_API_KEY`), never committed.
  Network calls go through `net.urlopen`; a blocked host raises a typed,
  host-named `NetworkBlocked`, never a stack trace.
- **Licence-bound vocabulary downloads stay out of git** (`vocab/sources/*/`
  except `STUB.md`; all of `vocab/compiled/`).
- **One writer per document.** Every build command writes fixed names beside
  the PDF, so two processes on one document interleave rather than collide.
  `doclock.hold` / `@_writes("<cmd>")` takes an `O_EXCL` lock named after the
  PDF; the second process refuses. 72 handlers carry it, and
  `test_every_pdf_writer_holds_the_lock` fails if a new one does not. The
  LaTeX compile also runs in a private directory (`-output-directory`, cwd
  still the doc folder so relative `\includegraphics` resolves) — a shared
  `.aux` yields a PDF resolved against another build's cross-references: it
  compiles, it looks right, and every `\ref` points at the wrong equation
  (297).
- **A prompt sent to a model lives in `docs/prompts/`, never in a Python
  string** (466). `YYYY-MM-DD-<name>-prompt.md`, body below the first `---`;
  `prompts.load(name)` reads it, `prompts.identity(name)` returns the filename
  and the sha256 of the body, and `callog.log_call(prompt_name=…)` records
  both beside the verbatim text. 447 already kept every prompt and reply; what
  it could not say was whether two runs used the SAME prompt. A missing file
  raises rather than falling back — a run that silently used a different
  prompt is the failure the convention exists to prevent.
- **Verify pushes**: after any push claim, `git ls-remote origin` — commits
  must never exist only locally or in a scratch worktree (2026-08-16 incident,
  HANDOVER-RULES header).
- **A new capability is a layer in the manifest, not a new verb — and not a
  tool.** Code that lands in `tools/` is invisible to the planner, `status`,
  and `--ensure`; register it in `commands.yaml` with `requires:`/`done_when:`
  so the layer graph can reach it (audit A4, 2026-08-17; `reporttex` is the
  worked example — it started in `tools/` and had to be promoted).
- **Math on a table cell, a heading, a title, a TOC entry, a figure label or
  inside a caption is never a transclusion** (674/676).
  `src/docmodel/line_types.py` is the single source of truth — five families,
  16 line types, plus `caption_anchors(doc)` because MathPix types most
  captions plain `text` and a caption's span is a Paragraph property, not a
  line type. Five readers enforce it (creation, the TiddlyWiki projector, the
  LaTeX projector, the host-line pick, the report) because the models on disk
  predate the gate. Refusing a transclusion does NOT mean losing the
  mathematics: `src/docops/mathdelims.py` renders it in place as the
  `<$latex .../>` widget every projection converts from. Delete `line_types`
  rather than growing it once the pipeline is subtractive.
- **A layer's `requires` names everything it READS, not everything it calls.**
  `reporttex` never calls `mathpix` — it reads the model mathpix populates;
  that indirection is how dependencies stay undeclared and get rediscovered by
  a user with a broken output (empty math columns, 2026-08-18). A dependency
  that is not in the manifest is not a dependency, it is a hope. Paid/network
  layers (`network: true`) are DECLARED in chains but never auto-run —
  `--ensure` runs the offline ones and names the paid ones with the exact
  command that satisfies them (`planner.network_commands`).

## Where the details live

| Topic | Doc |
|---|---|
| How a task is tested, and what counts as evidence | this file, § _Every task_ (above) |
| Which reading a document gets, and why | `docs/LANES.md` |
| State of play, constants, open work | `docs/HANDOVER.md` |
| Rules learned by defect, env facts | `docs/HANDOVER-RULES.md` |
| Full per-feature guidance (historic CLAUDE.md) | `docs/CLAUDE-FULL.md` |
| Layer semantics L0–L8 | `docs/layers/` |
| Per-command reference | `.claude/skills/pdfdrill/SKILL.md` (generated) |
| User-facing overview, projections table, keys | `README.md` |
| drillui / MCP servers | `tools/DRILLUI.md`, `tools/MCP.md` |
| Design specs | `docs/superpowers/specs/` |
