#!/usr/bin/env bash
# =============================================================================
# pdfdrill — Claude CLI capability test for the keyless LLM-delegation fallback
# =============================================================================
# Verifies that a given Claude model, invoked via `claude -p`, is good enough to
# REPLACE the hosted providers pdfdrill normally calls:
#
#   * Perplexity Sonar  -> must WEB-SEARCH and compose a CORRECT BibTeX record
#   * OpenAI GPT-4o      -> must do MORE THAN OCR: read a crop and emit valid
#                           LaTeX / tikz-cd (knowledge of LaTeX, not pixels)
#
# It also smoke-tests that `claude -p ... --output-format json` works at all.
#
# The prompts under test are pdfdrill's OWN prompts (pulled live from the repo),
# not paraphrases — the prompt IS the knowledge being validated.
#
# Usage:
#   ./claude_capability_test.sh [MODEL]
# e.g.
#   ./claude_capability_test.sh                 # default model `claude` uses
#   ./claude_capability_test.sh claude-opus-4-8
#   ./claude_capability_test.sh claude-sonnet-4-6
#   ./claude_capability_test.sh claude-haiku-4-5-20251001
#
# Requirements: claude CLI (logged in or ANTHROPIC_API_KEY), python3, pdflatex,
# pdftoppm, and the pdfdrill repo (run from its root, or set PDFDRILL_SRC).
# =============================================================================
set -uo pipefail

MODEL="${1:-}"
MODEL_FLAG=(); [ -n "$MODEL" ] && MODEL_FLAG=(--model "$MODEL")
SRC="${PDFDRILL_SRC:-$(pwd)/src}"
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
PASS=0; FAIL=0
say() { printf '%s\n' "$*"; }
ok()  { PASS=$((PASS+1)); say "  [PASS] $*"; }
no()  { FAIL=$((FAIL+1)); say "  [FAIL] $*"; }

command -v claude  >/dev/null || { say "claude CLI not found on PATH"; exit 2; }
command -v python3 >/dev/null || { say "python3 not found"; exit 2; }
say "Model under test: ${MODEL:-<default>}"
say "pdfdrill src:     $SRC"
say ""

# Pull pdfdrill's REAL prompts so we test the actual knowledge.
export PYTHONPATH="$SRC"
VISION_PROMPT="$(python3 -c 'from pdfdrill import openai_vision as o; print(o.DEFAULT_PROMPT)')" \
  || { say "cannot import pdfdrill.openai_vision (set PDFDRILL_SRC)"; exit 2; }
BIB_PROMPT="$(python3 - <<'PY'
from pdfdrill import perplexity_client as p
print(p.bibtex_prompt("vaswani2017","Vaswani, A. et al.","2017",
      "Attention Is All You Need",
      "Vaswani et al. Attention is all you need. Adv. Neural Inf. Process. Syst. 2017."))
PY
)"

# Helper: run claude -p, return the .result string from the JSON envelope.
claude_result() {  # $1 prompt  $2..N extra flags
  local prompt="$1"; shift
  claude -p "$prompt" --output-format json "${MODEL_FLAG[@]}" "$@" 2>/dev/null \
    | python3 -c 'import sys,json; print(json.load(sys.stdin).get("result",""))'
}

# -----------------------------------------------------------------------------
say "[0] smoke: claude -p returns a parseable JSON envelope"
SMOKE="$(claude_result 'Reply with exactly the token READY and nothing else.')"
case "$SMOKE" in *READY*) ok "claude -p --output-format json works";;
                 *) no "claude -p smoke failed (got: ${SMOKE:0:60})";; esac

# -----------------------------------------------------------------------------
say ""
say "[1] VISION: read a commutative diagram crop -> tikz-cd (more than OCR)"
cat > "$WORK/cd1.tex" <<'TEX'
\documentclass[border=8pt]{standalone}
\usepackage{tikz-cd}
\begin{document}
\begin{tikzcd}
A \arrow[r, "f"] \arrow[d, "g"'] & B \arrow[d, "h"] \\
C \arrow[r, "k"'] & D
\end{tikzcd}
\end{document}
TEX
( cd "$WORK" && pdflatex -interaction=nonstopmode -halt-on-error cd1.tex >/dev/null 2>&1 \
  && pdftoppm -png -r 200 cd1.pdf cd1 >/dev/null 2>&1 && mv cd1-1.png cd1.png )
if [ -f "$WORK/cd1.png" ]; then
  VRES="$(claude_result "Read the image file at $WORK/cd1.png and analyse it.

$VISION_PROMPT" --allowedTools Read)"
  # grade: a JSON object naming a diagram selector with all 4 nodes + 4 edge labels
  echo "$VRES" > "$WORK/vres.txt"
  python3 - "$WORK/vres.txt" <<'PY'
import sys, json, re
raw = open(sys.argv[1]).read().strip()
raw = re.sub(r'^```[a-z]*\n?|\n?```$', '', raw).strip()
try:
    o = json.loads(raw[raw.find('{'):raw.rfind('}')+1])
except Exception as e:
    print("PARSE_FAIL", e); sys.exit(3)
sel = o.get("selector","")
code = (o.get("commutative_diagram") or o.get("tikzpicture") or o.get("math") or "")
nodes = all(n in code for n in ("A","B","C","D"))
edges = sum(l in code for l in ("f","g","h","k"))
print("SELECTOR", sel)
print("NODES_OK", nodes)
print("EDGES_FOUND", edges)
sys.exit(0 if (sel in ("commutative_diagram","tikzpicture") and nodes and edges>=3) else 4)
PY
  GR=$?
  SEL=$(grep '^SELECTOR' "$WORK"/. 2>/dev/null); :
  if [ $GR -eq 0 ]; then ok "vision produced a valid tikz-cd (4 nodes, >=3 labelled arrows)"
  else no "vision output not a usable diagram (see below)"; sed 's/^/      /' "$WORK/vres.txt" | head -12; fi
  # optional strict check: recompile what the model emitted
  python3 - "$WORK/vres.txt" > "$WORK/emit.tex" <<'PY'
import sys,json,re
raw=open(sys.argv[1]).read().strip(); raw=re.sub(r'^```[a-z]*\n?|\n?```$','',raw).strip()
o=json.loads(raw[raw.find('{'):raw.rfind('}')+1])
code=o.get("commutative_diagram") or o.get("tikzpicture") or ""
print(r"\documentclass[border=8pt]{standalone}\usepackage{tikz-cd}\usepackage{tikz}\begin{document}")
print(code); print(r"\end{document}")
PY
  if ( cd "$WORK" && pdflatex -interaction=nonstopmode -halt-on-error emit.tex >/dev/null 2>&1 ); then
    ok "emitted diagram code COMPILES with pdflatex"
  else no "emitted diagram code does not compile (model knows the shape but not valid LaTeX)"; fi
else
  no "could not render the test fixture (need pdflatex + tikz-cd + pdftoppm)"
fi

# -----------------------------------------------------------------------------
say ""
say "[2] BIBTEX: web-search a truncated reference -> correct BibTeX"
# Needs the web search tool. Tool name may be WebSearch (Claude Code).
BRES="$(claude_result "$BIB_PROMPT" --allowedTools "WebSearch WebFetch")"
echo "$BRES" > "$WORK/bres.txt"
python3 - "$WORK/bres.txt" <<'PY'
import sys, re
raw = open(sys.argv[1]).read()
m = re.search(r'```(?:bibtex)?\s*([\s\S]*?)```', raw, re.I) or re.search(r'(@\w+\{[\s\S]*?\n\})', raw)
bib = (m.group(1) if m else raw).strip()
def field(n): 
    m = re.search(n+r'\s*=\s*[{"]([^}"]*)', bib, re.I); return (m.group(1) if m else "")
year   = field("year")
pages  = field("pages")
nand   = bib.count(" and ")          # 8 authors -> 7 ' and '
checks = {
  "entry is @inproceedings/@article": bool(re.match(r'\s*@(inproceedings|article|inbook|incollection)', bib, re.I)),
  "year == 2017": year.strip()=="2017",
  ">=6 authors recovered (was 'et al.')": nand>=5,
  "pages 5998--6008": "5998" in pages and "6008" in pages,
  "Polosukhin recovered (hidden author)": "Polosukhin" in bib,
}
for k,v in checks.items(): print(("PASS" if v else "FAIL"), k)
import sys; sys.exit(0 if all(checks.values()) else 5)
PY
if [ $? -eq 0 ]; then ok "BibTeX is correct AND web-search recovered hidden fields"
else no "BibTeX incomplete/incorrect — model likely did not web-search"; sed 's/^/      /' "$WORK/bres.txt" | head -16; fi

# -----------------------------------------------------------------------------
say ""
say "============================================================"
say "RESULT for model '${MODEL:-<default>}':  $PASS passed, $FAIL failed"
say "A model that passes [1] (incl. compile) and [2] is a valid"
say "drop-in for openai_vision and perplexity_client via delegation."
say "============================================================"
[ $FAIL -eq 0 ]
