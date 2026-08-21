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

**`docs/HANDOVER-RULES.md`** — the 18 working rules each learned by a defect,
the non-obvious environment facts (LgEval pin, dictionaries, `resume.sh`), and
the unverified assumptions.

## What this repo is

**PDFDRILL** = quality control of PDF→LaTeX OCR, building toward a
self-learning extraction loop. Three packages under `src/` (import root `src`):

1. **`src/pdfdrill/`** — flat CLI returning prose, state in a `.drill/` sidecar
   next to each PDF; wraps poppler/pdfplumber/tesseract. The entry point the
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

- `bash bootstrap.sh` installs missing system deps (poppler, tesseract,
  ghostscript, LaTeX+dvisvgm) via apt-get; **`pdfdrill doctor`** reports
  tools/deps/keys anytime.
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
tests failing against correct source (HANDOVER-RULES rule 4).

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
- **Scan acquisition never adds an OCR text layer** (it would misroute `route`
  to the born-digital lane). Scanned & ≤20pp → Gemma vision; >20pp → MathPix;
  text layer present → pdfminer.
- **Projected LaTeX compiles with xelatex**, not pdflatex (models carry raw
  Unicode). `injectlatex` = INPUT (author source → gold provenance);
  `latex`/`beamer` = OUTPUT (docmodel → .tex).
- **All model I/O goes through `model_io.save_model`/`load_model`/
  `load_docgraph`** (atomic write + packed `.docpack` sidecar + mtime staleness
  guard). Read-only commands use the ~10× faster DocGraph path.
- **A stale lines.json is never silently served** — projectors rebuild via
  `_stale_or_absent`/`_fresh_docgraph`.
- **Keyless math**: tesseract cannot type equations; a 0-equation model on a
  math-bearing doc sets `NEEDS_VISION_OCR` and the fix is `pdfdrill latex`
  (arXiv gold, free) / `visionocr` (LLM delegation) / `mathpix` (paid).
- **LLM delegation** (`llm_delegate`): no API key → route sub-tasks to the
  running Claude (CLI `claude -p`, or sandbox file handshake); image tasks are
  BATCHED (≤10/call) to amortize the ~180K-token harness tax.
- **Credentials are env-vars only** (`MATHPIX_APP_ID/KEY`, `OPENAI_API_KEY`,
  `DEEPL_API_KEY`, `PERPLEXITY_API_KEY`, `NOVITA_API_KEY`), never committed.
  Network calls go through `net.urlopen`; a blocked host raises a typed,
  host-named `NetworkBlocked`, never a stack trace.
- **Licence-bound vocabulary downloads stay out of git** (`vocab/sources/*/`
  except `STUB.md`; all of `vocab/compiled/`).
- **Verify pushes**: after any push claim, `git ls-remote origin` — commits
  must never exist only locally or in a scratch worktree (2026-08-16 incident,
  HANDOVER-RULES header).
- **A new capability is a layer in the manifest, not a new verb — and not a
  tool.** Code that lands in `tools/` is invisible to the planner, `status`,
  and `--ensure`; register it in `commands.yaml` with `requires:`/`done_when:`
  so the layer graph can reach it (audit A4, 2026-08-17; `reporttex` is the
  worked example — it started in `tools/` and had to be promoted).
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
| State of play, constants, open work | `docs/HANDOVER.md` |
| Rules learned by defect, env facts | `docs/HANDOVER-RULES.md` |
| Full per-feature guidance (historic CLAUDE.md) | `docs/CLAUDE-FULL.md` |
| Layer semantics L0–L8 | `docs/layers/` |
| Per-command reference | `.claude/skills/pdfdrill/SKILL.md` (generated) |
| User-facing overview, projections table, keys | `README.md` |
| drillui / MCP servers | `tools/DRILLUI.md`, `tools/MCP.md` |
| Design specs | `docs/superpowers/specs/` |
