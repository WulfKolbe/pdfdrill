# AGENTS.md — operating pdfdrill as an AI agent

If you are an AI assistant (Claude Code, Codex, Cursor, Aider, …) working with a
PDF, **pdfdrill is the source of truth for every extraction step**. Your job is to
call small pdfdrill commands and relay their prose. pdfdrill owns the heavy tools
(poppler, ghostscript, MathPix, Gemma-4, LaTeX) and the state machine.

The one rule behind all the others: **never solve a PDF-extraction step yourself if
pdfdrill has a command for it.** When something fails, take the next *valid*
transition (below) and say why — do not improvise a workaround.

## NEVER (this is cheating — it produces wrong, unverifiable results)

- ❌ `curl`/`wget`/`tar`/`unzip` a PDF or an arXiv e-print. Hand the URL/id/path to
  pdfdrill; it downloads (cached) and resolves. `pdfdrill <cmd> 2501.06699` works.
- ❌ Read/parse/edit a `.tex` or `.tgz` by hand. The sanctioned LaTeX entry points
  are `pdfdrill latex` / `model` / `latexbook` / `bibsource` — they do it for you.
- ❌ OCR, crop, do layout analysis, or transcribe math from a rendered page with your
  own tools — and that includes a `tesseract` your machine happens to carry (container
  images ship one next to texlive and LibreOffice). pdfdrill runs NO OCR engine; a
  reading comes from a LANE. Use `pdfdrill gemmaocr` (metered) /
  `pdfdrill gemmaocr --geometry-only` (free, offline: a box per line, no words) /
  `visionocr` / `snip` / `mathpix` / `rasterize`. `pdfdrill ocr` is RETIRED and only
  prints the lane it was replaced by.
- ❌ Hand-roll a `lines.json` by linearising equations (yields flattened, unusable
  LaTeX — see `pdfdrill mathcheck`).
- ❌ Invent a state transition. If a command reports a prerequisite is missing,
  satisfy it with the named command — don't skip ahead.

The ONLY exception: the user explicitly tells you to bypass pdfdrill.

## The pipeline (allowed transitions)

```
<pdf/url/arxiv-id>
   → preflight --ack # ONCE per working directory. Every BUILD command below is
   │                 #   blocked until you ack the SKILL token (the DRILL-… line
   │                 #   just before PREFLIGHT-TOKEN:END). size/route/links/doctor
   │                 #   stay open, so you can always reach this.
   → size            # text-layer vs scan; sets needs_ocr
   → route           # the lane, from docs/LANES.md: five in a FIXED order —
   │                 #   own text layer (free) → arXiv author's LaTeX (free) →
   │                 #   gemma (metered) → mathpix (paid) → geometry-only (free).
   │                 #   PAGE COUNT SELECTS NOTHING: the old scan≤20p→Gemma /
   │                 #   >20p→MathPix threshold is gone. OCR is the last resort.
   → model           # builds the docmodel from a lines.json (auto-acquires it);
   │                 #   records model_caps = {geometry, math, source}
   ├─ report / compare / mathir / mathcheck   # need MATH
   ├─ inspect / locate                        # need GEOMETRY
   ├─ md / llmtext / context / tiddlers        # text projections (codegen)
   ├─ okf [--semantic] / distill               # bundle + distill-HTML reading views
   ├─ scikgtex / stex / lean                   # LaTeX / sTeX / Lean 4 targets
   ├─ reconcile                               # dual-route: fix pdfminer math w/ MathPix
   ├─ repoinit + publish                       # package the set as a GitHub-repo TiddlyWiki
   └─ semantic / gaps / classify / ask / retrieve
```

- **Publish to GitHub Pages:** `pdfdrill repoinit` + `pdfdrill publish` build the
  repo folder (tiddlers/ + files/ + tiddlywiki.info); the `docset-publish` SKILL
  does build→tar in the Claude.ai sandbox (tar-only — the user pushes from their
  own machine, no sandbox credentials).

**Allowed:** `pdf → size → route → model → {report|compare|inspect|tiddlers|md|
llmtext|context|okf|distill|scikgtex|stex|lean}` (all codegen off the one model),
with `preflight --ack <TOKEN>` done once before the first build command.
**Forbidden:** `pdf → inspect` (no model yet), or `inspect` on a model with no
geometry — see below.

## Model SPECIES — the trap that causes wrong results

`model` is ONE command but yields **four incompatible species**, only some of which
carry page geometry:

| source | geometry (boxes) | math (typed eqs) | how it arises |
|---|:---:|:---:|---|
| `mathpix`         | ✅ | ✅ | MathPix key / cached lines.json |
| `pdfminer` / `pdfplumber` | ✅ | ⚠️ garbled | keyless born-digital text layer |
| `latex` (arXiv source) | ❌ | ✅ gold | keyless arXiv e-print |
| `gemmaocr`        | ✅ | ✅ | the model lane, METERED (~0.000718 EUR/printed page) |
| `gemmaocr --geometry-only` | ❌ | ❌ | FREE + offline: a box and a type per line, NO words |

`pdfdrill model` records this as `model_caps` in the sidecar. So:
- **`inspect` / `locate` need GEOMETRY.** On a `latex`-source model (no geometry)
  `inspect` will TELL you: *"no page geometry — rebuild via mathpix/ocr."* Do exactly
  that; do **not** improvise boxes.
- **`report` / `compare` need MATH.** A text-only model has 0 equations and
  sets `NEEDS_VISION_OCR` — run `visionocr`, don't present it as complete.

Check `pdfdrill status <pdf>` for the species/caps before assuming a command will work.

## ESCAPE LADDER — when a delegated page image is hard to read

Do NOT drift to `texsrc/` or hallucinate LaTeX. The sanctioned moves, in order:
1. **crop tighter, same image** — `pdfdrill snip <pdf> --page N --rect x0,y0,x1,y1
   [--ppi 300]`, then Read the crop again.
2. **ingest what you COULD read** — `pdfdrill visionocr <pdf> --ingest partial.json`
   (a JSON array of `{page,number,latex,kind}`). Partial is fine.
3. **report the rest as PENDING** — the unread pages stay queued in
   `<pdf>.drill/llm/`. Say "N eq_ocr requests pending" and STOP. A re-run under
   Claude Code, or a MathPix/Novita key, completes them. **A partial honest result
   beats an invented one.**

## Discovery / where to look

- `SKILL.md` — the full command surface (~100 typed commands) + the anti-patterns.
- `pdfdrill doctor` — prerequisites present/missing + the exact install line.
- `pdfdrill steps <cmd> <pdf>` — the prerequisite chain for a target command.
- `pdfdrill <cmd>` with no/short args prints its own usage.
- Every command returns **prose** — quote it back; don't re-derive it.

## On error

Report the command's message verbatim, then take the next valid transition it names
(e.g. "no geometry → run `gemmaocr --geometry-only` (free) or `mathpix` (paid) →
`model --force` → `inspect`"; `ocr` is RETIRED and reads nothing). Never substitute your own
extraction. If no valid transition exists (e.g. a math paper with no LaTeX source
and no MathPix key), say so and wait for the key/route — as the user instructed.
