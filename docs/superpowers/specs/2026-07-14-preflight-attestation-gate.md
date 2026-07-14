# Preflight attestation gate — design

**Problem.** pdfdrill's prose output reads as authoritative, so an LLM that
skimmed or truncated the SKILL produces trusted-but-WRONG results (wrong
extraction route, duplicated equations, a directory stat'ed as a PDF). Observed
live on a Claude.ai run: the SKILL was not read completely and a cascade of
avoidable errors followed. A CLI cannot force an LLM to read anything, so the
defense is a **hard-stop attestation gate** plus defense-in-depth.

**User decisions (2026-07-14).** Enforcement = **block build/cost commands**
(read-only bootstrap stays open). Proof-of-reading = an **end-of-SKILL token**
(catches truncation).

## Mechanism

### 1. Attestation token (proof the whole SKILL was read)
`SKILL.md` ends with `DRILL-<8 hex>` — a checksum of the SKILL body (everything
except the token region itself, trailing-whitespace-normalised). An LLM that read
to the last line can quote it; one that truncated cannot. `skillsync render-skill`
computes and writes it via `preflight.render_token_block`; a drift test asserts the
printed token equals `preflight.expected_token()` (recomputed from the file), so a
SKILL edit without a `skillsync` re-run fails CI.

### 2. `pdfdrill preflight`
- No arg: prints the distilled CRITICAL RULES + a core-dep check + how to attest.
- `--ack <TOKEN>`: validates against `expected_token()`; on success writes a
  session marker; wrong token → refusal that says "the token is the SKILL's last
  line."

### 3. The marker (`preflight.py`)
`<download_dir>/.pdfdrill-preflight.json` = `{token, ts}`. Valid iff the stored
token still equals the current `expected_token()` (a SKILL change invalidates it →
re-read) AND age < 24h. `PDFDRILL_PREFLIGHT_TOKEN=<token>` attests statelessly.

### 4. The hard stop (`cli.main`)
Before dispatch: `if preflight.blocks(cmd): print(gate_message); return 2`.
`blocks = enforced() and is_gated(cmd) and not is_attested()`.
- **EXEMPT** (always open): preflight, doctor, help, config, skill, size, pdfinfo,
  steps, plan, status, artifacts, ls, links, dests, urls, fonts, fonts_layer,
  images, route — read-only bootstrap/introspection so the LLM can always reach
  `preflight` and discover the gate.
- **GATED** (everything else): model, mathpix, latex, tiddlers, semantic, make,
  ocr, vision, … — build/mutate/cost.
- The gate is wrapped in try/except so a broken gate never bricks the CLI.

### 5. Escape hatch
`PDFDRILL_NO_PREFLIGHT=1` disables the gate. Set by the trusted local wrappers
(`drillbatch.pdfdrill_base` → also covers the MCP server, `drillui_chat`) — those
are curated command surfaces, not the raw-SKILL path the gate targets. In-process
handler calls (`cmd_folder`, `--ensure`, `make`'s steps) never re-enter `cli.main`,
so they aren't gated twice. The test suite calls `cmd_*` directly (never
`cli.main`), so it is unaffected.

## Defense in depth (reduce error chance regardless of the gate)
- Front-loaded "⛔ MANDATORY PREFLIGHT" block at the TOP of SKILL.md, so even a
  truncating LLM sees the disaster-preventing rules first.
- CLI validators that catch the disaster patterns directly: a directory is never
  accepted as a PDF (`sources` is_file), `latex` never duplicates equations
  (added_by guard), a math paper never presents a 0-equation model as complete
  (NEEDS_VISION_OCR gate).

## Out of scope
- Cryptographic anti-spoofing (a determined LLM could read the token from the repo
  without reading the prose) — the goal is a good-faith gate a compliant LLM
  passes and a non-compliant one fails, not DRM.
- Comprehension challenges (deferred — brittle vs. the token's simplicity).

## Tests
`tests/test_preflight.py` (8): token determinism/region-exclusion, render writes
last line, SKILL-change changes token, attest round-trip + wrong token, marker
invalidated on SKILL change, gate blocks-build/allows-bootstrap, env bypass, and
the not-stale drift gate on the real bundled SKILL.
