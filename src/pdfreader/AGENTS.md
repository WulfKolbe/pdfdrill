# pdf2mmd

PDF to Markdown converter with LaTeX support for born-digital PDFs.

## Resume Session

```bash
./resume.sh
```

## Quick Start

```bash
./install.sh                    # Install patched pdfminer.six
./pdf2mmd.sh book.pdf           # Convert PDF
./pdf2mmd.sh book.pdf 1-20      # Convert page range
```

## Install

```bash
./install.sh                    # Full install (check deps, build venv, run tests)
./install.sh --check            # Check files only
./install.sh --rebuild          # Force rebuild venv
./install-pdfminer-fork.sh      # Build patched pdfminer only
```

Requirements: `python3` (3.10+), `git`, `ghostscript`

## Tests

```bash
.pdfmm-venv/bin/python -m pytest -q
```

Tests needing real PDFs skip themselves (62 passed, 49 skipped in clean install).

Full test suite with fixtures:
```bash
PDF2MMD_TEST_PDF=/path/to/book.pdf \
PDF2MMD_TEST_LINES=/path/to/book.lines.json \
.pdfmm-venv/bin/python -m pytest -q
```

## Key Files

| File | Purpose |
|------|---------|
| `pdf2mmd.sh` | Entry point |
| `pdf2mmd.py` | Driver |
| `docmodel_six.py` | Document model (glyphs, rules, lines, spans) |
| `structure.py` | Fractions and scripts |
| `listings.py` | Code-listing grid, frame rectangle, style table |
| `pageprofile.py` | Page properties with evidence (listing, inline-code, frame…) |
| `lstlangs.py` | listings' own keyword lists, for naming the language |
| `texmap.py` | Glyph identity → LaTeX |
| `project_mmd.py` | Markdown/LaTeX output, headings, links |

## Architecture

- Venv at `.pdfmm-venv/` (patched pdfminer.six)
- Output goes to `mmd-out/` unless specified
- Requires Ghostscript for crop/render tools
- All files must be in one folder (they import each other by name)

## Dev Commands

```bash
bun run opencode                    # Start OpenCode session
bun run opencode --run-id <id>     # Resume specific session
```
