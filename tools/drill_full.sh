#!/usr/bin/env bash
#
# drill_full.sh — process ONE document so that everything ends up in the
# Markdown and the Tiddlers.
#
# Written for an auditing chat that presents its results as TiddlyWiki: run
# this, then read `<key>.md` and import `<key>.tiddlers.json`. Everything the
# audit needs is in those two artefacts.
#
#   bash tools/drill_full.sh <pdf|url|arxiv-id> [bibkey]
#
# ORDER MATTERS, and not always in the obvious way. The dependencies that are
# easy to get wrong are marked WHY at each step; the rest is a straight line.
#
# Nothing here is paid or networked EXCEPT `mathpix` (skipped unless
# MATHPIX_APP_ID is set) and `injectlatex` (downloads the free arXiv e-print).
set -uo pipefail            # NOT -e: a document without tables must not abort
                            # the run; each step reports and we continue.

DOC="${1:?usage: drill_full.sh <pdf|url|arxiv-id> [bibkey]}"
BIBKEY="${2:-}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONPATH="$REPO/src"
export PDFDRILL_NO_PREFLIGHT=1        # the SKILL attestation gate is for agents

# The two knobs the SANDBOX copy sets (tools/drill_full_sandbox.sh, which is a
# wrapper around THIS file — one script, two entry points, so the recording
# machinery below cannot drift between them).
#   DRILL_LOAD_ENV=1        source $REPO/.env into the SHELL. pdfdrill reads
#                           .env internally, but this script's own guards test
#                           the shell environment, so without this
#                           `[ -n "${MATHPIX_APP_ID:-}" ]` never fires.
#   DRILL_MATHPIX_NO_FORCE=1  never `mathpix --force` when <doc>.lines.json is
#                           already cached; --force re-uploads and re-charges.
if [ "${DRILL_LOAD_ENV:-0}" = 1 ] && [ -f "$REPO/.env" ]; then
  set -a; . "$REPO/.env"; set +a
fi

PD=(python3 -m pdfdrill)
KEYARG=(); [ -n "$BIBKEY" ] && KEYARG=(--bibkey "$BIBKEY")

# ---------------------------------------------------------------------------
# RECORDING. `set -e` stays off on purpose (a document without tables must not
# abort the run) — but a run WITH failures must be impossible to mistake for a
# clean one (HANDOVER-RULES rule 11: a masked success reads exactly like a
# masked failure). So every step is timed, its full output is teed to
# `<doc_dir>/drill_full.log` under its label (a traceback that scrolls past is
# a traceback that is gone), every failure is recorded with its exit code and
# the last 3 lines of its output, and the run ends with a STEP TABLE, a
# `== FAILED STEPS ==` block, and exit 1 when anything failed.
# ---------------------------------------------------------------------------
if [ -f "$DOC" ]; then
  DOC_DIR="$(cd "$(dirname "$DOC")" && pwd)"
else
  DOC_DIR="$PWD"                      # URL / arXiv id: no doc folder yet
fi
LOG="$DOC_DIR/drill_full.log"
printf '\n=== drill_full %s  %s\n' "$DOC" "$(date -Is)" >>"$LOG"

STEP_LABELS=(); STEP_RCS=(); STEP_SECS=(); STEP_TAILS=()
FAIL_IDX=()

step() {                              # step "label" cmd args...
  local label="$1"; shift
  local t0 rc tmp
  printf '\n\033[1m== %s\033[0m\n' "$label"
  t0=$SECONDS
  tmp="$(mktemp)"
  # tee, so the operator still watches it live AND the traceback survives.
  # PIPESTATUS[0], not $?, is the STEP's exit code (rule 11: the inkdrill
  # session was bitten twice by exit-code-masking pipes).
  "$@" 2>&1 | tee "$tmp"
  rc=${PIPESTATUS[0]}
  { printf '\n----- %s (rc=%d) -----\n' "$label" "$rc"; cat "$tmp"; } >>"$LOG"
  STEP_LABELS+=("$label"); STEP_RCS+=("$rc"); STEP_SECS+=("$((SECONDS - t0))")
  STEP_TAILS+=("$(tail -3 "$tmp")")   # parallel to STEP_LABELS, always appended
  if [ "$rc" -ne 0 ]; then
    FAIL_IDX+=("$(( ${#STEP_LABELS[@]} - 1 ))")
    printf '   \033[1m(step FAILED rc=%d\033[0m — continuing; later steps degrade rather than stop)\n' "$rc"
  fi
  rm -f "$tmp"
}

# Printed at the very end, by `summarise`, which is the ONLY thing that decides
# whether this run was clean. Tested on a real success AND a real failure
# (tests/test_drill_full_sh.py) — a summariser that can only see one of them
# sees neither.
summarise() {
  local i n_fail=${#FAIL_IDX[@]}
  printf '\n\033[1m== STEP TABLE ==\033[0m\n'
  printf '%-56s %4s %6s\n' 'STEP' 'RC' 'SECS'
  for i in "${!STEP_LABELS[@]}"; do
    printf '%-56s %4s %5ss\n' "${STEP_LABELS[$i]}" "${STEP_RCS[$i]}" "${STEP_SECS[$i]}"
  done
  if [ "$n_fail" -eq 0 ]; then
    printf '\nAll %d steps succeeded. Full output: %s\n' "${#STEP_LABELS[@]}" "$LOG"
    return 0
  fi
  printf '\n\033[1m== FAILED STEPS (%d of %d) ==\033[0m\n' "$n_fail" "${#STEP_LABELS[@]}"
  for i in "${FAIL_IDX[@]}"; do
    printf '  %s   (rc=%s)\n' "${STEP_LABELS[$i]}" "${STEP_RCS[$i]}"
    printf '%s\n' "${STEP_TAILS[$i]:-(no output)}" | sed 's/^/      | /'
  done
  printf '\nfull output (all steps, with tracebacks): %s\n' "$LOG"
  return 1
}

# ---------------------------------------------------------------------------
# 1. TRIAGE — cheapest first. `size` decides born-digital vs scan and, with the
#    producer, which extraction lane is even allowed.
# ---------------------------------------------------------------------------
step "size"   "${PD[@]}" size  "$DOC"
step "route"  "${PD[@]}" route "$DOC"

# ---------------------------------------------------------------------------
# 2. ACQUIRE the text layer.
#    MathPix is the richest source (page geometry + LaTeX + CDN crops) but is
#    PAID, so it runs only when credentials exist. Without it `model` falls
#    through to the free routes by itself.
# ---------------------------------------------------------------------------
if [ -n "${MATHPIX_APP_ID:-}" ]; then
  if [ "${DRILL_MATHPIX_NO_FORCE:-0}" = 1 ] && ls "${DOC%.pdf}".lines.json >/dev/null 2>&1; then
    # --force re-uploads and re-charges. Only force when nothing is cached.
    step "mathpix (cached — no re-upload)" "${PD[@]}" mathpix "$DOC"
  else
    step "mathpix (paid; --force because arXiv is skipped by default)" \
         "${PD[@]}" mathpix "$DOC" --force
  fi
else
  echo -e "\n== mathpix: SKIPPED (no MATHPIX_APP_ID) — free routes will be used"
fi

step "model" "${PD[@]}" model "$DOC" "${KEYARG[@]}"

# ---------------------------------------------------------------------------
# 3. GOLD LaTeX. WHY BEFORE expandmath: `injectlatex` caches the arXiv e-print,
#    and that cache is where the MACRO TABLE comes from. Without it
#    `expandmath` has nothing to expand with and says so.
# ---------------------------------------------------------------------------
step "injectlatex (free arXiv e-print; gold equations + the macro table)" \
     "${PD[@]}" injectlatex "$DOC"

# ---------------------------------------------------------------------------
# 4. STRUCTURE. Each writes into the model; all are offline and idempotent.
# ---------------------------------------------------------------------------
step "eqnums     (equation numbers)"      "${PD[@]}" eqnums     "$DOC"
step "lists      (nested list objects)"   "${PD[@]}" lists      "$DOC"
step "algorithms (pseudocode blocks)"     "${PD[@]}" algorithms "$DOC"
step "annotate   (link annotations)"      "${PD[@]}" annotate   "$DOC"

# ---------------------------------------------------------------------------
# 5. BIBLIOGRAPHY. `bibsource` is authoritative when the author's .bbl/.bib is
#    cached (injectlatex just fetched it); it DROPS the heuristic references
#    first, so run it BEFORE `bibliography`, not after.
# ---------------------------------------------------------------------------
step "bibsource   (author .bbl/.bib — authoritative)" "${PD[@]}" bibsource   "$DOC"
step "bibliography (heuristic fallback + citation linking)" \
     "${PD[@]}" bibliography "$DOC"

# ---------------------------------------------------------------------------
# 6. CLEAN. Lifts stray footnotes into Footnote objects, strips heading
#    residuals, and MATERIALISES transclusions into props["text"] — which is
#    what makes `md`/`llmtext`/`spoken` agree with the tiddlers.
#    WHY HERE: it rewrites prose, so it must precede every projection.
# ---------------------------------------------------------------------------
step "clean" "${PD[@]}" clean "$DOC"

# ---------------------------------------------------------------------------
# 7. MATH -> SPEECH.
#    expandmath persists the fully macro-expanded LaTeX; speak renders it.
#    WHY THIS ORDER: latex2mathml has NO macro table, so an unexpanded macro
#    reaches the engine verbatim and is spoken as its letters.
# ---------------------------------------------------------------------------
step "expandmath (persist expanded + original LaTeX)" "${PD[@]}" expandmath "$DOC"
step "speak      (math -> spoken, stored on each object)" "${PD[@]}" speak "$DOC"

# ---------------------------------------------------------------------------
# 8. GRAPHICS. WHY BEFORE tiddlers: `svg` attaches the rendered SVG to each
#    Diagram/Table, and the tiddler projector embeds whatever is attached AT
#    THE TIME IT RUNS. Run it after, and the tiddlers have no images.
# ---------------------------------------------------------------------------
step "svg (TikZ/tables -> SVG; needs latex + dvisvgm)" "${PD[@]}" svg "$DOC"

# ---------------------------------------------------------------------------
# 9. THE TWO ARTEFACTS THE AUDIT READS.
# ---------------------------------------------------------------------------
step "md       (canonical Markdown)"  "${PD[@]}" md       "$DOC"
step "tiddlers (the wiki)"            "${PD[@]}" tiddlers "$DOC" "${KEYARG[@]}"

# ---------------------------------------------------------------------------
# 10. SIDE PROJECTIONS — useful to the audit, not needed by the wiki.
#     `spoken` is the text an LLM is actually fed; `formulas`/`sre` expose the
#     math layer; `report` is the human-readable formula report.
# ---------------------------------------------------------------------------
step "spoken   (the LLM INPUT text)" "${PD[@]}" spoken   "$DOC"
step "formulas (math projection)"    "${PD[@]}" formulas "$DOC"
step "report   (formula report)"     "${PD[@]}" report   "$DOC"

# ---------------------------------------------------------------------------
# 11. WHAT WAS PRODUCED
# ---------------------------------------------------------------------------
step "artifacts" "${PD[@]}" artifacts "$DOC"
step "status"    "${PD[@]}" status    "$DOC"

cat <<'NOTE'

--------------------------------------------------------------------------
For the audit:
  <key>.md                the canonical Markdown
  <key>.tiddlers.json     import into TiddlyWiki (drag & drop the file)
  <key>.spoken.txt        the text an LLM is actually fed
  <key>.formulas.json     every formula: latex, latex_original, placeholder,
                          unresolved macros
Both `md` and the tiddlers are rebuilt from the SAME model, so a discrepancy
between them is a projector bug; a defect present in BOTH is a model bug.
That distinction is usually the fastest way to locate a fault.
--------------------------------------------------------------------------
NOTE

# ---------------------------------------------------------------------------
# 12. THE VERDICT. Last thing on screen, and the exit code.
# ---------------------------------------------------------------------------
summarise
