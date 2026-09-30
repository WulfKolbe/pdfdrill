# out/ — the measurement harness

Code that MEASURES the reader, kept apart from the data it measures. Nothing
in this folder contains corpus material, and nothing in it writes into this
repository.

    $PDF2MMD_LIBRARY   where the corpus is       default ~/pdfdrill-library
    $PDFDRILL_SRC      PDFDRILL's src/           default ~/MX/PDFDRILL/src
    $PDF2MMD_CODE      the reader                default the parent of this folder

The corpus (`wzlxjtu-*`, each with its `golden/`) is licensed to TEES, Texas
A&M — "not to be reproduced or disclosed without written authorization". It
lives outside this repository and must stay there. So does every build these
scripts produce.

## What is here

| | |
|---|---|
| `corpusrun.py` | run the reader over all 102 documents, and install the result |
| `sweep.py` | which gold equations are not reproduced, and the refusals behind them |
| `canon.py` | the dialect-aware comparison: is this reading right, however spelled |
| `eqtable_716.py` | the four-column table — No, gold, MathPix, pdf2mmd |
| `test_table.py` | the table pipeline, fed deliberately malformed elements |
| `lstscore.py` | the LISTING gold set read back and scored — the peer of `canon.py` |
| `lstroundtrip.py` | LaTeX → PDF → pdf2mmd → LaTeX → PDF → pdf2mmd: does the projection re-read? |
| `lstgoldcheck.py` | is the gold set sound — errors, and how much of each page IS the listing |
| `lstprobe.py` | the frame probe: one body, every frame style, with and without an image |
| `gridguard.py` | can the monospace grid be seen from LINE geometry alone — measured for MathPix |
| `profilerun.py` | the page profile over a folder — which pages carry what, and what a paid pass would bill |
| `lstlang.py` / `langdetect.py` | language guessing, measured against the declared gold |

## The loop

```bash
cd ~/pdf2mmd/out

python3 corpusrun.py /tmp/run --install     # 1. convert, and install
python3 sweep.py                            # 2. what is still missing
python3 canon.py                            # 3. correct / arranged / wrong
python3 eqtable_716.py                      # 4. the table, to look at
```

Step 1 writes to a scratch directory and, with `--install`, copies each
document's output to `<doc>/pdf2mmd/page.md` in the library. **Steps 2–4 read
only the library.** A run you have not installed cannot change a measurement
by accident — which is the point of the separation.

## Building the 716 table, in detail

```bash
python3 eqtable_716.py                               # default output path
python3 eqtable_716.py --out /somewhere/table.tex    # elsewhere
python3 eqtable_716.py --no-compile                  # .tex only
python3 eqtable_716.py --no-unmatched                # omit the per-document
                                                     # table of blocks that
                                                     # match no gold equation
```

Blocks matching no gold equation are shown BY DEFAULT, in a small table of
their own after each document's. They used to be counted in the caption and
not shown, and 61 of them (MathPix 8, pdf2mmd 53) never appeared anywhere:
a reader looking for a document's Nth equation found N-1 rows and no sign of
the rest. Counted is not shown. They are kept out of the main table because
every row there exists to be read ACROSS -- gold beside the two readings of
it -- and a row with an empty gold column breaks that run.

Run `python3 -m pytest test_table.py -q` after changing anything in this
folder. It feeds unbalanced braces, an unpaired `\left`, a comment
character, a parameter character, a subscript in text mode, an empty block
and a 4000-character line through the whole chain, and asserts the two
properties the instrument depends on: every gold equation gets a row, and
every block a source emitted is either matched or listed.

It writes `716-equations.tex` and compiles it to `716-equations.pdf`. Five
things happen, in this order:

1. **Read three sources per document.** Gold from `golden/*_gt.tex` — eleven
   display environments occur in this corpus and all are taken, plus `\[..\]`
   and a `center` block whose content is mathematics. MathPix from
   `<slug>.md`. This reader from `pdf2mmd/page.md`.

2. **Match by CONTENT, never by position.** The three sources do not agree on
   how many blocks an equation is, so the Nth block of one is not the Nth of
   another. `key()` normalises spelling — `\mid` for `|`, `{a\over b}` for
   `\frac{a}{b}`, font commands and spacing away — and every gold equation
   takes its best unit above 0.35 similarity. A unit is a whole block OR one
   row of an `aligned`, because a fused run can hold several authored
   equations. Greedy, highest ratio first, each unit claimed once.

3. **Judge every cell on its own.** Each `$\displaystyle …$` is set alone in
   a probe document and compiled; a line number is then a cell. Only the
   FIRST erroring line of a pass is a verdict — TeX cascades — so that cell
   is dropped and the probe runs again. A cell that fails is shown as its
   SOURCE, marked, never as a blank: an empty cell that means "did not
   render" is indistinguishable from one that means "nothing was read", and
   that confusion is what this table exists to prevent.

4. **Compile to a fixpoint.** `report_tex.compile_fixpoint` demotes any row
   that still errors and recompiles. After step 3 there is normally nothing
   left to demote; `compile: (pages, errors, demoted)` should end `, 0)`.

5. **Stamp it.** Page 1 carries the reader's commit and the build time, so a
   table and the code that made it can be matched at a glance.

### What it needs

- `pdfdrill.report_tex` from the PDFDRILL repository, for the preamble and
  the compile fixpoint. That is the only cross-repository dependency; point
  `$PDFDRILL_SRC` at it.
- `xelatex`. Not pdflatex — the output carries real Unicode.

### Reading the result

`gold N; matched MathPix m, pdf2mmd p; unmatched blocks …` per document. A
dash means that source produced nothing for that equation. `no match` means
the source produced blocks but none of them is this equation. Neither ever
means the sources agree.


## The listing gold set

`~/pdfdrill-library/lstgold/` — 307 listings from 39 documents, each ONE
`lstlisting` taken from an AUTHOR'S OWN e-print and reduced to what
reproduces it: the listings preamble (`\definecolor`, `\lstset`,
`\lstdefinestyle`, `\lstdefinelanguage`), the listing with its options, and
a provenance header. Every file compiles under `pdflatex`; the 21 candidates
that did not are excluded and the reasons are in its README.

Built the same way as the math set and read the same way: the gold is the
question, the page is the answer.

```bash
python3 lstscore.py --limit 20     # compile, read back, score
```

`lstscore` is dialect-aware for three things the PAGE does and the reader
must follow — `numbers=left` really does print `1 `, `2 ` at the start of
each line; `escapechar` marks LaTeX that never reaches the page at all; and
`breaklines=true` wraps, so the wrapped form IS the page. Indentation is not
on that list: leading whitespace is content, and in Python it is the block
structure, so it is compared and reported SEPARATELY — a loss there cannot
hide inside a high text score.

### Is the gold sound?

```bash
python3 lstgoldcheck.py --install
```

A PDF appearing is not evidence that a file compiled: LaTeX recovers from
nearly everything and prints the rest of the source. The builder's check
was "a PDF exists and is over 1000 bytes" and all 307 candidates passed it
while 96 compiled with errors and 23 pages did not show the listing at all
— one showed its own `\lstdefinelanguage` as body text. This asks for the
`!` lines instead, and measures how much of each rendered page is the
listing the file was built for. After repair: 39 of 291 carry errors, all
cosmetic, and no page fails to show its listing.

### The frame probe

```bash
python3 lstprobe.py
```

One body, every frame style, with and without a PNG above it — fourteen
files under `lstgold/probe/`. They are synthetic and that is the point:
with `frame=single`, `lines`, `tb`, `shadowbox` or `trBL`, pdf2mmd found
**zero** listings, because `listings` sets a framed listing line by line
and twenty marks around forty glyphs read as a dense figure, so the block
was cropped away as a diagram. `frame=none` and `leftline` worked, which is
why 291 gold listings from real papers never showed it. 4 of 14 before the
fix, 14 of 14 after.

It also carries the **external probe** (`gh/`): a `\lstinputlisting` of a
file in a cloned git repo, lines 10–25, whose caption is an `\href` to the
*commit* that contains it. The body is not in the `.tex`, the gutter starts
at 10, and the provenance is a **PDF annotation** — the commit-pinned URL
with its `#L10-L25` anchor is nowhere in the glyph stream. 16 of 16 on
text, indentation and numbering.

It also carries the **cell probe**: two listings in one `tabular` row. 52
of the 1,025 listings in the library sit in a table cell (5.1%), 43 of the
291 gold files have a cell provenance — and none of them exercises it,
because the builder lifted each listing *out* of its cell into a standalone
document. A gold set built by extraction cannot measure a defect of
containment.

### The round trip

A projection that cannot be re-read is not a projection.

```bash
python3 lstroundtrip.py            # ~25 min over the 307
```

Each gold file is compiled (generation 1), read, projected, compiled again
(generation 2) and read again. If the two readings differ, the `.tex` we
wrote does not set the page we read, and the difference names the property
that was lost. It writes `lstgold/roundtrip.json` and leaves both
generations in `lstgold/pdf/` and `lstgold/again/`.

Sources are e-prints held in the library; provenance is per file. Local
test material, not for redistribution. Nothing under `texzip/` or named
`evidence-*.tex` is used: those are MathPix's output and ours.
