# Prompt to paste into Claude.ai

Use this after attaching `pdfdrill.tgz` (or after cloning the repo) in a
Claude.ai chat. It tells Claude how to run the tool correctly and, crucially,
how to answer math questions **without cheating** (no transcribing equations
from the rendered page).

---

You have the `pdfdrill` toolkit (attached as `pdfdrill.tgz`, or cloned from my
private GitHub `WulfKolbe/pdfdrill`). Set it up and use it as the ONLY way to
read math from PDFs — do not transcribe equations from your own reading of the
page or from an uploaded Markdown rendering; that is unreliable and counts as
cheating.

Setup (no install, no keys to enter — keys are bundled in the repo):

    mkdir -p pdfdrill && tar -xzf pdfdrill.tgz -C pdfdrill   # skip if cloned
    cd pdfdrill
    export PYTHONPATH=src
    python3 -m pdfdrill size <pdf>     # sanity check

Rules:

1. NEVER ask me for a MathPix or Perplexity key. They are already configured
   (`src/pdfdrill/*_creds.py`). If you hit "credentials not found", you forgot
   `export PYTHONPATH=src` — fix that, don't ask for a key.

2. For "where is the code / repo / dataset?": run
   `python3 -m pdfdrill links <pdf>` — it reads the PDF annotation layer (the
   URL is often a hyperlink with no visible anchor text).

3. For "show me equation N" or any formula: do NOT typeset it yourself. Run

       python3 -m pdfdrill model  <pdf>     # offline if <name>.lines.json exists;
                                            # else fetches it via the bundled key
       python3 -m pdfdrill report <pdf>     # writes <pdf>.drill/formula-report.html

   Then open `formula-report.html` and find the equation's row. Give me:
   - the **LaTeX source** (verbatim, from the report), and
   - the **MathPix CDN image URL** (`https://cdn.mathpix.com/cropped/…`) for
     that row, as proof.
   The rendered math you show me must be either a KaTeX node (rendered from the
   report's `data-latex`) or that CDN image. If it is neither, you fabricated it
   — redo it from the report.

4. Prefer the cheapest sufficient command; the structural path
   (`model`/`compare`/`report`/`tiddlers`/`folder`) is fully offline.

Confirm setup by telling me the page count from `pdfdrill size`, then wait for
my question.
