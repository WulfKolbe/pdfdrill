# Using pdfdrill on Claude.ai (private, install-free)

The repo is **private**, and Claude.ai's GitHub file-source list currently does
not show it (other repos show fine — cause unknown, likely indexing lag). Until
that resolves you do **not** need the GitHub connector. Two install-free ways
to run pdfdrill in a Claude.ai chat:

## Option 1 — upload a bundle (recommended)

On your machine:

```bash
cd ~/MX/PDFDRILL
git archive --format=tar.gz -o /tmp/pdfdrill.tgz HEAD     # tracked files only
#  -> includes the bundled keys (private use); excludes data/, .codegraph, pyc
```

Attach `/tmp/pdfdrill.tgz` to the Claude.ai chat, then paste the prompt in
`docs/PROMPT_FOR_CLAUDE_AI.md`. Claude extracts it and runs everything with
`PYTHONPATH=src` — **no pip install, no key setup** (keys ship in the bundle).

## Option 2 — clone with a token (if the connector still hides it)

```bash
git clone https://github.com/WulfKolbe/pdfdrill.git
```

In a sandbox without your credential helper this needs a tokenized URL:
`https://<TOKEN>@github.com/WulfKolbe/pdfdrill.git` (use a fine-grained PAT with
read-only contents on this one repo; revoke after).

## Running (both options)

No install required — the package root is `src/`:

```bash
cd pdfdrill
PYTHONPATH=src python3 -m pdfdrill <command> <pdf> [args]
# e.g.
PYTHONPATH=src python3 -m pdfdrill size  paper.pdf
PYTHONPATH=src python3 -m pdfdrill model paper.pdf      # offline if lines.json exists
PYTHONPATH=src python3 -m pdfdrill report paper.pdf     # formula-report.html
```

Optional convenience: `pip install -e .` puts a `pdfdrill` command on PATH, but
it is **not** required for testing the lower function layer.

## Keys

MathPix/Perplexity keys are bundled in `src/pdfdrill/mathpix_creds.py` and
`src/pdfdrill/perplexity_creds.py`, so `mathpix`/`snip`/`bibfetch` work with no
setup. The whole structural path needs no key at all. **Before any public
release: delete those two files and rotate the keys** (env vars still work).

## System prerequisites

- **poppler-utils** (`pdfinfo`/`pdftotext`/`pdffonts`/`pdfimages`/`pdftoppm`) —
  core; the Claude.ai sandbox already has it (`pdfplumber`/`pydantic` too).
- **tesseract-ocr** (+ `eng`/`deu`/`equ`) — the keyless OCR route (`pdfdrill ocr`).
- **LaTeX DVI toolchain + dvisvgm** (`latex`/`pdflatex`/`dvips` + `dvisvgm`,
  with `texlive-pictures`/`texlive-latex-extra` for TikZ/standalone) — the
  TikZ/table SVG route (`pdfdrill svg`, `latexbook`).

`bash bootstrap.sh` installs all of these via `apt-get` (only what's missing),
then prints a requirement check. Run that check anytime with **`pdfdrill
doctor`** — it lists which system tools / Python deps / API keys are present,
which routes they enable, and the exact `sudo apt-get install …` line to fill
any gap (e.g. the full `dvisvgm texlive-latex-base … texlive-pictures` set for
the SVG route).
