# pdf2mmd — born-digital PDF → Markdown with LaTeX

## Quick start

```bash
./install.sh                          # Install dependencies and build venv
./pdf2mmd.sh /path/to/book.pdf 1-20   # Convert pages 1-20
```

`./pdf2mmd` is a plain launcher that works from any directory and needs no
arguments beyond the file:

```bash
./pdf2mmd paper.pdf              # whole document, into ./paper/
./pdf2mmd paper.pdf 1-6          # just those pages
./pdf2mmd -c paper.pdf 1-6       # and compile the .tex with xelatex
```

It exits **2** when the PDF has no text layer on those pages — a scan, which
a glyph reader cannot help with. See `USAGE.md` for the outputs and for what
the reader refuses to guess.

## Files

Put all of these in one folder. They import each other, so a partial copy
fails — `pdf2mmd.sh` checks for them by name before it starts.

**Required to convert**

| file | |
|---|---|
| `pdf2mmd.sh` | the entry point |
| `pdf2mmd.py` | driver |
| `docmodel_six.py` | the document model: glyphs, rules, lines, spans |
| `structure.py` | fractions and scripts |
| `listings.py` | the code-listing grid, its frame, and its style table |
| `pageprofile.py` | what is ON a page — properties with their evidence, for triage |
| `lstlangs.py` + `.json` | the keyword lists `listings` itself ships, for the language |
| `texmap.py` | glyph identity → LaTeX, and font-family classification |
| `project_mmd.py` | Markdown / LaTeX / crop links / headings |

**Required to install**

| file | |
|---|---|
| `install-pdfminer-fork.sh` | builds the patched pdfminer |
| `pdfminer-glyph-identity.patch` | the patch itself |

**Optional**

| file | |
|---|---|
| `inspectserver.py` | serves the crop links (and 400-dpi renders) |
| `inventory.py` | corpus analysis: what glyph names a document uses |
| `dpitopo.py` | measures glyph topology across render resolutions |
| `test_*.py` | the test suite |

## Install (once)

```bash
./install-pdfminer-fork.sh
```

Clones pdfminer.six, applies `pdfminer-glyph-identity.patch`, installs it into
an isolated venv at `./.pdfmm-venv`, and verifies the feature actually works.
**Your system pdfminer.six is untouched**, so anything pinning a released
version keeps running.

Other forms:

```bash
./install-pdfminer-fork.sh --user            # pip --user; replaces pdfminer for your user
./install-pdfminer-fork.sh --venv ~/.pdfmm   # a venv elsewhere
./install-pdfminer-fork.sh --check           # verify an existing install
```

If the venv is not at `./.pdfmm-venv`, point the converter at it:

```bash
PDFMM_PYTHON=~/.pdfmm/bin/python ./pdf2mmd.sh book.pdf
```

### Why a patch is needed at all

Stock pdfminer.six imports and runs fine and produces output with **no glyph
identity in it** — every maths symbol arrives as `(cid:N)` or, worse, as a
plausible-looking wrong character. The information is present in the PDF and
pdfminer parses it; it is discarded before reaching `LTChar`:

| discarded | consequence |
|---|---|
| the PostScript glyph name from `/Encoding /Differences` | `\star` becomes `(cid:7)` |
| the character code (`cid`) | nothing downstream can repair it |
| the text rendering mode (`Tr`) | an OCR layer is indistinguishable from typeset text |

The patch keeps them. ~160 additive lines over five files; existing behaviour
is byte-identical over 1,160,979 `LTChar` records across 57 documents.

Requirements: `git`, `python3` (with `venv`), and **Ghostscript** (`gs`).

## Convert

```bash
./pdf2mmd.sh book.pdf                    # whole document
./pdf2mmd.sh book.pdf 150-158            # a page range
./pdf2mmd.sh book.pdf 150-158 out/       # and where to put it
SERVE=1 ./pdf2mmd.sh book.pdf 150-158    # then start the crop server
```

Outputs, all projected from one docmodel so they cannot disagree:

| file | what |
|---|---|
| `<stem>.md` | Markdown, LaTeX inline, crop links where maths defers |
| `<stem>.tex` | the same content as LaTeX |
| `<stem>.lines.json` | MathPix-shaped geometry |
| `<stem>.fonts.md` | the type-size evidence behind the heading levels |
| `<stem>.report.txt` | what projected, what did not, and why |

Plus 250-dpi page images in `out/inspect/pages/`.

## Make the crop links resolve

Maths that cannot be proven becomes a crop link rather than vanishing. Start
the server to see those crops:

```bash
python3 inspectserver.py --pages out/inspect/pages \
        --lines out/book.lines.json --pdf book.pdf --port 8000
```

| route | resolution | for |
|---|---|---|
| `/cropped/<id>g-<page>.jpg?height=&width=&top_left_y=&top_left_x=` | 250 dpi, stored | looking at the page |
| `/render/p<N>.png?dpi=400` | any, Ghostscript on demand | measuring topology |
| `/pages/p<N>.png` | stored | `docinspect --image-base` |

**Do not measure topology on the 250-dpi images.** Against a 1200-dpi
reference, 250 dpi gets the component count wrong for 2.6 % of isolated glyphs
and the hole count wrong for 6.7 %; at 400 dpi that is 0.5 % and 5.2 %. A 7 pt
alpha is two components at 250 dpi and one at 400.

## Scope

Born-digital PDFs only. A page whose glyphs are all invisible (`Tr 3`) is a
scanner's OCR layer: its positions are good and its identities are another
tool's guess. `pdf2mmd` refuses those pages and names them — send them to
MathPix instead.

## What it writes, and where

Everything stays inside the install folder. Nothing is written to `/tmp`, and
no path outside the folder is read unless you name one.

| path | |
|---|---|
| `.pdfmm-venv/` | the patched pdfminer and its dependencies |
| `.pdfmm-build/` | scratch during the venv build; removed on exit |
| `mmd-out/` | conversion output, unless you pass another folder |
| `mmd-out/inspect/pages/` | 250-dpi page images |

The only thing read from elsewhere is the PDF you name on the command line.

## Tests

```bash
./.pdfmm-venv/bin/python -m pytest -q
```

Tests that need a real PDF skip themselves, so a clean install reports
something like `62 passed, 49 skipped`. To run the full set, either drop files
into `./testdata/` (`corpus.pdf`, `corpus.lines.json`, `pages/`,
`texzip-images/`) or point the environment at your own copies:

```bash
PDF2MMD_TEST_PDF=~/books/some-maths-book.pdf \
PDF2MMD_TEST_LINES=~/books/some-maths-book.lines.json \
./.pdfmm-venv/bin/python -m pytest -q
```

`testpaths.py` holds the resolution rules. No absolute path from whoever built
the toolkit appears anywhere in the shipped files.

The pdfminer patch carries its own 20 tests, which run inside the fork.
