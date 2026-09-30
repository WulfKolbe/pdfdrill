# Integrating pdf2mmd into pdfdrill

*2026-09-30. Design spec. Measured before written.*

## Why now

**The political reason, stated first because it is the real one.** People with
reach — individuals with followings, people inside organisations — have not
answered emails. The one party that always answers is MathPix, and MathPix is
the party pdf2mmd threatens. A keyless reader that matches a paid API is only
an argument if it is *part of the product*: a side tool in `~/pdf2mmd`, invoked
over a pipe, spoken of as "a separate install", is a research prototype. The
same code reached by `pdfdrill <anything>` on a fresh machine is a claim.

**The technical reason.** Three seams already cost real defects this week, and
each is a job done correctly in one program and incorrectly in the other:

| | preamble | crop images | crop id |
|---|---|---|---|
| pdf2mmd | derived from content (`texpackages.packages_for`) ✅ | emitted as `http://…` URLs, no files ❌ | `{doc_id}g-{page}` |
| pdfdrill | fixed, never reads the document's own ❌ | rendered from the PDF (824), `\graphicspath` (822) ✅ | `<uuid>-01` (MathPix-shaped) |

Measured on `arxiv.1102.1889`: pdfdrill's `evidence-equation` compiles with
**1,029 errors** (`\xymatrix` undefined — the shared preamble never loads the
document's `\input xy`); pdf2mmd's `.tex` has no preamble errors at all and
instead emits **324 of 324** `\includegraphics` as live HTTP URLs, so it
produces a PDF in `nonstopmode` with every image missing. Neither tool is
wrong about its own half. They are two halves.

And the id mismatch means the Markdown pdf2mmd writes cannot resolve against
the crop server pdfdrill's `inspect` feeds: `404`, with a helpful message
pointing at the wrong fix.

## The constraint that turns out not to be one

`commands.py` states the boundary:

> pdf2mmd is a SEPARATE INSTALL with a PATCHED pdfminer (the glyph-identity
> fork). It cannot be imported here and **must not be**: the fork is what makes
> its glyph names trustworthy, and pulling it into this environment would
> change what every other pdfminer caller in this package sees.

That is the reason the two programs are two programs. It is measurably wrong.

    pdfminer-glyph-identity.patch:  600 lines,  +461 / -0

**The patch deletes nothing.** It adds class-level `std2name` / `mac2name` /
`win2name` / `pdf2name` tables and a `get_encoding_names()` classmethod, whose
own docstring calls it *"the twin of `get_encoding`"*, and threads `cid` and
`textstate_render` through converter → device → layout. `get_encoding` — what
every existing caller uses — is untouched.

A purely additive patch cannot change what existing callers see. The 33 files
in `src/` that import pdfminer are at risk only if the patch removes or alters
behaviour, and it does neither. The boundary was drawn on a fear that the diff
refutes.

This is the single fact the whole integration rests on, and it must be
re-checked on every pdfminer upgrade, not assumed. See "Gate" below.

## What is being absorbed

    20 modules, 15,405 LOC     docmodel_six 4,247 · project_mmd 2,999 ·
                               texmap 1,632 · listings 1,517 · structure 1,247 ·
                               inspectserver 799 · psstream 581 · texpackages 450
    21 test files, 8,123 LOC

That is not a utility. It is a second reader of comparable weight to the
docmodel, with its own test suite, and it must arrive with that suite intact —
a merge that drops 8,123 lines of tests to "tidy up" would discard exactly the
evidence that makes the reader trustworthy.

## Design

### 1. Vendor the fork, do not depend on a sibling checkout

`pyproject.toml` grows a dependency on the patched pdfminer, built from
`pdfminer-glyph-identity.patch` which moves into this repo. `install.sh` /
`bootstrap.sh` applies it. `PDF2MMD_HOME` and the sibling-checkout search are
deleted, not deprecated: a path convention that can point at a stale copy is
how ser7 ran 784 for a week while this machine ran 820, and how a deleted
`~/Downloads/pdf2mmd` took `~/pdf2mmd/.pdfmm-venv` with it (it was a symlink
into the tree, 2026-09-29).

### 2. pdf2mmd becomes `src/pdfreader/`

A package beside `docmodel` and `docops`, not inside either: it is a READER,
peer to the MathPix ingest, and burying it under `docmodel/` would invert that.
Its tests move to `tests/` under their own names. `import docmodel_six` becomes
`from pdfreader import glyphs`; nothing else about the modules changes in this
phase. A rename and a move, measured by the suite passing unchanged.

### 3. The three seams become one implementation each

- **Preamble** — `texpackages.packages_for(body)` becomes the single source of
  a generated document's package list, and `report_tex.PREAMBLE` consults it
  instead of carrying a fixed list. The document's OWN preamble
  (`meta['latex_preamble']`), which `standalone_preamble` already extracts and
  826 taught to carry `\input xy`, is injected behind `\IfFileExists` guards.
  Target: `arxiv.1102.1889` evidence report, 1,029 errors → single digits.
- **Crops** — `report_tex.render_crops()` becomes the single crop renderer, and
  pdf2mmd's `.tex` projector calls it instead of emitting URLs. The Markdown
  keeps URLs (a reader with a server is the point); the LaTeX gets files.
  Target: pdf2mmd `.tex` compiles with 0 missing images.
- **Crop id** — one scheme, `<bibkey>-<page:02d>`, written by whichever
  renderer runs and indexed by the manifest `inspect` writes. pdf2mmd's
  `{doc_id}g-{page}` is retired; the `g` and the unpadded page are the two
  halves of the current mismatch.

### 4. It runs always, and asks nothing

The user's requirement, and the point of the whole exercise. `glyphlines` stops
being a command a person remembers to run:

- `route` gains the keyless glyph reader as its **default** lane for a
  born-digital PDF. Today it picks pdfminer/text-layer; it will pick the glyph
  reader, which is the same input read better.
- `model` builds from the glyph reader's typed `lines.json` when no MathPix
  conversion exists, with no flag and no prompt.
- `readme` (831) records which reader ran, so the choice is auditable after the
  fact rather than guessed from file shapes.

Nothing paid moves: `mathpix`, `translate`, `vision`, `bibfetch` stay declared
and never auto-run. The free reader becoming automatic is precisely what makes
the paid one optional.

### 5. Gate

`tests/test_pdfminer_fork_is_additive.py`: apply the patch to the pinned
pdfminer, diff the public surface, and FAIL if anything is removed or changed
rather than added. The integration is safe because the patch is additive; the
day that stops being true, the test says so instead of 33 callers finding out
one defect at a time.

## Phasing

Each phase leaves the tree working and the suite green.

1. **Vendor + gate.** Patch into the repo, dependency declared, additivity
   test. No behaviour change. *(This phase is executed below.)*
2. **Move.** `src/pdfreader/`, tests relocated, `PDF2MMD_HOME` deleted,
   `glyphlines`/`profile` call imports instead of subprocesses.
3. **Seams.** Preamble, crops, crop id — one implementation each, each with the
   before/after measured on `arxiv.1102.1889` and `CG_2008___51_7_0`.
4. **Default.** `route` and `model` prefer the glyph reader; `readme` records
   it; `--no-glyphs` for the caller who wants the old lane.
5. **Retire.** `inspectserver` becomes `pdfdrill imageserve`; `pdf2mmd.sh`
   becomes `pdfdrill glyphlines` in truth rather than by delegation.

## Two things the user has flagged for later, recorded so they are not lost

**Tesseract.** The intent is to remove it, or to reach a solution with no ML at
all. Today it is the fallback for a scan with no text layer, and it "cannot
type equations" (a 0-equation model on a math-bearing document sets
`NEEDS_VISION_OCR`). Removing it is not a deletion but a replacement, and needs
a lane that reads a scan without a trained model. Out of scope here; named so
the integration does not entrench it.

**A CCL approach to maths, audited elsewhere.** Reported, not verified here:
line-by-line image processing with connected-component labelling, merged with
the characters read from the PDF stream. Roughly 11 years old; mathematics
only; incomplete code; Ghostscript for rasterisation; performance comparable to
`inkdrill`; the CCL itself in C, with the optimised version *removed* from the
git revision that survives. A university group with time and knowledge gave up
on it. A Claude.ai session has audited and run the code and will supply notes.

Why it belongs in this spec: it is the same shape as `inkdrill` and
`eqblobs` — ink geometry married to the character stream — and if it works it
is the no-ML maths lane that makes the Tesseract question moot. The integration
should leave room for a third reader beside MathPix and the glyph reader,
rather than hard-coding two.

## What this does not decide

- Whether `inspectserver` stays a separate process (it is a server; probably
  yes, as `pdfdrill imageserve`).
- The licence and provenance story for vendoring a patched pdfminer.six —
  its own licence permits it, but the patch must stay readable and attributed.
- Whether `docmodel_six` and `docmodel` eventually converge. They are two
  document models and this spec deliberately does not merge them; it merges
  the READER, not the model.
