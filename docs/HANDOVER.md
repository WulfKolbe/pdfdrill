# HANDOVER

Current state, current blocker, next task. Nothing else — the per-task
evidence lives in `out/NNN.txt` and `~/pdfdrill-library/out/NNN/`, and the
rules learned by defect are in **`docs/HANDOVER-RULES.md`**.

Last updated 2026-09-12, after task 676 — EXCEPT "A volume is an archive"
below, added 2026-10-10 after 899. Nothing above that section has been
re-verified since 676, so treat its numbers as of that date.

Tasks 649-676 are the 2026-09-12 session's
run: the projection defect set (649-653), the size budget and the conserve
gate (654-656), the "(not rendered)" causes (659-668), the ink/crop identity
work (667, 670, 671), the marks command (672, 673), and the transclusion
scope work (674-676).

---

## Where the 20 published documents stand

Twenty documents are published. `penev_A` and `pdf-dc99cf88` are **retired**
from the set by decision, not by failure — the population is 20, and a check
that still reports 21 is reading a stale list. Verify with:

    python3 tools/publishcheck.py --list ~/pdfdrill-library/out/documents.json

Per document the site carries:

    evidence-equation.pdf   every display equation, six columns, unbounded
    evidence-formula.pdf    every inline formula; Page/Conf./Image are the
                            HOST LINE's, and the file says so
    evidence-table.pdf      every table, region rendered from the PDF
    evidence-image.pdf      every image region
    residuals.pdf           the action list: Corrected, Unresolved, Flagged,
                            Low confidence, Doubted — worst first
    report.pdf              retired from reading; kept as the ink chain's
                            measure build
    inspect.html            the docmodel browser (page / reflow / tree)
    formula-report.html     tables.html    <slug>.md
    report.build.json       report.ink.json

Evidence is for lookup, residuals for reading. The site copies are
Ghostscript /ebook derivatives under `<doc>/published/`; `publishcheck`
compares against `published/` when it exists.

    pdfdrill evidence <pdf> --all-kinds --pdf     # every kind, then the PDFs
    pdfdrill marks <pdf> --build                  # 673: inkdrill's marks
    pdfdrill residuals <pdf> --pdf
    pdfdrill publishready <pdf>

`report`, `breport`, `inkreport` are aliases; `reporttex` is superseded for
reading. The reports read the Document (`src/pdfdrill/reports/`), never
tiddlers, and take identifiers from `tiddlywiki.math_titles` /
`region_titles`.

Residuals are **measured on display equations only**. The 36,041 inline
formula rows have never been measured; the residuals header states when the
equations were measured and against which model.

---

## The rule that governs what may be transcluded

**674/676.** Math on a table cell, a section heading, a title, a TOC entry, a
figure label or inside a CAPTION is never an inline formula and never becomes
a `{{…||FO}}` transclusion. `src/docmodel/line_types.py` is the single
source of truth: five families named after the sentence that asked for them,
16 MathPix line types, plus `caption_anchors(doc)` for the caption span —
which is a Paragraph property (`kind: "caption"`), not a line type, because
MathPix types most captions plain `text`.

Five readers, because 1,367 models on disk predate the gate:

    docmodel/modules/formula.py       the object is never created (THE fix)
    docops/projectors/tiddlywiki.py   no substitution, and no residual FOX
    docops/projectors/latex.py        no standalone `$x$` in the .tex body
    pdfdrill/inlinectx.py             the host line is the first PROSE one
    pdfdrill/reports/from_document.py the row is not published

**675.** Refusing a transclusion leaves MathPix's own `\(...\)` in the text,
and TiddlyWiki's KaTeX does not render it. `src/docops/mathdelims.py`
converts it in place to the `<$latex .../>` widget every projection already
converts FROM — three named policies, wired at `tiddlywiki._t`. That renders
math without creating an object, so the refusal holds.

**A model rebuild is deferred.** Gate 1 only takes effect on a rebuilt model,
and a rebuild renumbers FO identifiers, which invalidates every crop and
every ink row keyed on them (667). Gates 2-5 make every published surface
correct without it. `math_titles` is deliberately untouched for the same
reason.

---

## The measurement chain, as it now works

    reporttex --cellrect   phase 1 (the MEASURE build, still report.pdf):
                           full listing, legend off, bullets off. Emits
                           pdfdrill-rows.json.
    inkdrill compare       per page, 300 vs 600 dpi
    inkmeasure.measure     claims each lattice row by the rect that CONTAINS it
    inkconvert             pairs by identifier; report.ink.json carries
                           measured_against {built_at, model_sha256, model_mtime}
    residuals              reads the ink as it stands; --measure runs the chain
    publishready           artefacts, glyphs, ink, timestamp, coverage, crops

Invariants worth keeping:

- **`zeroScan` must be 0** on the measure build.
- **The ink's `model_sha256` equals the model's** — the timestamp gate.
- **`fresh_ink` asks six content questions**, the sixth being
  `report_tex.geometry_signature()`, an AST hash of the functions that
  decide report layout (670). A layout change now invalidates a measurement.
- **The crop cache is keyed on `(page, region)`**, not on the filename (671).
- **A published row's crop must be the one the ink measured** (667,
  `reports.gate.crop_gate`, whose `GateStatus.verified` distinguishes
  "asked and passed" from "nothing to ask about").

## The size budget

**655.** `src/pdfdrill/reports/budget.py` picks a crop rung so an artefact
fits its budget: scale/quality down a fixed ladder, 1.00/q75 (62% of
original) to 0.42/q70 (17%, = 105 dpi, the floor). `conserve` is a gate with
a checked-in baseline (`src/docops/conserve.py`,
`conserve_baseline.json`) — a projection that drops objects a previous one
carried fails rather than shipping.

## inkdrill

Consumed as a **subprocess, never an import** — `docs/inkdrill-integration.md`
has the contract. `INKDRILL_ROOT` locates it; `INKDRILL_HOME` is a
deprecated alias that warns. `pdfdrill marks` (673) runs
`tools/formulamarks.py`, parses its stdout apart from its progress stderr,
and writes `marks.json` beside the document. inkdrill keys books by the
LIBRARY FOLDER NAME, pdfdrill by the site slug; the two differ for every
Z-Library book, and `inkmarks.resolve_key` tries both and says which matched.

---

## Current blocker

**Nothing is blocking the 20.** `tools/publishcheck.py` is green in both
directions: 20 published, 20 identical, 0 stale, and the 100 superseded
`<doc>/published/` snapshots (214 MB, 09-06) were deleted on 09-14 — every
one had a current twin in its parent folder, and the inventory is in
`out/689-published-leftovers-deleted.txt`.

The **48 held census-verified repairs** are published (690, site 3756a29):
six documents rebuilt, re-measured, READY on all six gates, publishcheck
20/20 identical. The one open item is **`penev_B`**, the 7th planned rebuild,
whose model changed for a reason nobody has explained — explain that before
rebuilding it.

**pdf2mmd** (`~/Downloads/pdf2mmd`, the pdfminer route built in a Claude.ai
chat) is reviewed read-only in `out/690.txt` and deliberately NOT integrated
until it is understood — the user's instruction of 2026-09-14.

---

## Open — a silent partial conversion has no detector

A MathPix conversion can return HTTP success with two thirds of the document
missing, and nothing in the result says so. Measured on
`20260620_Sach_Beitragsrechnung_999391621.pdf` (LVM, 3 pages), both through the
API and by hand in the web app:

| page | fonts | text layer (`pdftotext`) | in MathPix output |
|---|---|---|---|
| 1 | 11 x Type 3 | 2,183 chars | no |
| 2 | 1 x Type 3 | 211 chars | no |
| 3 | 2 x TrueType | 3,387 chars | yes |

Exactly the Type-3 pages are dropped, deterministically — two identical runs
give byte-identical output. 9 of 17 files from that source show the same shape,
each yielding 3.4-3.9 KB and in every case only the final page. The Type 3
fonts are embedded and carry ToUnicode maps, so nothing about the file is
undecodable: poppler reads page 1 without difficulty and pdf2mmd reads 6,187
glyphs across 91 lines with nothing deferred.

`conserve` cannot see this. It checks the model against the projection it
produces — both sides of a document that was already truncated before either
existed. The missing check is PDF -> model, and its input is ALREADY ON DISK
for every document: `probe-page-text.json`, written at acquisition, holds
pdftotext's per-page character count. A page with a substantial text layer and
no model content on it is the signature, and it is one comparison.

What it must NOT be is a ratio over the whole document: page 3 alone is 57% of
this file's characters, so a document-level check passes while two thirds of
the invoice is gone. Per page, or it does not detect the case it exists for.

Wire it where the cost lands: `mathpix` should refuse to report success, and
`status` should carry it, rather than a reader discovering it in a projection.

## A volume is an archive (898, 899)

One PDF holding several independent works — a proceedings volume, an edited
book, a journal issue — is now listed and taken apart without a paid call and
without building a model. Three layers: `members` → `profile` → `memberprofile`,
and `unpack` to hand one member on as its own document.

Population: the four Springer ICDAR 2026 volumes, 2,663 PDF pages, 401 MB,
148 members (40/41/41/26, exactly the publisher's Crossref deposit).

Measured constants, each with the population it came from:

| constant | value | population |
|---|---|---|
| members found from the chapter-opener footer | 148 of 148 | 4 volumes |
| printed ranges agreeing with Crossref | 148 of 148, 0 differences | 4 volumes |
| `members` wall time | 1.2 s for all four | 2,663 pages |
| `profile` wall time | **2.2 s/page** — 17m19s for 470 pages | part IV |
| member cut, pikepdf | 2.6 MB, 0.2 s | one 18-page member of 86 MB |
| member cut, `pdfseparate`+`pdfunite` | 101 MB, 75 s | the same member |
| printed→PDF offsets in ONE volume | up to **ten** (+19…+9) | part I |

Four things that are true and look false:

- **The printed→PDF offset is not one number.** Springer prints a part divider
  before each section and strips its blank verso, so the offset is piecewise:
  +19 throughout II and III, ten distinct offsets in I, two in IV. T-0004's
  contract assumes the single offset `booktoc` computes; that is
  underspecified. The rule that holds 148/148 is `last = first + (Crossref
  last − Crossref first)`, never "the next member's first page minus one" —
  which reported 14 of 148 mismatches, all artefacts.
- **Crossref is a check, not a dependency.** Each member prints its own DOI
  and `pp. <first>-<last>` in a footer on its own first page: 148 of 148 found
  there, agreeing with Crossref 148 of 148. A truth source the deliverable
  depends on is not independent.
- **A bare DOI search finds 71 members in a 40-member volume** (sibling DOIs
  in reference lists). Constrain to the volume's own ISBN. And tolerate
  `_\s*\d+`: a line break put a space in `978-3-032-36039-7_ 28` and cost
  one member silently.
- **The folio needs the first THREE lines of a page.** A verso puts the number
  first, a recto puts the running head first; reading one line found 26 of 40.

`memberprofile` joins the two measurements — each member's page range against
the pages each property was established on — and reads no page again. On part
IV: `listing` is on 3 of 26 members (52 of 470 pages, 11%), while
`inline-math`, `diagram`, `inline-code` and `coloured-fill` are on 26 of 26
and therefore select nothing. Report the carrying count FIRST; "a paid pass
over just those members bills 329, not 470" is not a saving when 19 of 26
members hold the 40 equation pages.

`slow:` in the manifest is new and separate from `network:`: network means
never auto-run, slow means auto-run but announce it first. `profile` carries
it, because `--ensure` is silent by design and drillui appends `--ensure` to
every command (896) — the only route to `memberprofile` was a 17-minute
freeze with nothing on screen.

**A property roll-up prices a reading; it does not rank relevance.** Measured
over all 148 members once all four volumes were profiled: the 34 members
picked by READING the titles carry equation pages at 9.5% (56 of 591) and the
other 114 at 9.6% (189 of 1,969), median 1 either way, and `inline-math` is
13.3 pages per member in both the math-titled papers and the ten carrying the
most equations. The detector is right — checked both ways: HME-Leibniz, a
mathematical-expression DATASET paper, has **zero `=` in 18 pages** because
its mathematics is in the handwriting images, while the top-ranked member is a
document-security paper with real typeset equations. So `equation` tracks
"states a model with loss functions", which is nearly every ICDAR paper. A
`--has equation` selector would have EXCLUDED the most relevant member of all
four volumes. Do not build one; this is why the owner chose `--match` alone.

Open: the 34 members extracted into `~/pdfdrill-library/` (591 pages, 22% of
2,663) are Springer-licensed and are **on disk, not committed**. The library
is a git repo; nothing has been `git add`ed there.

---

## A projection nothing requires is a projection nobody has (900)

Eleven LaTeX/TeX books in the corpus had **no markdown projection**, and the
reason was neither cost nor a missing capability. `md` is a projection, no
layer `requires:` it, and for every one of them `pdfdrill steps md <pdf>`
answered *"prerequisites satisfied (equations, provenance, size) — runs
directly."* Grätzer's 621 pages took **94 s, keyless**.

Counted rather than assumed: across all **163 manifest commands, `md` appears
in no `requires:` at all** — it is a terminal projection, so no chain can ever
pull it in and `--ensure` can never offer it. That is NOT the `cmd_tiddlers`
shape, and the first draft of this note said it was: `tiddlers` is required by
five commands (`standalone`, `cdncrops`, `breport`, `reporttex`, `publish`) and
was rebuilt anyway. Two different faults with the same symptom — one layer was
unreachable, the other was reachable and still unread.

They are projected and pushed: `pdfdrill-library` (PRIVATE)
`projections-latex-math-layout/`, 12 files, 9.4 MB, index in `INDEX.md`.
Full text of commercially published books — it must stay in that repo.

**`TeX in Practice Vol. II` reports `0 inline and 0 display math` across 396
pages of a book subtitled *Paragraphs, Math and Fonts*.** The number is wrong
in the way this project keeps paying for. `pdffonts` settles it:
`HiddenHorzOCR` over one `jbig2` stencil per page at 600 dpi — a **scan with
an invisible OCR text layer**, so the 122,230 words are OCR, not the book's
typesetting, and `nodes/math_detector.py` classifies math by FONT CLASS
(CMMI and friends). A page whose only fonts are Times-Roman and an OCR layer
can never register math. The 203 `$…$` spans in the markdown are the book
*printing TeX source* for the reader, not detections.

So `md`'s summary states `0` where the truth is *not established*. Three more
projections carry no counts at all because the unified-model route records
different layer metadata. **Absent is not zero — and the summary line is
currently the only place a reader learns the difference, by not being told.**
Unfixed; the honest counts would need the route named beside them.

Two writers on the `md` path bypassed `jsonio`, which exists for exactly their
failure and says so in its own docstring. A folder name carrying a bare CP1252
byte (`Marco \xd6chsner`) killed the build **after 245 pages were already
read**. Fixed in `commands._extract_pdfplumber_chars` and
`context.DocumentContext.to_json`/`from_json` — and the first attempt was a
half-fix that wrote an `ir.json` pydantic's parser could not read back, caught
only because the test asserted the round trip instead of the absence of a
crash.

Cost on disk: the 11 builds left **3.9 GB of `chars.json`** caches beside the
books (570–906 MB each, gitignored). Deleting them is safe; each rebuilds in
about 90 s.

---

## The markdown extractor resolved no glyph names at all (901)

A reader of The TeXbook's markdown reported "missing Greek letters". The Greek
was not missing — scored against `texbook.tex` itself, every route recovers 155
of Appendix G's 158. What reached the eye was `C(cid:48)` where `C′` stood and
`θ = 0` where `θ ≠ 0` stood.

`cid_glyphs.py` opens by saying its table lives in one module so that *"one
table, imported by every extractor"* stops the leak recurring. The extractor
`md` actually uses — `_extract_pdfplumber_chars` — imported nothing and dumped
pdfplumber's chars raw. **That was the fourth copy of one table here** (texmap's
`CM_ENCODING`, `cid_glyphs`' `_CID_MAP`/`_GLYPH_BASE`, `ingest_pdfplumber`'s own
`_CID_MAP`, and this gap). The general resolver reads names from `/Differences`;
this is a 2000-era dvipdfm file declaring `Encoding /Builtin` with no array at
all, so even wired up it had nothing until it could ask `texmap.CM_ENCODING` —
391 (family, cid) pairs, zero carrying two names.

Second half: TeX sets `\ne` as `\not` then `=`, **two glyphs at the same x**.
Measured, not assumed — both occurrences put the slash and its `=` at an
identical x0 (92.1, 126.3). The join is geometric and the composition is
Unicode's own NFC; a pair NFC declines to compose is left standing.

Whole book, rebuilt: **`(cid:N)` 5,971 → 2,580**, the 3,100 `(cid:104)/(cid:105)`
⟨⟩ brackets now `\langle`/`\rangle` (21 → 3,023), the 127 style primes → 0.
Appendix G: `≠` 0 → 2, primes 0 → 18, `(cid:N)` 41 → 9.

**1,222 `(cid:127)` remain on purpose** — `manfnt`'s dangerous-bend signs, whose
codes collide with CMSY's. Adding manfnt to the table is easy and unclaimed.

### Three defects this exposed and did NOT fix

1. **`md` has no `--force`, and it misreports provenance.** With a `<stem>.md`
   present it serves the file while printing *"Markdown from MathPix … preferred
   over the text-layer extraction"* — for a file the text-layer route built
   (same word count both times, demonstrably the same file). Provenance is
   decided by the file EXISTING, which is "the label is not the key" again, and
   the only way to rebuild is to move the file aside. **Owner's call whether
   `md --force` or the honest label comes first.**
2. **`≤` is extracted and then misplaced** to the end of its sentence (`Thus,
   $C S$ means … $\leq$ Style`). A reading-order fault, not a glyph fault; it
   reads exactly like a dropped symbol while the count looks healthy, which is
   how it survived counting.
3. **Subscripts and fraction bars** on this route: `\sigma22` for
   `\sigma_{22}` (53 of them) and `${1\over2}v+a$` fragmented into `$^{1}v + a$`
   plus an orphan `$$^{2 2 }-$$`. The margin index words also interleave into
   the prose. The pdf2mmd2 `--refine` route has none of these.

### Two measurement errors of mine, both caught by scoring against gold

`texbook.tex` lines 24755–25273 are Appendix G's own source and are on disk —
this is the rare case where gold exists, and it caught both:

- A `\b` after the macro name undercounted the gold to zero sigma, because `_`
  is a word character and `$\sigma_1$` never matched.
- Scoring for the Unicode `′` and `≠` and never for `^{\prime}` and `\not=`
  scored pdf2mmd2's correct TeX as absent. I had published that as "both routes
  lose all 26 primes" and nearly sent pdf2mmd2 a fix it did not need.

**When a projection's source document is available, score against it.** Both
errors were in the measurement, and both looked like defects in someone's code.

---

## When the corpus cannot supply an encoding, the document can (902)

901 resolved every Computer Modern font in The TeXbook from
`texmap.CM_ENCODING`, the table measured across 102 corpus documents. It left
1,667 `manfnt` glyphs standing, 64% of everything still unresolved, and on
purpose: **manfnt is not Computer Modern, appears in none of the 102 documents,
and its codes collide with CMSY's** — 104/105 are angle brackets in CMSY and
something else in manfnt, so a resolver that went by code alone would print a
dangerous-bend sign as a bracket. A visible `(cid:N)` is a defect you can count;
a wrong glyph is a corruption nobody sees.

The codes were never unknowable. They were declared by the document itself. The
TeXbook's TeX source sits beside its PDF in the library, and it defines its own
characters:

| code | the book's own line | glyph | count |
|---:|---|---|---:|
| 127 | `\def\dbend{{\manual\char127}}` (23727); prose at 2691 | ⚠ | 1,222 |
| 120 | `\llap{\manual\char'170…}% triangle in margin` (23908) | ▶ | 305 |
| 91 | `\def\pennyedge{…\char'133}` (15676) | *unmapped* | 20 |
| 88 | `\def\pennytop{…\char'130…}` (15675) | *unmapped* | 16 |
| 65 69 70 77 78 79 84 | `\def\MF{{\manual META}\-{\manual FONT}}` (23782) | `METAFONT` | 14 |

Measured on the book, `md` route: `(cid:N)` **2,580 → 1,037**, `(cid:127)`
**1,222 → 0**, `(cid:120)` **314 → 9** (the 9 are CMEX10's, a different font with
the same code, correctly untouched), `METAFONT` **5 → 7**.

**The logo letters are the table's own proof.** `META`+`FONT` needs M E T A F O N
with T twice, and the measured book-wide counts are exactly 2 for each of
A E F M N O and 4 for T. A guessed table does not land on that.

**Three deliberate limits, each with a test.**

- `MANFNT` is a **separate dict from `CM_ENCODING`**, because the provenance is
  different. `CM_ENCODING`'s docstring earns its authority by saying it is 391
  pairs measured across 102 documents with zero disagreements; folding in codes
  read off one book's macros would quietly make that sentence false.
- The table is **partial**. manfnt's codes 97–100 and a tail at 104–117 (90
  glyphs in this book) are never named by the source, so they stay `(cid:N)`.
  `test_manfnt_resolves_only_the_codes_the_books_source_names` asserts it, and
  `test_manfnts_codes_do_not_leak_into_cmsy_or_the_other_way` holds the collision
  apart in both directions.
- ⚠ and ▶ are **chosen stand-ins, not decodings** — neither sign has a Unicode
  codepoint — and they are the only entries of that kind in `_GLYPH_BASE`. The
  case for them is that both are pure signposting, so a stand-in cannot mislead
  anyone about a formula; what a reader got instead was
  `(cid:127)(cid:127)(cid:120)EXERCISE`. The penny pieces get no stand-in, because
  nothing stands in for a fragment of a drawing.

**The generalisable rule: a document that typesets its own font is the authority
on that font.** The corpus is the right source for a standard encoding and has
nothing to say about a one-document font. Before refusing a font as unknowable,
check whether its source is on disk — here it was, two directories away, and had
been through the whole of 901.

### A side finding, for anyone scoring Appendix G against `texbook.tex`

The `.tex` beside the PDF is the **Twenty-third Printing, February 2021**; the
PDF is dvipdfm, 2000. In Appendix G they differ because Knuth moved the
Inner-atom wrapping out of rule 15e into rule 19 — rule 15e makes an **Ord** and
says *Go to rule 19*, rule 19 gains *The entire resulting list now becomes the
nucleus of an Inner atom*, and rule 3 gains *and move on to the next item*. One
edit, three sites. Confirmed on both extraction routes independently, and
`grep -c -i 'go to rule 19'` over the whole book returns 0. **The gold source is
not the same text as the PDF**, so three "extraction failures" at those sites are
not failures. 901's lesson was *score against the source when you have it*; this
is its footnote: check that the source is the same edition.

---

## The reading order was in the file and no reader asked for it (902b)

`md` reconstructs reading order from glyph geometry. Measured across eleven
PDF-Association / ISO documents, 1,234 pages, drilled on 2026-10-13:

| | geometric `md` | **`structmd`** |
|---|---:|---:|
| markdown tables, all 11 documents | **0** | **773** |
| …in ISO 32000-2 alone (11,036 tagged cells) | 0 | **732**, 4,305 rows |
| watermark / running-header lines in the prose | 1,265 | **1** |

Ten of the eleven ship a `/StructTreeRoot` — 78,468 structure elements in
32000-2 — and before this `grep -rn 'StructTreeRoot' src/` returned NOTHING.

**Two sources, each for what it is authoritative about.** The tree (pikepdf)
gives ORDER and ROLE, with `/RoleMap` translating a producer's private names
(`/Heading_2`, `/Table_Position`, `/H1 bold_` — 66 entries in 32000-2) into the
standard roles. pdfplumber gives the TEXT keyed by `(page, mcid)`; the
`chars.json` cache `md` already writes carries `mcid`, so a document already
drilled costs a JSON read. Above 256 MB of cache it reads the PDF instead —
32000-2's cache is 1.3 GB and `json.load` holds all of it; streaming takes 108 s
and bounded memory.

**Artifacts are excluded for free, and that is the whole watermark fix.** A
running head, a folio and a licence footer are artifacts, not content, so they
are not in the tree and the walk never sees them: 191,012 artifact characters in
32000-2, no filter and no list of strings to strip. That is why this is a layer
and not a cleanup pass.

### Four defects this found in itself, each now a test

- **A `/P` can contain a `/Table`.** ISO/TS 32005's measured chain is
  `/Document > /Art > /Sect > /P > /Table > /THead > /TR`, because
  `/Table_Position` maps to `/P`. Treating `/P` as a leaf reported **0 tables
  for a document with 151 rows** — the fault this layer exists to remove,
  reintroduced one level up.
- **A table is ONE block.** `project` joins blocks with a blank line, so a row
  per entry put a blank line between every row and markdown stopped seeing a
  table at all. The table COUNT was right and the output was broken; only a
  test asserting the rendered lines caught it.
- **A header row is all `/TH`.** ISO tables put a `/TH` in the left column of
  every data row as a row label; promoting one `/TH` merged a whole table into
  its own header.
- **The non-breaking-space hole.** pdfplumber loses `mcid` AND `tag` inside a
  nested marked-content sequence, and InDesign splits a run at a non-breaking
  space, so a page reads `H1/150 '1'`, `None 'Scope'`. Dropping the untagged
  half lost `Scope`, `1.7`, `2.0` and whole clause bodies — 8,583 characters on
  32005, 13.8% of it. The rule: an untagged run is appended to the run
  immediately before it in the page's own stream, and only when another marked
  run follows (the sandwich); an `Artifact` neither absorbs nor is absorbed.
  Recovered 8,144 characters there, 12,224 on 32004.

**A measurement error worth keeping.** I first reported genuine content loss as
**0.00%** by classifying every `tag=None` char as page furniture. They are
content — `Scope`, `1.7`, the clause bodies — and the true figure was 20.4% of
all characters before the sandwich rule. The lesson is narrow and repeatable:
*a bucket named "untagged" is a question, not an answer.* Print what is in a
bucket before concluding it is empty.

**Still absent, and reported in the command's own output every run** so the
number is checked rather than assumed: characters the file tags as content but
places in no marked-content run this layer can attach them to — 1,303 in
32000-2, 442 in 32005, 26 in each of TS 32001–32003. `structmd` refuses rather
than falling back when there is no usable tree: a tagged PDF whose tags are a
stub is exactly where a silent fallback is indistinguishable from success.

---

## A page turn is not a paragraph break, and the band is not text (T-0011)

`nodes/lines_paragraphs.py` carried one line of rule — *"Page break always
starts new paragraph"* — and no notion of page furniture at all. Every
paragraph that ran over a page was cut in two, and the folio, copyright line,
licence stamp and next running head were then composed INTO the text: on
`PDF-Declarations` four paragraphs ended with `© 2019 PDF Association <folio>`
glued to the last sentence, and the reading contained that footer nine times.

This route has **no subtypes** to read a join off (the MathPix route does, see
T-0010; `structmd` has the tag tree and pdf2mmd2 has `page_info` — three
routes, not to be mixed). So all the evidence here is geometric.

**Furniture is three signals, each sufficient, all of them requiring the line
to be short (≤ 80 visible chars) and to sit outside the band the body text
occupies:** the same line (digits normalised) on ≥ 3 pages, rights/licence
wording, or a bare folio. A line INSIDE the body band is never furniture — a
page number mid-page may be a cross-reference or a table cell and this route
cannot tell which.

**The band is learned from long lines that do NOT repeat.** A licence stamp 64
characters wide on every page of a 1,023-page standard is otherwise sampled as
body text, which pushes the band past the foot of the page, after which
NOTHING is outside it. That cost a whole measurement pass: the first ISO run
found 1,025 furniture lines and none at all in the range the task names.

**The grapheme stream does not move.** Furniture is recorded as its own L2
span and listed in the containing paragraph's `furniture_holes`; the
projection takes it out. The stream's sha256 is identical to the published
`ir.json`, so offsets cited against that artefact stay valid.

### Measured

ISO 32000-2 (1,023 pages, 2,639,631 graphemes — keep local, cite by offset,
never quote):

| | before | after |
|---|---|---|
| paragraphs | 6,862 | 5,875 |
| furniture spans | 0 | 4,348 |
| headings (this node's own) | 4,773 | 3,274 |
| headings (full pipeline L2) | 11,167 | 8,163 |
| band lines inside a paragraph | 2,845 | **2** |
| paragraphs ending unterminated, then furniture | 352 | 187 |

The two heading rows are the correction the audit asked for: this node emits
4,773 of main's 11,167 L2 headings and `EmphasisDetectorNode` the other 6,394.
A count from a partial pipeline needs the pipeline named.

The gate's yardstick is deliberately looser than the product (any short line
outside the band), so what it still counts are table cells and formula
fragments at the page edge. 1,496 running heads had been read as HEADINGS,
which is where this node's heading count falls from; the full-pipeline figure
falls further because the emphasis detector now declines the band too.

`PDF-Declarations` (PDF Association, CC-BY-4.0, 10 pages): furniture 0 → 16,
paragraphs 40 → 37, and `© 2019 PDF Association` in the markdown **9 → 1** —
the one left is the imprint page's own copyright statement, which sits inside
the body band and is the document's text.

### The range the task names had to be re-derived

`865128–865405` ends AT the form feed: it holds the sentence's tail and the
band, but the continuation begins at `865427`. The honest range is
**865128–865534**. Over it: before, 3 paragraph spans plus a HEADING (the next
page's running head) and 4 of 5 band lines inside paragraphs; after, **one**
paragraph span over pages 315–316 with 5 furniture holes and **0** band text
inside it.

End to end on the reading markdown, counted without quoting anything: the 40
most common band shapes of ≥ 12 characters occur **19,248 times** in the
baseline projection, 107 at 766795db and **60** now. The baseline projection is
byte-identical to the published `.md` (same sha256), so that is the file the
corpus has been reading.

For a consumer that reads paragraph RANGES and ignores `furniture_holes` —
`stub_nlp` slices `graphemes[start:end]` to build sentences — band lines
inside a paragraph range fall 2,845 → 1,206 rather than to 164. Those 1,206
are the declared holes. A hole-aware slice is a small change in one place and
is not part of this task; it is named here so the next reader does not
measure it as a regression.

The suite is **5,371 → 5,393 passed, 60 skipped, 0 failed**: the difference is
exactly the 22 new tests of this task, so no existing test described the old rule. A page
turn ending a paragraph was never written down as behaviour — it was just what
the code did.

### The audit returned two points, and both were invisible in the reading

1. **The running head was still a HEADING.** The paragraph node had stopped
   emitting one; `EmphasisDetectorNode` makes a heading of any short bold run
   and knew nothing about furniture. ISO 32000-2 carried **1,500** heading
   spans and **485** L4 emphasis spans lying wholly inside a furniture span
   (PDF-Declarations: 9 and 0). The markdown was already right, so only a
   reader of L2 could see it. The emphasis detector now declines any run
   inside a furniture span — emphasis as well as headings, because italic in
   the band is the same mistake: **1,500 → 0**, **485 → 4**, headings
   9,671 → 8,163. The 4 that remain are `math_inline` ×2, `math_display` ×1
   and one `flag`, from the math detector and the flagger, which do not
   consult furniture. (L3 tokens are a lexical layer and still tokenise the
   band; 31,655 of them lie inside one. That is what a token layer is for.)

2. **A footer cut short is furniture that no per-line signal can reach.** Ten
   ISO lines held footer wording and were not furniture. Nine are pure
   PREFIXES of the canonical 70-character form (13–53 normalised characters,
   checked character by character), each repeating on one or two pages, with
   no rights wording and no folio shape — so repetition, wording and shape
   all had to decline them. All ten print at y 823.1–823.2: the row where
   **1,042 lines over 1,023 pages** print, 1,001 of them identical. So a row
   the first pass confirms is now evidence in its own right, and a short line
   on it is furniture by position (`why: "row"`). **164 lines newly marked;
   band lines inside a paragraph 164 → 4.** The tenth line is that footer's
   first 60 characters plus 40 more: only the **prefix** becomes furniture, 64
   of its 110 graphemes, and the rest stays prose (`why: "row prefix"`). A
   fused line is not a licence to delete the text fused to it.

The four band lines that remain inside a paragraph are each unique, carry no
rights wording, are no folio, and two of them sit exactly ON the band
boundary. There is no evidence any of the four is furniture, so they stay —
the rule is not widened until a number reaches zero.

### 29 "stamp lines with text outside their span" were a page boundary

Every one of the 29 ranges the audit named contains a **form feed**. Each is
the stamp at the foot of page N followed by the first line of page N+1, which
a line model that splits only on `\n` reads as one line. In this route's
model the stamp part is covered in all 29, and the uncovered graphemes are the
next page's own first line: 82 characters of the title page's title, 55 of a
heading, 9 of an index entry. Two of the 29 were at band rows and are now
covered end to end. Worth keeping because it is the second time in this task
that a yardstick's own line model, not the code under test, produced the
finding.

**An observation, not a claim:** a 12-character line with no digits prints at
y 97.6 on 155 pages, 9 points inside the body band, and is emitted as a
HEADING. It never enters a paragraph (0 of 155), so it does not touch this
task. Catching it would mean counting repetition INSIDE the band, which would
also catch a repeated table header — a decision, not a fix.

### A tail of band vocabulary is the band, and the stamp is not a band sample

*(The vocabulary rule described here was deleted one audit later — see "And
the vocabulary rule is gone" below. The finding that produced it stands.)*

The audit returned one more point, and it was the one that mattered most: the
46 graphemes left as prose after the row prefix at offset 3133 were stamp
text. Measured, not read — two of their words occur 1,047 and 1,041 times in
the document, **1,017 of those inside furniture**, and the remainder carries a
seven-digit group. Taking only the canonical prefix had left the one place in
the reading text where this document's stamp still appeared.

So whether a fused tail is prose is a question about VOCABULARY, and the
document answers it: a word of ≥ 4 letters occurring ≥ 3 times that the
document uses mostly OUTSIDE furniture is a prose word, and one of those in
the tail keeps the tail (`why: "row prefix"`). With none, the whole line is
the band (`why: "row fused"`). Three-letter words decide nothing — one of them
occurs 1,985 times here, half inside the band and half outside.

The default is that way round on purpose. The six sponsored copies are
personalised, and a licence stamp reaching the reading text is the worse
failure; the cost is that a tail of genuinely rare prose goes with the band.
On the documents measured that is 1 line of 44,416 (ISO 32000-2) and 0 of 244
(PDF-Declarations).

**And a line that says it is about rights is not a sample of the body band.**
Gate 3 found this by being run on two more documents rather than one: on
ISO/TS 32001 (14 pages) three unique 47–54 character stamp lines at the foot
of the page were enough to put the sample's 98th percentile PAST the page
edge, after which nothing was outside the band and the whole bottom band went
undetected. Excluding rights-matching lines from the sample (they were
already excluded when they repeat; these did not repeat) takes
**ISO/TS 32001 from 10 furniture spans to 39 and ISO/TS 32003 from 12 to 39**
on 14 and 13 pages — about three per page, which is a running head, a footer
and a stamp. PDF-Declarations stays at 16, which is the control: the change
adds nothing where there was nothing to add.

The stamp string that had been reaching the reading text occurs **once** in
the published `.md`, once at 766795db, once at e22228f9 and **zero** times
now. ISO 32000-2: furniture 4,341 → 4,348, paragraphs 5,879 → 5,875, band
lines inside a paragraph **4 → 2**; the 40 most common band shapes in the
markdown 19,248 → 60. Suite **5,393 passed, 60 skipped, 0 failed** (22 tests
in the file).

### The band line is not always at character 0, and the walk does not always start there

The audit's last point was four 112-character lines of the ISO/TS copies that
stayed prose, inside paragraphs and in the markdown. Two defects, both
narrower than the audit's guess (which was that the vocabulary rule was
finding prose words — it would have, but it never ran):

1. **`_canonical_prefix` required the row's canonical line at character 0.**
   All four lines begin with two spaces, so the match scored **0**, the line
   was not a fused candidate, and at 90 visible characters it was over the
   cap the first pass applies. No rule saw it. The matcher now skips the
   line's own indent first.

2. **The projector entered the span two characters in and so never saw it.**
   `furniture_from` was keyed by a span's FIRST character, and after a
   paragraph break the walk consumes the following whitespace run — which
   steps over an indented band line's start. The skip is now by containment
   (`bisect` over the spans), so a band span is dropped wherever the walk
   enters it.

With those, `row fused` covers all four: **ISO/TS 32001 39 → 41 spans,
ISO/TS 32003 39 → 41**, and the lines occur in the reading markdown **2 → 0**
each, with the 5-digit group that is theirs alone going 2 → 0 while the
document's own use of the other group stays.

### And the vocabulary rule is gone

Measuring the four lines settled the question it existed for. Their tail's
words score 0.75, 0.75, 0.80 and **0.36** inside furniture once the
candidates are excluded from their own evidence — so one ordinary word that
the standard's prose also uses would have kept a licence line in the text.
A 15-page document's stamp cannot win a majority against prose that shares
its vocabulary, and no document measured here fuses PROSE onto a band line:
six such lines over three documents, six of them band text printed longer on
that page, none of them prose.

So the rule is now one line: at a confirmed furniture row, a line that begins
with the row's canonical band line is furniture, whole. `_band_vocabulary`,
`_prose_tail`, the three VOCAB_ constants and the partial-span path are
deleted. Two mechanisms built for a case that does not occur, each of which
let through the case that does.

**The trade-off, stated rather than buried:** if a document ever does fuse
prose onto a band line, that prose is now lost from the reading text. The
grapheme stream still holds it, and the paragraph still names the range as a
hole, so nothing is destroyed — but a reader of the markdown will not see it.
On the evidence available that is the right side to err on: the six sponsored
copies are personalised, and a licence stamp in the reading text is the worse
failure.

The suite is 5,393 passed, 60 skipped, 0 failed on the final code; the file
holds 18 test functions and 22 cases, after I deleted six of this task's own
page-turn tests along with the two that documented the vocabulary rule and
restored them from d2c7d955.

ISO 32000-2 is unchanged by all of this except in detail: furniture 4,348
(`repeats` 4,155, `row` 170, `rights` 21, `row fused` 1, `folio` 1),
paragraphs 5,875, band lines inside a paragraph 2, gate 1 as before — span
for span the same furniture as before the fix, which is what one expects of a
document whose band lines carry no indent.

**A number of mine that was wrong, and how it got that way.** 903f's commit
message reports `row` 168 and `row fused` 3 here, and says the whitespace fix
found two more fused lines. It did not. That measurement came from a run I
started BEFORE the last line of the fix — the one that makes the
twelve-character threshold count matched characters rather than the indent
with them. Under the looser threshold two indented lines reached the fused
branch on the strength of their own whitespace; the tightening puts them back
where they belong. The audit caught it by building the committed code and
getting 170 and 1, which is what the committed code gives. The totals were
never affected (4,348 / 5,875 / 2), only the split between `row` and
`row fused`.

The lesson is the same one T-0010 learned and this task then repeated twice:
a measurement is of a BUILD, not of an intention. A figure taken from a tree
that is one edit behind the commit is not a figure about the commit.


### A defect of my own, found by the gate rather than by reading

Furniture only became a hole when a PAGE TURN followed. 24 ISO paragraphs have
a footer with more text after it on the same page — pdfplumber's line order is
not always top-down — and those paragraphs contained the band without saying
so. The projection dropped it either way, which is exactly why only a gate
could see it.

---

## Next task

- **LaTeX field promotion** — the user's decision of 2026-09-14, recorded in
  `docs/superpowers/specs/2026-09-14-latex-field-promotion-design.md` and in
  `docmodel.prop_contract`'s docstring. There are already TEN latex-family
  props; pdfminer LaTeX arrives shortly with authoritative symbol names and has
  nowhere to go that any reader looks at. The best reading takes the standard
  name, every other keeps a source-named copy, the WRITER promotes so no reader
  needs a flag. Four measured constraints before implementing — the sharpest
  being that ink measures the UNPROMOTED MathPix reading by name
  (`prefer_refined: False` is deliberate), so the losing copies are not
  history.
- **Listings** — MathPix math expressions that are really algorithmic
  structure tables should be detected as images. The user's named next goal.
  676's caption work is the shape this wants: a TYPE, not another exclusion.
- **The LaTeX projection of a `CodeListing`** — a branch now exists in
  `src/docops/projectors/latex.py`, and the comment above it is the SPEC,
  written from the worked example at `~/pdfdrill-library/lstgold/probe/gh/`
  (read back 16 of 16 on text, indentation and numbering). Four things it
  must keep, each learned by a defect in pdf2mmd 781:
  **the body is the program** — a listing is the opposite of an equation, so
  nothing goes inside it: no `\textcolor`, no escape markers;
  **the style is a header property** — `morekeywords` with a `keywordstyle`,
  `commentstyle`, `stringstyle`, said the way `listings` says it;
  **brace any option value carrying a bracket** — `morekeywords=[1]{for}`
  ends the environment's optional argument at `[1]` and silently drops every
  option after it: the file compiles, the listing sets, nothing is coloured;
  **`firstnumber` is not always 1** — `\lstinputlisting[firstline=10]`
  starts the gutter at 10.
  The probe also covers provenance: a caption that is an `\href` to the
  commit containing the file, with a `#L10-L25` anchor, recoverable only
  from the annotation layer. Its README records that `\href[opts]{url}{text}`
  inside `listings`' `caption=` does NOT work — `#` is TeX's parameter
  character and listings re-reads the caption, so the URL is typeset
  instead of linked.
- **Inline formula measurement**, and with it moving the measure build from
  `report.pdf` to `evidence-equation.pdf`.
- **The 38 rows with no prose-typed occurrence** (676 B4, ruled and recorded,
  not closed) and **the ~11 dropped headings with no owner object** (676 B6).
- Unopened by instruction: the 58 rewritten-reading rows; the 10 empty-LaTeX
  equation objects.
- **T-0004's remaining piece**: `--member N` as an `unpack` selector (the user
  chose only `--match` on the title, so the chapter number is printed and
  recorded but cannot be addressed), and NOT `--has equation` /
  `--has table`: `memberprofile` measures those properties and measures them
  USELESS for this purpose (see above), so that selector should not be built
  on them without a corpus where the property discriminates.

---

## Three things that cost the most time here

**Report first, build second.** Every defect that cost a full run came from
specifying against data nobody had read. The environment map in 628 fired on
zero rows of 660,504.

**A number computed across build generations is not a measurement.** 575 put
a build stamp in every model for this reason; the same class recurred as a
manifest describing a build that no longer existed.

**Six subagent reports in one session had a central claim that failed on
checking** — hence rule 19. Check the number before reading the sentence
built on it, including your own.

## Open: a ListItem's math is a widget where a Paragraph's is a transclusion (811)

Reported by a consumer of `1-s2.0-S2590118425000565-main`: "list items carry raw
`<$latex>` widgets instead of LaTeX". Measured on that document's tiddlers:

| | n | `<$latex>` | `{{…||FO}}` |
|---|---|---|---|
| paragraph | 74 | 0 | 28 |
| listitem | 106 | 40 | 0 |

`pdfdrill tiddlers` says so itself in its integrity line — *Unreferenced
(emitted, nothing points at them): 49 FO*. Those are the formulas the list items
should be transcluding.

This is a violated contract, not a preference: `src/docmodel/line_types.py`
lists `list_item` among the PROSE types that host a transclusion, and the user's
requirement of 2026-09-2x is that transclusion in TiddlyWiki is mandatory.

**Cause.** `tiddlywiki.py:1514` routes Paragraphs through
`_transclude_paragraph`; ListItems are emitted at ~1837 as
`li.props.get("content", "")` — raw, with `mathdelims`' in-place widget still in
it. Nothing else is wrong.

**Why it is not a one-line change.** `subs_by_line` is keyed by LINE ANCHOR and
holds `(offset, length, replacement)` with offsets into *that line's* text. A
ListItem's `content` is `_from_container`'s JOIN of its children's texts, and its
surface Realization spans only the container anchor (`start == end`), whose own
text is empty. So the offsets need remapping onto the joined string — or the
ListItem's realization needs to span its children, in which case
`_transclude_paragraph` rebuilds the body from lines and re-introduces the
marker text (`1. `) that `content` deliberately strips and the tiddler carries in
its own `marker` field. Either route is a real change with its own regressions;
both need measuring before and after.

## Four measurements that were of the wrong page, or of nothing (T-0024)

Four defects found while comparing two readings of the same scans (a Gemma
transcription against MathPix's) over 138 rows of one document and 29 of
another. None of them failed. Three produced numbers that looked like
measurements, and the fourth printed equation numbers against the wrong
equations.

**1. A crop came from whatever page sorted first.** `pdf_reading.rasterize`
returned `sorted(out_dir.glob("page-*.png"))` — every page in the output
directory, not the pages the caller asked for. `refine.scan_crop` and
`commands._deliver_region_crop` then took `imgs[0]`, and both share one
directory across calls: `<doc>/refine/_pages` is reused by every row of a run
and survives between runs (`commands.py` keeps `sc.blob_dir / "refine"`), and
`snip/` keeps every page it has ever rendered. So after the first row, each
crop came from the LOWEST page number present — at its own region's
coordinates, scaled by its own page's dimensions, so the error grew down the
page rather than announcing itself.

Measured: re-cropping each row from its own page changes the ink signature on
**131 of 138 rows** of the Killing document (135 of 138 on an earlier run of
it, 27 of 29 on Hilbert), and a "lowest page present so far" model reproduces
the stored signatures **138 of 138**. Replaying a row with the page it was
actually cropped FROM matched 8 of 138; replaying with the row's OWN page
dimensions matched 138 of 138 — which is what says the scale came from the
right page and the pixels did not. Every raw refine ink number taken before
this fix is of a crop of the wrong page.

`pdf_reading.render_crops` already defended against exactly this, with the
reason in a comment, and `pyramid.py` defends by unlinking each page after use
— two of four call sites, which is the usual sign the guard belongs in the
callee. It is now there: `rasterize` returns only the pages asked for, in page
order (not filename order — `page-11232` sorts before `page-9999`), and
`page_of(path)` is the one rule for reading a page number back out of a name.
The files themselves are left alone.

**2. `accept` crashed on a row it could not compare.** `select` writes
`ink_before` only for the rows its own ink gate reached; `measure` writes
`ink_after` for every validated row. A row with one half of a comparison met
`after < before` — `int < None`, a TypeError — which ended the run BEFORE
`record`, so proposals that had already been accepted and verified were never
attached to the model. The comparison is now `refine.ink_verdict`, which has a
third answer: `NO_REFERENCE` is not a rejection, nothing about the proposal
has been found wanting, and the row stays proposed for a later run that gates
it.

**3. A row with half a comparison was counted as measured.** `ink_delta` was
`after - (before or 0)`, which is `after`: a positive number that reads as a
proposal that worsened the reading by exactly its own distance from the scan,
written into `changes.json` as a measurement. `refine.ink_delta` returns None
without a reference, and `measure`/`accept` each report `no_reference`
separately. Note that 0 is a reference — a proposal matching the scan exactly
has `ink_after` 0 — so the test is `is None`, never falsiness.

**4. Three numbers that belonged to three rows went to three different
objects.** Hilbert 1902, book p.96: MathPix set three separately numbered
inequalities as ONE `math` line holding `\begin{array}{ll}`, with (1) (2) (3)
printed down the inside of its own box (y 1057/1120/1182, all three centres
within the block's y 1061..1231). `array` is deliberately not an alignment by
name — it is also how a matrix body is written, and splitting a matrix on its
`\\` takes it apart silently — so `alignment_rows` returned `[]`, the split
declined (`equation_number_blocks_unsplit` 1), and the nearest-number fallback
put every number one object too high: (1) on the line above, which prints
none, (2) on the array, (3) on the `gathered` block below it.

This was reported as a representation limit — one `refnum` per DocObject
cannot describe a display whose rows each carry a number. It was not. The
split that gives each row its own object, its own number and its own region
band already existed (823) and declined to fire. What it lacked was permission
to read an `array` as an alignment when the printed page says it is one:
`numbered_rows(latex, count)` widens the environment set only where the
numbers corroborate — `count` rows against `count` numbers inside the block's
own box, which is the same unambiguous-evidence test the existing refusals are
built on. A fenced `array` (`\left(\begin{array}…`) stays a matrix whatever is
printed beside it, and fewer than two numbers is still the ordinary one-number
case. After: (1) (2) (3) on the x/y/z rows and (4) on the line that prints it,
with the two lines that print no number carrying none.

Fixing that exposed a fifth, latent: `_ENV_OPEN` matches `\begin{array}` to the
end of the NAME, so the column spec `{ll}` stayed in the body and became the
first characters of the first row. `alignat{2}` carries a column count the same
way and always did. `_after_env_args` skips an opener's own `[pos]` and `{spec}`
— only for the environments that declare one, because a brace group is ordinary
content elsewhere (`\begin{gathered} {x \over y} \\ z`) and eating it would
lose the first row's first term.

**What is NOT fixed here, and remains for the owner:** `select` overwrites the
request file's `basis` and `author` on every row it keeps (`"basis":
"inferred"`), while `ingest` honours them — 109 of 138 request rows were
rewritten to `inferred` in one run. That is a decision about whose attribution
wins, not a defect with one right answer.

---

## T-0026 — the model lane: a second reader that writes MathPix's file (2026-10-19)

The user's decision: replace Tesseract with a Gemma-4 reading, and make the two
lanes as alike as possible. `~/Gemma4` was the proof of concept; this is
pdfdrill's own implementation of it, scored against MathPix's readings of the
same pages.

**The lane.** `gemmaocr` mirrors `mathpix` deliberately — the same two files
under the same names beside the PDF (`<base>.lines.json`, `<base>.md`), the
same `{status, files}` result, the same idempotence, the same refusal inside
`no_paid_steps()`. Three stages, and only the middle one costs anything:

    render    gs >= 400 dpi (pdf_reading.rasterize)       free, offline
    read      page -> Markdown, via vision_router         PAID
    assemble  Markdown + the page's ink -> lines.json     free, offline

`assemble` is a separate public function because a 10 EUR account cannot fund a
verification loop. Every number below was obtained from Markdown already on
disk, at no cost.

**Scored against MathPix** (`pdfdrill linescmp`, boxes normalised per page
because the two readings are in different pixel frames — MathPix 1,220 x 1,880,
this reader 1,952 x 3,008 for the same page):

| document | reference lines | found at IoU>=0.5 | median IoU | typed alike |
|---|---|---|---|---|
| Killing 1889, 48 pp, bitonal | 1,694 | **1,581 (93%)** | **0.826** | 1,575/1,581 (100%) |
| Hilbert 1902, 10 pp, greyscale | 306 | **250 (82%)** | **0.770** | 239/250 (96%) |

Per type on Killing: text 1,379/1,434, math 150/193, equation_number 41/51,
section_header 8/9, footnote 3/4. `model` builds **1,377 objects** from it
(MathPix's reading gives 1,251, the POC's 1,332) with **4 Footnote objects on
the right pages carrying bodies of 89/227/419/1,644 chars** — `footnote_adopted
3`, `footnote_span_not_located 1`, and no duplicate-Footnote class.

**The shapes that had to be copied exactly, each measured off a bought reading
and each one a thing that silently does not work otherwise:**

- A footnote is a CONTAINER: one `footnote` line with EMPTY text, `children_ids`,
  region = the union, and the printed lines as `text` children carrying
  `parent_id`. The first child's `text_display` opens `\footnotetext{` and the
  last closes it. That wrapper is what `FootnoteProcessor` reads for the body —
  0 bodies without it, 3 with. MathPix uses the same shape for `title`,
  `authors` and `section_header`.
- A two-line section heading (`§ 16.` then its title) is one container, 9 of 9
  on the reference document.
- A table is one `table` line carrying the whole `tabular` plus one
  `simple_cell` per cell with its own tight box.
- The folio and the running head are TWO `page_info` lines: they are printed at
  opposite ends of one row, and one box spanning that row scores zero against
  both while declaring a row of body text to be furniture.
- `source` goes in the FIRST bytes of the file. `commands._lines_json_source`
  reads only the head — "both producers emit `source` near the top" — so a
  1.5 MB reading declaring its producer at the end declares it to nobody. The
  lane's own cache check missed and it set out to buy a reading already on disk.

**Geometry is by alignment, not by coordinates.** The model returns no boxes, so
the items (printed lines, in order) are matched to the page's ink rows (in
order) by a monotone DP: an item takes one row, or k consecutive rows
(`MAX_ROWS_PROSE` 2, `MAX_ROWS_BLOCK` 12 — MathPix groups a multi-line display
into one `math` line), or a row is skipped, or an item gets no row. A greedy
1:1 walk is wrong in the case that matters: one mismatch early shifts every box
after it, which is a crop of the wrong line with nothing in the output saying
so — T-0024's defect arrived at from the other side.

**Four measured constants, each from a failure:**

| constant | what it fixes | measured |
|---|---|---|
| the MISS move in the DP | a page with more lines than ink rows was infeasible, so it placed NOTHING | 34 boxes of 311 before |
| `rows(max_height=6*lh)` | a 97 x 3413 gutter band collapsed a page to one row | score 6% -> 42% |
| `drop_scan_edges` + `drop_speck_rows` | border slivers joined text rows and stretched them to the page edge | 42% -> 73% |
| `prune_row_outliers` (far AND small) | 1-2 px flecks in the outer margin, in clusters | 73% -> 82% |

`prune_row_outliers` needs both conditions: far-and-large is an equation number
(deliberately at the margin, 45 x 40 px, and its ink is needed to cut it out of
the display's row), near-and-small is an `i` dot. Only far-and-small is nothing.
It measures distance to the nearest LARGE component, because flecks arrive in
pairs and peeling inwards stops at the first one.

The equation-number split is the same lesson twice: taking a geometric fraction
of the host box found **1 of 51**, because MathPix's number boxes are 3.6% of
page width and one line tall while the display beside them is 27-54% wide and
up to six rows tall. Cutting the host's own components at their widest gap
finds 41, with the gap threshold in LINE HEIGHTS (the margin runs 70-204 px on
pages of the same width, so a page-width threshold either misses the tight ones
or starts cutting displays apart).

**The budget is part of the design.** The account is a fixed prepayment: 10 EUR,
0.28 spent over three days of POC testing. Measured from the POC's own
`run.json` files — 390 pages billed, 1,711,193 tokens — that is **0.000718
EUR/page**, so 9.72 EUR is ~13,500 pages, ~280 Killing-sized books, 0.41 EUR
for the 576 remaining volume pages, and nowhere near the library's 11,989
documents. When it empties the endpoint stops answering MID-DOCUMENT, so:

- `gemmaocr` is declared `network: true` and estimates the read against
  `PDFDRILL_OCR_BUDGET_EUR`, REFUSING rather than starting one it cannot finish;
- `callog.log_call(usage=…)` records the provider's own token counts and
  `pdfdrill spend <pdf>` adds them up — 447 kept every prompt, 466 made it
  identifiable, neither recorded a number;
- `commands._auto_run_offline_only(name)` makes the two places where a command
  calls another directly (`cmd_model` and `cmd_visionocr` both reach for the
  keyless OCR lane) ASSERT that the step is offline. The planner enforces
  "declared, never auto-run" only for the steps it inserts; those two sites are
  invisible to it, and they are where a free command silently becomes a bill the
  moment an engine changes underneath.

**Makora is its own provider**, not `NOVITA_API_BASE` pointed elsewhere: the key
would be filed under a Novita name, and the hosts differ — Makora needs
`{"reasoning_effort": "none"}` or it loops on an image prompt, and it hung on
requests with four or more images. `cost_rank 0`, first for both page tasks.

**Open, and for the owner:**

1. `MAKORA_API_KEY` is not in pdfdrill's `.env` — only in `~/Gemma4/env.txt`.
   One line (see `.env.example`), plus `PDFDRILL_OCR_BUDGET_EUR`.
2. Novita's `gemma-4-26b-a4b-it` now answers a vision request with
   `HTTP 400 "vision type image_url is not supported"`. That is the fallback
   provider for both page tasks AND the route `snip --gemma` is documented on,
   so Makora is currently the only working host for either.
3. ~~`ocr` is still declared offline, because its engine is still tesseract. The
   flip to `network: true` belongs with the engine swap.~~ CLOSED by 905k: the
   engine is gone and the verb reads nothing, so there is no network lane to
   declare. `ocr` is a POINTER that prints the lane contract's decision and the
   command that replaced it; it writes nothing and spends nothing, which is why
   it stays offline and exempt from `_auto_run_offline_only`'s concern.
4. Not implemented: no YOLO, so a figure the model did not describe gets no
   `diagram` box (3 such lines on the Hilbert pages), and `math_regions`
   (inline formula boxes) is not produced — pdfdrill reads neither field today.
5. Hilbert's 82% against Killing's 93% is the MODEL's reading, not the geometry:
   it transcribed a ruled table as four display equations, so the reference's 15
   `simple_cell` lines have no counterpart at all. Prompt work, not code.
6. `glyphdrill` (under development, for large equations) replaces or complements
   this lane. The seam is `vision_router` — a provider entry and a task — and
   `linescmp` scores whatever it produces against the same references.

### T-0026 follow-up — the OCR / born-digital pair, and the candidate pool

The user's next ask: one good SCAN and one good BORN-DIGITAL document, read by
both routes, to show progress in each direction and the remaining distance to
MathPix. Both halves need a MathPix reading as the yardstick, so the pool is
the library documents that hold one.

Surveyed 2026-10-19 over all 1,607 held MathPix readings, restricted to 10-25
pages and classified by how much text the PDF's own layer yields on pages 1-3
(`pdftotext -f 1 -l 3`, under 200 characters = a scan): **620 candidates, of
which 7 are scans and 613 are born-digital.** The scarce half is the OCR half:

    10 pp  hilbert1902-foundations-math10   (already an example)
    14 pp  penev_B
    18 pp  US6100897A                       a patent
    20 pp  UM-CS-1988-053                   a 1988 typewritten tech report
    21 pp  groups
    21 pp  844673279-LESSON-1-...           a chemistry lesson, 85 chars
    22 pp  penev_A

`penev_A` is the strongest OCR half: it is the document `footnote_extent` was
measured on (45 of 45 same-page pairs; 48 printed footnotes that once gave 93
objects), so it exercises the container class the lane copies hardest. A
typewritten report (`UM-CS-1988-053`) would be the harder typography.

For the born-digital half the choice is wide and should be made on content —
tables plus display equations. Note the instrument already exists on that
side: `conformance` (879) measures our born-digital reading against MathPix
per line TYPE, and `linescmp` adds the geometry half. Running both on one
document is the "distance to MathPix" the pair is meant to show.

**What it costs:** the born-digital half is free (pdfminer). The OCR half
needs a paid Gemma read of a document for which no Markdown is held — about
0.016 EUR for 22 pages at the measured rate — so it is blocked only on
`MAKORA_API_KEY` being present in `.env`, not on anything in the code.

### T-0026 follow-up (2) — penev_A is a 4-UP SCAN, and the lane assumes 1-up

`penev_A` was chosen as the OCR half and read: 22 sheets, 3,007 lines, 0.0158
EUR on Makora (86,730 in / 67,927 out, 10 min). MEASURED against the held
MathPix reading of the same 22 sheets:

    transcription   89.4% of MathPix's words present   (as a bag of words)
    reading order   71.2% of them in the same order    (LCS over words)
    geometry        474/3,080 lines at IoU>=0.5 (15%), median IoU 0.316
    typed alike     405/474 (85%)

The 18-point gap between the bag and the sequence is the whole finding: the
words are THERE and in the wrong order. One fact explains both that gap and
the geometry, and it is a property of the document:

**each PDF sheet carries two to four printed book pages, side by side and
stacked.** MathPix types them `column` (2 per sheet typically, 4 on sheets 4
and 9) and its `page_info` folios say it outright — sheet 2 carries `iv`, `v`,
`vi`, `vii`; sheet 8 carries `19`, `20`, `21`, `22`. 22 sheets, ~88 printed
pages.

The lane assumes ONE printed page per sheet, at both stages:

- the PAID stage cuts the sheet into six FULL-WIDTH horizontal strips, so every
  strip spans all of the sheet's printed pages and the model has to choose an
  order within it. It chooses sensibly (it emits `<!-- page 9 | -->` furniture
  comments and the folios at the right places) but the choice is per strip
  chunk, so the sheet's pages interleave at chunk boundaries — measured on
  sheet 5, our first 43 lines are the left page's first 43 in order, then the
  folio `7`, then the next printed page, while MathPix reads all 59 of the left
  page first.
- the FREE stage (`align`) is a monotone matching of ONE item sequence against
  full-width ink rows. On a 4-up sheet four printed pages share every ink row,
  so the matching is not merely inaccurate, it is describing the wrong object.
  Measured on sheet 5: 81 ink rows for 144 items, rows spanning 317 px where
  the line pitch is 48, and boxes landing on every fourth item.

So the geometry number is not a tuning failure and no threshold reaches it. The
missing capability is **n-up sheet segmentation**: split the sheet's ink into
its printed-page blocks (vertical gutter, then horizontal band), then strip
WITHIN a block and align WITHIN a block. That fixes the order and the geometry
together, and it changes the paid stage, so it costs one fresh read (0.016 EUR).

Not every candidate has this shape. Columns per sheet over the seven scans:
`UM-CS-1988-053` 0 on all 20 sheets and `groups` 0 on all 21 — single printed
page per sheet, the shape the lane is built for. `penev_B` is 2-up on 10 of 14,
`US6100897A` mixed, `hilbert1902` 1-up (which is why it scored 82%).

Also exposed, and worth fixing whatever is decided: `--force` re-READS every
page, so there is no way to EXTEND a reading to more pages without re-buying
the pages already on disk. The per-page Markdown cache under
`.drill/gemmaocr/page-NNNN.md` already makes the data available; what is
missing is a flag that means "top up", not "redo". On a metered prepayment that
distinction is the one that matters.

### T-0026 follow-up (3) — the four missing steps, taken over into pdfdrill

The Gemma4 proof-of-concept read the same 22 sheets to 89% of MathPix's boxes
against this lane's 15%, and named four steps the lane did not have. All four
measured on penev_A, independently reproduced here by scoring the POC's own
merged output with `linescmp` (2,740/3,080 at IoU>=0.5, median 0.824, 2,590
typed alike — its table to the digit). The POC's numbers were right.

**1. N-up sheet splitting** (`src/pdfdrill/nup.py`). Each sheet carries four
printed pages. `detect` finds the gutters, `shape` decides ONE imposition for
the document and `merge` brings the reading back to sheet coordinates. Three
things in it are not in the POC's `split_nup.py` and each was forced by a
measurement:

  * the gutter is the blank run NEAREST THE MIDDLE, not the widest (the POC
    has this too, and it is the detail the detector rests on: a sparse page
    has a wider blank run inside it than the gutter);
  * a BAND gutter is sought only INSIDE a column a vertical gutter made.
    Sought unconditionally, all three of killing20's probe sheets, two of
    collatz14's and one of hilbert10's were cut in half through their own
    text. Printed text runs across the full measure, so a vertical blank
    channel is extraordinary and a horizontal one is ordinary. The cost is
    that a STACKED 2-up with no vertical gutter reads as 1-up; `--nup 1x2`
    says so explicitly;
  * the shape is a property of the DOCUMENT. Per sheet, penev_A reads as 2x2
    on 19 of 22 sheets and 2-up/3-up on sheets 1, 3 and 16 — which do carry
    four pages but lack the ink to prove the gutter. Trusting each sheet gives
    84 printed pages where there are 88. The POC always cuts 4 and gets 88 by
    assumption; `shape` gets 88 by majority vote (21/22) and still reads the
    1-up documents as 1-up, unanimously.

**2. The layout detector** (`src/pdfdrill/yololayout.py` + `yolo_driver.py`,
command `yololayout`). DocLayout-YOLO + PDF-Extract-Kit MFD, run in a SEPARATE
interpreter because they are torch — wrapped the way poppler and ghostscript
are, named by `PDFDRILL_YOLO_PYTHON`, reported by `doctor`, cached one TSV per
page. Display boxes become ANCHORS in the alignment (`align_anchored`), which
is the real algorithmic change: `align` is one monotone walk and its errors are
cumulative, so a display whose row count it guesses wrong shifts every box
below it. MEASURED free on Killing pages 1-20, same Markdown, same reference:

    ink walk alone   705/733 (96%), median IoU 0.824, math 73/81
    + anchors        715/733 (98%), median IoU 0.832, math 76/81
    + sanitizer      714/733 (97%), median IoU 0.830

So anchors are worth +10 lines on a document that was already good, and the
sanitizer is NEUTRAL there (-1). It is kept on because the boxes it is for are
the detector's, which are loose at the left and right by construction.

**3. The sanitizer** (`src/pdfdrill/sanitize.py`). claim -> grow -> shrink ->
check against the page's ink, whoever made the box. On the 22-sheet reading it
tightened 820 boxes, claimed 1,142 stray components and re-unioned 41
containers, and named the 829 `geometry: none` + 95 `pending-split` lines it
could not place. `pending-split` is an INTERNAL marker of `align` and should
never have reached a file at all.

**4. Figure whitening.** Before the paid read, so the model stops transcribing
a picture, and before the ink pass, so a figure's strokes never join a text
line. 25 of penev_A's 88 printed pages carry a figure box.

A HAZARD THIS CREATED, and it is a money hazard: the per-page Markdown the
paid read writes is named for the PRINTED PAGE, so a changed map makes page 1 a
different picture than the page-1 Markdown on disk was read from — and a
resumed run would serve it anyway. Live on penev_A, whose first reading
numbered 22 SHEETS 1..22 while the split numbers 88 printed pages 1..88. The
Markdown now lives beside the printed page it was read from, the map is
compared before anything is written, and a changed map MOVES the old directory
aside rather than removing it, because what is in it was paid for. A 1-up
document's existing Markdown is carried over, so this upgrade re-buys nothing.

Also fixed on the way: the cost preflight now runs INSIDE the lane, on the
printed pages still to be read, not on the PDF's page count. For penev_A that
is 88 and not 22, and for a resumed run it is only what is left to buy.

### T-0026 follow-up (4) — penev_A re-read on the printed pages: 15% -> 88%

The paid re-read, 88 printed pages, 363,642 tokens in / 77,188 out, estimated
0.063 EUR. Scored with `linescmp` against the same MathPix reading; the POC's
column is ITS output scored by the same instrument, not its own table.

                                sheet read   printed-page read   POC
    lines boxed at IoU>=0.5     474 (15%)    2,696 (88%)         2,740 (89%)
    median IoU                  0.316        0.820               0.824
    typed alike                 405          2,572               2,590
    text                        439/2363     2,299/2363          2,306/2363
    display math                5/116        110/116             110/116
    equation numbers            3/116        112/116             112/116
    diagrams                    0/14         13/14               13/14
    charts                      0/11         11/11               11/11
    footnotes                   3/28         22/28               19/28
    words present               91.9%        93.5%               94.2%
    words in order              71.2%        87.8%               88.0%

Level with the POC on everything except THE TABLE OF CONTENTS: 49 of 79
`table_of_contents_row` and 38 of 83 `table_of_contents_item` against 74 and
48. Neither reader TYPES a contents list (0 of 79 typed alike for both), so it
is a geometry gap on two sheets and it is the whole of the remaining point.
That is the next thing to look at if this document is pushed further.

`folios_ascending` is in the lines.json `ocr.nup` block and is the evidence
that the reading order was right: every comparable adjacent pair ascends.

Also added, because taking the four steps over required it and the gap was
already recorded here: **`gemmaocr --rebuild`** assembles the lines.json again
from the Markdown already read and spends nothing, refusing if any printed
page has none. The assembling half of the lane is offline by design; without a
verb for it, re-measuring a change to the geometry meant either editing a
scratch script or re-buying the document.

Example folder: `~/pdfdrill-examples/gemma-lane/penevA22/` (85 MB), with the
previous sheet-level reading kept beside it as `penev_A.sheetread.lines.json`
for the comparison. Inspector audited as the other four were: 1,280 elements,
0 boxes outside their own page's frame, 0 missing, 24 zero-area, furthest edge
0.999, no empty pages.

STILL OPEN on this lane: `page_info` is 15 ours against 98 reference. Reading
a single printed page, the model writes the folio as a bare line instead of
the `<!-- page N | Head -->` furniture comment it emits for a sheet, so folios
land as `text`. The detector's `abandon` class (running heads and folios) is
already parsed and unused — retyping a line whose box sits inside an `abandon`
box would fix it. It costs nothing in the score (page_info is excluded on both
sides) and it is a type disagreement with MathPix, so it is honesty rather
than accuracy.

---

## T-0026 follow-up (5) — the lane contract, and the OCR path used for geometry

**`docs/LANES.md` is the contract.** Five lanes in a fixed order, one pure
function (`ocr_router.choose_route`), the same words from `route`, `drill` and
`doctor`: the PDF's own text layer (free) → the arXiv author's LaTeX (free) →
`gemmaocr` (metered, 0.000718 EUR/printed page) → `mathpix` (paid) → the free
geometry-only lane. Read that file rather than this summary.

Two things the old router got wrong, both measured, both worth keeping written
down because each looked reasonable when it was written:

- **`model` bought MathPix whenever a key was present** and no lines.json
  existed, which made it a paid command reachable from about forty places that
  do not say so. It bought 9 pages of arXiv 2402.13444v1 during this session,
  whose whole purpose was to measure the free lanes. The planner's rule — a
  paid layer is DECLARED and never auto-run — had been written for `--ensure`
  and did not reach one level down. `model` now names the lane;
  `model --mathpix` is the opt-in.
- **The scan lanes split on page count** (">20pp → MathPix"). That threshold
  was set when the only alternative was a 50 s/page vision call and left
  standing after `gemmaocr` made the large book the cheap case. Page count no
  longer selects a lane.

**`PDFDRILL_SANDBOX=1`** makes a keyed machine answer as the keyless sandbox
does: every name in `env.CREDENTIAL_NAMES` reads empty and `.env` is not read.
`PDFDRILL_OCR_BUDGET_EUR` keeps working — a budget of nothing is not no budget.
This is how a lane decision is checked before it ships.

**`drill` goes the whole way now.** It stopped at Markdown, which on an arXiv
paper left a geometry-less source model on disk and no inspector at all; the
next command to ask for one got 131 elements with 131 missing boxes, because
`model` saw MODEL_BUILT and returned the cached one. The chain is now the cheap
probes → `route` (reported, with the reason) → the lane, **but only a free
one** → `model` → `md` → `geometry --layout` → `inspect`. A paid lane is named
with its exact command and not run.

### The geometry half of the OCR path, which costs nothing

`geometry --layout` (`src/pdfdrill/layoutgeom.py`) gives the detector's boxes to
the objects whose printed form is not their text — an inline formula's text is
`ax^2+bx+c = 0` and the page carries a picture of it, so no text match can
reach it. Chosen by a MONOTONE WALK between the objects the text match did
place: each unboxed object may only take a box of its own class inside its
neighbours' window, each box once, and where the window holds no box of the
right class the object keeps NONE. The window is built from BOTH edges of an
anchor — with tops alone, 23 of 26 candidates found nothing, because an inline
formula sits inside its host paragraph and the next anchor's top is below it.

Measured on arXiv 2402.13444v1, 9 pages, keyless, from cold:

    elements with no box      131 of 131   drill as it was (source model)
                               54          + the text match
                               29          + `raw_text` consulted, so the
                                             author's .bbl entries are matched
                                8          + geometry --layout

0 boxes outside their page frame, 0 zero-area, furthest edge 0.949. The
remaining 8 are 2 Formula, 2 Table, 2 Reference, 1 Section, 1 Paragraph.

`gemmaocr --geometry-only` is the keyless install's scan lane: split, detect,
and a lines.json in which every line has a box and a type and no text — the ink
gives the rows, the detector gives each row its type, a figure is one object
rather than the rows its strokes form. 12 printed pages of penev_A, 273 typed
boxed lines, 0.0000 EUR. `model` is NOT its consumer (a model keeps what has
prose); `linescmp`, `geometry --layout` and the detector cache are.

A Reference the bibliography made from a `\cite` key is **not an object with a
missing box** — it is an object with nothing to box. `layoutgeom.not_printed`
says so and the inspector records it as `not_printed`, so an audit stops
counting 27 citation stubs as missing geometry.

### `page_info`, closed

The open item above is done. `gemma_reader.retype_furniture` retypes a `text`
line as `page_info` on FOUR conditions, and the conjunction is the whole of it:
the detector's `abandon` box, the margin band (top/bottom 12%), a short line
(≤55% of the measure), and a detector box no taller than 2.2 line heights.

Measured the other way round first: with the band and the detector's word
alone, 128 lines were retyped and the score fell from 2,696 of 3,080 reference
lines to 2,617 — 79 lines of body text typed as furniture and dropped from the
Markdown, because the top twelfth of a scanned page holds the first body line
as often as a running head. With all four, `page_info` is **63** (was 15,
reference 98) and the score is unchanged at 2,696/3,080, median 0.82, 2,572
typed alike. Each condition alone is dangerous in the same direction:
`markdown()` drops a `page_info` line, so a wrong retype deletes prose, and a
deletion is not visible in the result.

STILL OPEN: the table of contents, unchanged — 49 of 79
`table_of_contents_row`, and neither reader types a contents list. A leader-dot
run is a measurable thing and nothing looks for it.

### tesseract is out of the distribution, and what replaced it

`bootstrap.sh` installs no OCR engine, `doctor` looks for none, and no module
invokes one. `tests/test_no_ocr_engine.py` holds that shape: an argv head or a
`which()` probe for any of eight engines fails the suite. Proved at runtime too
— a trap script named `tesseract`, first on PATH, logged **0 calls** across two
full `drill` runs and `ocr`/`tsv`/`continuity`/`elements`/`fontid`/`doctor`.

Seven features had been getting word geometry by rendering a page and running
tesseract: `tsv`, `elements`, `continuity`, `ordered`, `autosegment`, `fontid`
and `model`'s own fallback. That made an OCR engine a dependency of
*measurement* rather than a reading lane. `src/pdfdrill/word_boxes.py` now gives
three answers and no fourth: the PDF's own text layer (word boxes **with their
text**, in points), the page's own ink (boxes with **no** text, in render
pixels), or nothing — plus the lane that would change that, in `route`'s words.

**The inter-word gap is 0.35 of the row's median glyph height.** Measured on
2402.13444v1 (born digital, so its own text layer is the ground truth for a
word's count *and* its extent): ink words matched the text layer's 5,264 word
boxes at IoU ≥ 0.5 —

    gap      0.25   0.30   0.35   0.40   0.45   0.50   0.60
    matched  77.6%  80.8%  82.9%  82.8%  82.3%  77.6%  61.7%
    n/truth  1.148  1.032  0.951  0.945  0.939  0.900  0.767

0.35 is the peak and the count closest to 1 from below; mean IoU of a matched
box is 0.786 there. The ~17% that never match are mostly the inline formulas of
a math paper, where "one word" is not a thing the ink can know.

`fontid` is the ink route's natural consumer — it never wanted the words, it
wanted the pixels a word occupies. Its "field" was an OCR block and is now a
SIZE BAND (quarter-of-median glyph height), because a field's defining property
here is its type size. On hilbert10 (a keyless scan) it reports 3 fields,
predominantly serif, and labels each sample `(ink: no text read)` rather than
printing `''`.

LOST, and named in `docs/LANES.md`: `continuity`/`elements`/`ordered`/
`autosegment` on a SCAN (they need a word's text, which no free lane reads off
one); cardinal page orientation in `scandrill` (OSD could tell 0 from 180, the
ink cannot — `measure_orientation` now records SIDEWAYS as a warning and rotates
nothing); the `scan --ocr` text-layer graft (refused, because a text layer on a
scan misroutes `route` to the born-digital lane); and two passes whose only
caller was the retired engine (the text-layer merge → use `linescmp`; the
barcode pass → `pdfdrill qr` already does it with the same zxing-cpp).

### `drill` reports what each part cost in seconds

The sandbox question is not only whether every report finishes. `drill` times
every step and ends with one line per part, the total, and the per-page rate —
the only figure that transfers to a document of another length. Measured cold,
keyless, on this machine:

    2402.13444v1 (9 pp, born-digital)   TOTAL 46.75 s   5.19 s/page
      geometry --layout 42.36 s (91%)   inspect 3.07 s (7%)   model 1.05 s (2%)
      size/fonts/abstract/toc/route/md/status together under 0.2 s

    hilbert10 (10 pp, keyless scan)     TOTAL 39.35 s   3.94 s/page
      gemmaocr --geometry-only 39.32 s (100%)

So on both lanes the cost IS the layout detector, and everything else is noise.
That is the number to watch when the test documents arrive.

## The documented suite grew by 23, and a bare `pytest` is no longer a second suite (T-0078 follow-up, 2026-10-26)

**Any suite number quoted before this date is not comparable with one quoted
after it.** Two things changed, both deliberate:

  * `pyproject.toml` now pins `testpaths = ["tests"]`. It used to set nothing,
    so `python3 -m pytest` from the root walked the whole tree and collected
    5955 where `python3 -m pytest tests/` collected 5932 — the difference being
    `src/pdfreader/out/test_table.py`, which had no package beside it and so put
    `src/pdfreader/out` first on `sys.path` for everything collected after it.
    From that point `import langdetect` found a subprocess tool, not the
    package. A peer session measured 33 failures from that one insertion, and no
    two runs agreed, because the poisoning depends on collection order.
  * that file is now `tests/test_table.py` (owner's call: "Move under tests/"),
    so the documented command covers its 23 table-pipeline tests. They were
    never run by anything routine before.

The two commands now collect the same number, which is the property worth
keeping: measured in a fresh clone on the documented base install, **5884 and
5884**. In-tree with every extra it is higher, as always — quote the install
with the number, per CLAUDE.md.

`pytest tests/…` (the console script) also works now. It never did: it does not
put the current directory on `sys.path`, so the six files here that import each
other (`from tests.test_publish_ready import …`) were a collection ERROR, not a
failure, under any invocation but `python3 -m`. `tests/conftest.py` puts the
repository root on `sys.path` once.

### A missing optional tool is a skip that names the tool

Seven tests FAILED on the documented base install, reading `LTChar.glyphname`
(3) and `LTChar.invisible` (4, through `src/pdfreader/docmodel_six.py:2936`).
Both come from `vendor/pdfminer-glyph-identity.patch`; neither exists on PyPI's
pdfminer.six. The suite was reporting seven defects in the reader on a machine
where only a tool was missing. They now ask
`pdfreader.build_identity.missing(...)` — the one function that asks the LOADED
module — through `requires_fork(...)` in
`tests/test_pdfminer_fork_survives_pip.py`, and every skip names
`bash vendor/install-pdfminer-fork.sh --user --rebuild`. README's install block
names that step too: `pip install -e .` alone cannot do it, and the fork cannot
be a requirement because it is a local patch, not a package on PyPI.

## The author's LaTeX now renders, and what refuses it is named (T-0080 items 1-2, 2026-10-27)

**31.5% of the author's expanded maths could not be rendered, and the page said
nothing.** Measured read-only over the drill library through the same four
functions `cmd_injectlatex` uses — 530 e-print sources readable, 441 with at
least one display equation, 23,608 display equations expanded and each given to
KaTeX 0.16.9 (the version `docinspect._KATEX_JS` loads from cdnjs), with
`throwOnError: true`:

| | equations |
|---|---|
| expanded display equations measured | 23,608 |
| refused by KaTeX 0.16.9 | 7,438 (31.5%) |
| refused with one of six LaTeX-only commands as the first error | 1,163 |
| now rendering, after `latex_only.resolve` | **1,065**, 0 newly broken |
| still refused | 6,373 |

`src/pdfdrill/latex_only.py` holds the six as a stated table, each with the
example it is stated by and the population it came from: `\ensuremath` (732
equations, 30 documents), `\vspace` (352/18), `\xspace` (53/8), `\centering`
(17/3), `\label` (7/1), `\noindent` (2/2).

**The expander was not the thing to fix.** An author writes
`\newcommand{\dom}{\ensuremath{\mathbb{D}}}` and `expand_macros` substitutes
the body verbatim, which is what a macro IS. `\ensuremath` means "be in maths
mode even if you are not", and a formula already is — so the expansion is
correct and unrenderable at the same time. `latex_source.expand_math` is the
maths-side entry point (`expand_macros` then `latex_only.resolve`) and the only
call a new maths site should make. `latex_original` is never touched.

**The two graphics sites deliberately do NOT resolve.** A Diagram's or Table's
`latex_code` goes to a real `xelatex` run (`pdfdrill svg`), where `\vspace`
means what it says. Both sides call the same expander on the same kind of
string and the only difference is what the result is for, so the split is
stated in `tests/test_a_formula_carries_no_latex_only_command.py`
(`GRAPHICS_ONLY`) and a new maths site that calls the raw expander fails there.

**Not resolved, on purpose, each for its own reason.** `\ref` (35 equations, 18
documents) and `\eqref` (20/7) PRINT a number this pass does not know, so
dropping them would silently remove content; `\textsc` (24/8) and `\emph` (8/7)
are formatting KaTeX cannot do, so translating them would be a guess.
`tikzcd` (1,072 equations, 17 documents) and `tikzpicture` (545/8) are pictures
captured as equations and no rewriting reaches them. And 374 of the 456
distinct undefined names occur in ONE document each (2,084 equations) — the
author's own macros `extract_macros` did not pick up, which is a gap in macro
COLLECTION and the corpus-wide form `docops.katex_notice` already records.

### Three quiet defects in the inspector, all now loud

1. **`throwOnError: false`.** KaTeX's default on a formula it cannot parse is
   to put its own error INTO the output as red text containing the source, so
   `renderMath`'s `catch` never fired and every count of failures was zero.
   6,373 formulas were being shown that way.
2. **One grey box for two different things.** `katex-missing` meant both "KaTeX
   did not load" and "KaTeX refused this formula". A reader could not tell a
   broken formula from a broken network, and the second says nothing about the
   formula. `katex-refused` is now its own mark, and names what KaTeX objected
   to.
3. **`props["latex_original"]` is empty on the documents this is for.**
   `cmd_injectlatex` attaches the author's form to the matched equation as a
   `provenance="tex"` REALIZATION and writes props only when there was no
   MathPix scaffold. Measured on the two gate papers after
   `pdfdrill injectlatex`: of 254 maths objects, **0** carried
   `props["latex_original"]` and 27 carried it on a realization. A props-only
   reader would have shipped a feature that does nothing on its own gate.

The inspector now shows `latex_original` as TEXT (never rendered — it still
holds the author's macros) and renders two forms: the document's own reading
and, beneath it, the author's. The count is taken **once over every renderable
form at load** (`katexAudit`), not accumulated by `renderMath`: the inspector
renders lazily, so a tally built while rendering reports what the reader
scrolled past and would say "0 refused" about a document whose every formula is
refused. `window.__katexRefused` is the hook a test or drillui reads.

**Resolving also improved matching.** `latex_similarity` compares the EXPANDED
forms, so on 1702.06385 `injectlatex` went from 15 of 19 display equations
attached (4 unmatched) to **18 of 19** (1 unmatched), with no change to the
matcher.

### The gate, on the page's own KaTeX

| document | maths objects | rendered forms | with the author's latex | refused |
|---|---|---|---|---|
| 1702.06385 | 178 | 196 | 18 | **0** |
| 2210.01629v3 | 49 | 61 | 12 | **0** |
| 2510.15795 (diagrams) | 263 | 272 | 9 | **3, each listed** |

The three on 2510.15795 are `tikzcd` blocks the author wrote as display
equations, so their author's reading is a picture body KaTeX cannot render.
They are marked where they appear and listed in the page's own banner.

### What is left on item 3 (T-0045's merge), measured

Geometry is already there and MEASURED for everything that carries a box. What
has none is the author's own pictures:

| document | elements | boxed | unboxed |
|---|---|---|---|
| 1702.06385 | 462 | 427 (all measured) | 34 Reference, 1 Table |
| 2210.01629v3 | 154 | 152 (all measured) | **2 Diagram** |
| 2510.15795 | 473 | 418 | **55 Diagram** |

Those Diagrams are the TikZ/table graphics `ingest_source_graphics` creates from
the author's source, so they arrive with no region at all — they appear in the
element tree and in reflow with no box on the page, which is `drill`'s own
"131 elements and 131 missing boxes" failure in miniature. **`pdfdrill geometry
--layout` does not reach them**: on 2510.15795 it moved the boxed objects from
418-all-measured to 254 measured + 84 interpolated + 80 yolo and left all 55
Diagrams unboxed. An equation can be joined to a reading by text similarity;
a picture has no text, so the join T-0045 has to make is geometric — against
the figure rects `cmd_images` lifts, or inkdrill's regions.

**The same `throwOnError: false` is still in the other four KaTeX generators** —
`docops/projectors/formula_report.py`, `comparison_html.py`,
`distill_reader.py` and `pdfdrill/reports/html.py`. T-0080 item 2 named the
inspector, so only the inspector was changed; the other four still show a
refused formula as KaTeX's own red error text and still cannot count one.
`docops.katex_notice` already exists because a warning retyped in five files
says five different things within a month, and this is the same shape one level
down: the marking belongs beside that constant.

### Found by the new count, measured, and deliberately NOT fixed

`pdfdrill drill 1702.06385.pdf` — the owner's own command, on the born-digital
path where `cmd_model` auto-merges the e-print — now puts the author's LaTeX on
170 of 170 maths objects, and the page's own KaTeX refuses exactly **one**:

    author's source   L(\data\mid\model)          valid TeX
    expanded          L(D\midM)                   \midM exists nowhere

A control word ends at a backslash, so `\mid\model` needs no space; `_apply_once`
substitutes `\model` -> `M` and the two fuse. The guard is one line before the
append in `latex_source._apply_once`:

    if expanded[:1].isalpha() and re.search(r"\\[A-Za-z]+\Z", "".join(out)):
        out.append(" ")

**Measured over the whole library, it changes 6 of 23,608 expansions and fixes
1 more refusal.** That is why it is not in this branch: `expand_macros` is the
function every consumer depends on, the two stated items do not include it, and
six strings do not justify the blast radius. The audit now NAMES this case on
the owner's own document, which was the point of counting. The owner's call.

### Where the author's LaTeX does and does not arrive

`cmd_model` auto-merges `injectlatex` only when `lines_source` is
`pdfminer-chars`/`pdfplumber-chars` and the document is arXiv. **With a MathPix
`lines.json` on disk the merge never fires**, so `pdfdrill drill` gives geometry
with no author LaTeX at all and `pdfdrill injectlatex` has to be run by hand —
which is how both gate papers behaved. Measured, same document, two routes:

| route | maths objects | with the author's latex | refused |
|---|---|---|---|
| `drill` (no lines.json, born-digital) | 170 | 170, in props | 1 (the fusion above) |
| `model` + `injectlatex` (lines.json present) | 178 | 18, on realizations | 0 |

The second number is the owner's goal unmet: 18 of 178. `injectlatex` reads
`extract_display_equations` and nothing else, and that source has 19 display
equations, so on the MathPix route the 160 inline Formulas could not get an
author reading from it at all — only `build_source_model` produced those, and
**nothing in `src/` called it** (its only callers were tests). The source is
not short of inline maths: the follow-up below measures **400 inline
occurrences, 185 distinct forms**, in the same file. Closed by the next
section.

**A prose comment in the page script can be load-bearing.**
`tests/test_docinspect_lang_js.py` slices the shipped language block between
`const LANGS = …` and the literal line `/* ---------- KaTeX helper ---------- */`
so that it runs the real code and not a copy. Extending that line into a block
comment's opener deleted the boundary and failed 11 tests with
`ValueError: substring not found` — nothing about KaTeX. The line is now marked
as a boundary in `docinspect.py` itself.

## The author's LaTeX on every route (owner, 2026-10-27: "Author LaTeX on every route")

The step the owner chose after T-0080 items 1-2: with a MathPix (or any other)
`lines.json` on disk, `drill` must still give the author's LaTeX for INLINE
formulas too. Two things were missing, not one.

**One: nothing read the author's inline maths.** `cmd_injectlatex` reads
`extract_display_equations`, so only an Equation could ever carry a
`provenance="tex"` reading. `latex_source.extract_inline_math(body)` is its
counterpart, and `commands.attach_author_inline(doc, body, macros)` gives each
`Formula` object the author's own reading of that formula.

**Two: the overlay was gated on the route.** `cmd_model`'s auto-merge ran only
for `lines_source in ("pdfminer-chars", "pdfplumber-chars")`, so on the richest
input pdfdrill has the author's LaTeX never arrived at all. The gate is now
`_arxiv_id_for(pdf, sc)` alone — except that `--no-source` suppresses it, like
every other author-source lane, because that flag exists to measure a READER
with the author's source out of the way. The PROSE merge (`cmd_merge`) stays
born-digital-only: the char layer is garbled by two-column interleaving and the
arXiv margin stamp, MathPix's prose is not, and replacing it would throw away
the reading that was paid for.

### Why an exact key and not the display loop's threshold

The display loop attaches at `latex_similarity >= 0.55`, which is right for an
equation. An inline formula is three characters, and at that length the best
match is routinely the wrong formula — measured on 1702.06385, the model's
`\mid` scores 0.75 against the author's `\min`, `X_{2}` scores 0.67 against
`Y_2`, `\mathcal{G} \leftarrow` scores 0.84 against
`\mathcal{M}_{X \rightarrow Y}`. What is attached is shown to a reader AS THE
AUTHOR'S LATEX, so a wrong match is not a partial result, it is a false one.
`scoring.author_match_key` is therefore an EXACT key: `normalize_latex` plus
four stated equivalences (`\ldots`==`\dots`; a font wrapper is not content, so
`\operatorname{X}`==`\textsc{X}`==`\textit{X}`; `x^{\prime}`==`x'`; and script
order commutes, so `T'_i`==`T_i^{\prime}`). `normalize_latex` itself is NOT
touched: it is what `compare` and `scoring` score with, and every agreement
number in this repo came from it.

The key is applied BEFORE `normalize_latex`, not after — its brace collapse
turns `\textit{type}(a)` into `\textittype(a)`, where no wrapper is left to
unwrap. The two passes do not commute and the wrong order is silent.

### Two independent choices, both measured

The harvest blanks only display maths and verbatim-like blocks — NOT
`_STRUCT_RE`, which is `build_source_model`'s prose splitter and also blanks
`algorithm`, `figure`, `table`, `itemize`… Those are not paragraphs, which is
why prose skips them, but the `$...$` inside them is the author's, and MathPix
reads every pseudocode line as a Formula. On 1702.06385's 160 Formula objects:

| blanking | key | given a reading |
|---|---|---|
| `_STRUCT_RE` | `normalize_latex` | 109 |
| display+verbatim only | `normalize_latex` | 123 |
| `_STRUCT_RE` | `author_match_key` | 113 |
| display+verbatim only | `author_match_key` | **132** |

Neither choice substitutes for the other: the widest key over the prose
splitter still reads 19 fewer formulas than the narrow blanking does.

### The gate, both routes, on the page's own KaTeX 0.16.9

`pdfdrill drill 1702.06385.pdf` twice in two clean directories, once with the
document's MathPix `lines.json` beside the PDF and once without, then the
shipped `inspect.html` driven through `tests/dom_shim.js` and real KaTeX 0.16.9
in node, reading the page's own `window.__katexRefused`:

| route | maths objects | with the author's latex | rendered forms | refused |
|---|---|---|---|---|
| no `lines.json` (born-digital) | 170 | **170** | 170 | 1 |
| MathPix `lines.json` present | 178 | **150** (was 18) | 264 | 5 |

The MathPix route's 150 are 18 display equations and **132 of 160 inline
formulas**; the sidecar records the split (`latex_attached` 18,
`latex_inline_attached` 132, `latex_inline_formulas` 160,
`latex_inline_unmatched` 28) and `model_caps` reads
`{geometry: True, math: True, source: mathpix, merged: latex}` — the first time
a MathPix model has said `merged: latex`.

**One consequence to know about.** `cmd_injectlatex` also runs
`ingest_source_graphics`, so a MathPix model now gains the author's TikZ and
table bodies as Diagram/Table objects — `latex_graphics: 1` on the gate
document, which `pdfdrill svg` can render and MathPix gave as a picture. That
is `injectlatex`'s documented behaviour when run by hand on a MathPix model;
what changed is that nobody has to remember to run it.

**The 5 refusals are the counting working, not a regression.** One is the
`\midM` fusion already recorded above, now visible on a Formula's author
reading as well. The other four are `\textsc`, which T-0080 deliberately did
not resolve ("formatting KaTeX cannot do, so translating them would be a
guess") — all four are the author's own algorithm block, e.g.
`T_i \leftarrow \textsc{TrivialTree}(a_i)`. They were invisible before because
the forms were not in the page at all. If `\textsc{X}` -> `\text{X}` is
acceptable (it loses small caps, which is why it was left out), it is a
one-line rule in `latex_only.RULES` and the owner's call.

### What it reaches corpus-wide, and what it does not

Measured with the SHIPPED functions over every library folder that has a
`lines.json`, the author's e-print and a model whose Formula objects carry no
`latex_original` (which is what makes it a MathPix-route model and not a
circular measurement):

    documents measured                391
      skipped: already an author model   120
      skipped: no Formula objects         17
      skipped: model too large to parse    1
      skipped: source unreadable           2
    MathPix Formula objects          69,667
    given the author's reading       38,681   55.5%
    per document                     median 61.1%, mean 56.1%, 0.0% .. 97.6%
                                     266 of 391 documents at or above 50%
    with the PROSE blanking rule     34,945   50.2%   (-3,736)

**Quote the median, not the total.** The one skipped model is 1511.08771's, at
**4.73 GB** — it alone holds about 70,600 Formula objects, as many as the other
390 documents together, and parsing it needs ~25 GB of dicts. An earlier pass
that did parse it reported 41.9% for the same code, because that one document
is half the denominator. Its size is a finding of its own and not this task's.

The 44.5% that get nothing are overwhelmingly one class: **MathPix's own
fragments and splits.** On 1702.06385 the 28 unmatched are `P(`, `)`, `\mid`,
`K(x)+`, `N C I`, `{ }_{\delta}` and a formula cut mid-line. Corpus-wide only
12 of 30,985 were forms the author wrote in DISPLAY maths, so pooling the
display equations into the inline key would buy nothing. **A fragment has no
author reading to find, and `unmatched` is the honest report: the pass counts
it rather than attaching the nearest thing.**

Every attached reading goes through `expand_math`, so T-0080's six rules hold
across the corpus: of the 38,681 attached, **0** still carry one of the
LaTeX-only commands (`latex_only.names_left` is empty on all of them).
---

## Every TikZ row in an evidence report said "(not rendered)" (2026-10-27)

Found by **gemma4-ba**, whose user asked why. Owner's yes relayed the same day:
"yes, ask pdfdrill to make the change", scoped to TikZ.

**Two defects, one gate.** `reports/tex.py::_rendered` has exactly one route to
a separate compile, `report_tex.needs_own_document`, and that predicate was
XY-pic only. A `tikzpicture` body is not legal display maths, so `display_safe`
returned "" for it and the row fell to `\emph{(not rendered)}`. The HTML half
refused for its own reason: it renders every row's LaTeX through KaTeX, which
has no TikZ at all. Meanwhile `props['svg']` — the drawing `pdfdrill svg` had
already compiled, with the document's own preamble — was read by
`docops.projectors.formula_report` and by nothing the evidence row could see.

Measured by gemma4-ba over the 54 `svg_ok` rows of their crop corpus:
`display_safe` true for **2**, `needs_own_document` true for **0**. The 2 are
`tikzcd` bodies, and those are the worse case, not the better one — a
commutative diagram handed to the maths parser inside a longtable cell is the
239-error shape `_ampersand_safe` exists to work around.

**The route already existed.** `region_standalone` was written for exactly this
content (its docstring counts tikzpicture 762 · tikzcd 658 corpus-wide) and
says why standalone beats the in-cell workaround: alone in its own document,
`&` means what its own environment says it means, and a failure costs one PNG
instead of the report. gemma4-ba verified it by calling it directly on three of
their rows — 3 of 3 PNGs, one checked by eye.

**What changed.** `_TIKZ_CONSTRUCT`, built from the module's existing
`_PICTURE_ENVS` rather than a second list, plus `\usetikzlibrary` (the spelling
the two accepted rows open with). `standalone_math` split into `standalone_png`
(the compile, cached) + `standalone_cell` (the `\includegraphics`), so both
halves of a report share one compile and the PDF cell can carry the reason;
`standalone_math` keeps its old contract for the align-only equation route.
`ImageRow` now carries `svg` and `svg_error`. The HTML Rendered cell shows the
SVG where there is one (vector, and already compiled), the same standalone PNG
otherwise, and `(not rendered)` plus both reasons when neither exists. The PDF
half can never show the SVG — xelatex does not `\includegraphics` one.

**A refusal is remembered.** A failing xelatex costs up to the 90 s timeout and
`region_standalone._clean` deletes its log, so the second half of a report used
to repeat every failure of the first with nothing to show. `standalone_png`
writes a `.err` memo beside where the PNG would be, keyed to a hash of the body
AND the preamble — `packages_extra` is an open item on the diagram props, and a
memo that outlived its input would make the retry a no-op reporting a stale
error.

**Not done, deliberately** — both recorded, neither chosen:

- the gate was NOT widened to everything `region_standalone.needs_math_wrapper`
  admits (tabular, minipage, axis, lstlisting, …). A test pins that boundary.
- `report_tex.region_render` — the in-cell TikZ route, with the corpus
  vocabulary measured in its comment and the `ampersand replacement=\&` remedy
  — is **called from nowhere in `src/`** and was NOT deleted. A test pins that
  it is still here, so removing it is a deliberate edit.
- a `Table` object's `svg` still has no row to show it: `TableRow` carries no
  `svg` field, and the crop corpus has 0 Table objects to measure it on.
- `commands.yaml` was NOT touched: no command and no flag changed, only what a
  cell shows.

## 256 rendering threads on 16 cores: the gs budget is now one decision (2026-10-27)

The owner, through gemma4-ba: "limit pdfdrill's gs workers so they don't
oversubscribe the cores". They had seen more than 16 gs at once.

**Two constants that were never multiplied.** `pdf_reading` carried
`RENDER_WORKERS = max(1, min(cpu_count, 16))` and, 67 lines away,
`RENDER_THREADS = max(8, min(cpu_count, 16))`. `rasterize` shards the pages
across the first and hands EVERY shard `-dNumRenderingThreads=` the second, so
one call asked for **16 x 16 = 256 rendering threads on 16 cores**. Each
constant is defensible alone, which is why this survived review: the defect
only exists in the product, and the product appears nowhere in the source.
Measured consequence, 2026-10-26: one `pdfdrill evidence` crop pass forked
**241 concurrent gs processes** and took the load average to **137**.

Two further faults in the same two lines:

- `os.cpu_count()` reports the MACHINE. A run pinned with `taskset -c 8-15`
  still started 16 workers of 16 threads, so the drillgroup core split (4-7 are
  GLYPHDRILL's) could not be enforced from outside pdfdrill.
- `max(8, ...)` made 8 threads a FLOOR, so a 2-core container asked for 8
  before any sharding at all.

**Now:** `render_cores()` counts `len(os.sched_getaffinity(0))`, and
`render_plan(pages)` returns both halves from one budget with
`workers * threads <= render_cores()`. The budget goes to workers first, because
this file's own measurement says sharding is the 6.3x lever and
`-dNumRenderingThreads` about 20% on text pages; when there are fewer pages than
cores the remainder goes to threads instead of being wasted, so a one-page
render is still one process with every core — the case the old constants got
right by accident. `PDFDRILL_GS_WORKERS` / `PDFDRILL_GS_THREADS` may only
LOWER the budget: a cap that can be raised is not a cap.

**Measured, `pdfdrill rasterize` on a 40-page arXiv paper, 400 dpi, each tree's
own installed console script, fresh shell, clean directory:**

| | gs procs | threads each | threads asked | wall | pngs |
|---|---|---|---|---|---|
| before, unpinned | 16 | 16 | **256** | 3.8 s | 40 |
| after, unpinned | 16 | 1 | **16** | 4.4 s | 40 |
| before, `taskset -c 0-3` | **16** | 16 | 256 | 9.4 s | 40 |
| after, `taskset -c 0-3` | **4** | 1 | **4** | 12.1 s | 40 |

**The wall-clock effect, measured properly the second time.** The table above
was taken while a 7-minute pytest suite was compiling on the same 16 cores, and
an earlier version of this section read "~16% unpinned, ~29% pinned" off it.
That was wrong -- it measured the machine. Retracted.

Measured again by INTERLEAVING the arms (before, after, before, after...), five
repeats each, same 40-page input, each tree's own installed console script.
Alternating cancels slow drift in background load, which is exactly what the
first attempt fell for; `min` is the least-contended run of each arm:

| | before | after | |
|---|---|---|---|
| unpinned, min | 3.82 s | 3.87 s | **+1.3%** |
| unpinned, median | 3.95 s | 3.97 s | +0.5% |
| `taskset -c 0-3`, min | 8.10 s | 7.56 s | **-6.7%** |
| `taskset -c 0-3`, median | 8.37 s | 7.87 s | -6.0% |

So **the cap is free unpinned and FASTER pinned.** Unpinned the two arms'
ranges overlap (before 3.82-4.21, after 3.87-4.14) and the difference is inside
the noise. Pinned it is a real gain, and the reason is the defect itself: 16
processes each asking 16 threads on 4 cores is thrashing, and 4 x 1 is
right-sized. The ~20% this file measures for threads on text pages did not
show up as a loss, because that measurement was one process alone with cores
to spare -- not 16 processes competing.

Independently checked by the drillgroup coordinator from a fresh clone with its
own installed venv under `env -i`: `pdfdrill rasterize` on a 54-page copy under
`taskset -c 8-11` gave exit=0, 54 PNGs, **4 gs processes each with
-dNumRenderingThreads=1** read from `/proc/<pid>/cmdline`, and 115 tests passing
(these plus T-0078's).

A middle setting (8 processes x 2 threads, the same budget of 16) remains
unmeasured. There is now no timing reason to look for one.

Not done, deliberately: the cross-process budget. Two pdfdrill runs at once
still get a full budget each, so the machine can still see 32 gs. A lock-file
slot pool was proposed and left out of this change because it is the only part
that can deadlock a batch and it needs its own failure mode for a holder that
dies (gemma4-ba agreed).

## The reader had no front door, and its output said nothing about itself (T-0045 step 2b, 2026-10-28)

`src/streamreader/` arrived in step 2a as 214 modules nothing calls. Two things
were missing before it could be a producer under ENGINEERING 2d ("pdf2mmd2,
glyphdrill and Gemma should produce lines.json formated output and not interfere
with docmodel data"):

**No installed entry point.** `pyproject.toml` declared one console script,
`pdfdrill`. Nothing a user could type produced the reader's lines.json. Now
`pdf2mmd2 = "streamreader_entry:main"`.

**No declared source.** The reader writes `{"pages": [...]}` and nothing else
(`runner.py`, `_write_json(lines_json, {"pages": pages}, …)`). It cleared
`inspect`'s geometry prerequisite anyway — through the `""` entry in
`commands._TYPED_GEOMETRY_SOURCES`, which that tuple's own docstring calls an
accident of "168 legacy files that forgot to declare a top-level source".
`streamreader_entry` runs the reader unchanged and then writes
`"source": "pdf2mmd2"` as the file's first key.

### The number, and the flag it needs

Measured through the installed entry point on 1702.06385 (9 pages, 170 maths
objects, every one carrying the author's LaTeX), each arm in a fresh directory,
then `pdfdrill model`:

| lines.json beside the PDF | lines | maths boxed | matched + interpolated |
|---|---|---|---|
| none — pdfdrill reads the PDF itself | — | 30 of 170 | 45 + 62 |
| `pdf2mmd2 <pdf>` (default warm-up, tsv) | 1029 | 31 of 170 | 56 + 59 |
| `pdf2mmd2 <pdf> --refine` (glyph route) | 955 | 40 of 170 | 65 + 68 |

**The stamp is worth +10 with `--refine` and +1 without.** The default warm-up
reads poppler's text layer, which is the same ink pdfdrill already reads for
itself; `--refine` patches the lines from the page's own glyphs (33471 glyphs,
0 unassigned, agreement_min 0.9106, 0.6 s for 9 pages). The entry point does
**not** inject `--refine`: a front door that quietly adds a flag the caller did
not type is the worse defect. Any pdfdrill layer that comes to run the reader
should pass it, and this table is the reason.

A correction: `docs/t-0080/ITEM3-JOIN-DESIGN.md` first quoted the 40 as the
reader's number without naming `--refine`, taken from a roll-up whose
`total_pages` key had been written by hand. The number survived re-measurement;
the condition had been left out. Both documents now carry the three arms.

### Why the stamp is not inside the reader

Every module under `src/streamreader/` is byte-identical to pdf2mmd2@5190249
apart from a 4-line stamp, and `tests/test_streamreader_provenance.py` holds it
there — including `test_stripping_the_stamp_reproduces_the_source_bytes`, which
passes against the checkout, so all 213 modules are verified, not just claimed.
pdfdrill-side behaviour therefore cannot live in the package. `streamreader_entry`
is a module **beside** it, and the boundary is now a test in both directions
(`tests/test_the_reader_boundary_holds_both_ways.py`): the reader imports nothing
from pdfdrill's side, and only the entry point may name the reader. Imports are
read from the AST, because `mathpix`, `linetypes` and `compare` are module names
that exist on both sides and a text search answers a different question.

### `drillcheck.py` is gone, and that is what turned the suite green

213 modules, not 214. It asked "does pdfdrill accept what pdf2mmd2 writes?" — a
question that stops existing once the reader IS pdfdrill's, and `INVENTORY.md`
had already decided "drop" for it in step 1. It was also the single failing test
on this branch: it defaulted twice into the owner's own checkout, which T-0078
forbids. Neither contract could give way — the file is byte-locked, and
T-0078's allowlist "may only shrink" — so the collision only existed on a file
that should never have been ported. `test_the_development_tools_that_were_dropped_are_gone`
now keeps it from returning with the next sync.

### What was NOT deleted, measured rather than assumed

The relayed step-2b scope said to delete `inkboxes`, `linescompare` and
`structure` "where production needs none of them". Measured:

| module | importers |
|---|---|
| `src/pdfreader/structure.py` | `docmodel_six.py` (6 sites), `project_mmd.py` |
| `src/pdfreader/inkboxes.py` | `docmodel_six.py:4057` |
| `src/pdfreader/linescompare.py` | **none, anywhere** |

`docmodel_six` and `project_mmd` are what `src/pdfdrill/commands.py` imports, so
`structure` and `inkboxes` are production dependencies and **stay**. They are
also pdfdrill's own 2026-09-30 absorption of pdf2mmd v1, not pdf2mmd2's code,
so 2d does not reach them at all. `linescompare` has no importer, but it is one
of the three comparators `INVENTORY.md` decided to **merge into one**; deleting
an input to a merge that has not happened loses the code the merge was supposed
to harvest, so it stays too, recorded here instead.

### Packaging: the editable install was hiding a hole

`[tool.setuptools.packages.find]`'s `include` list never named `streamreader*`,
so a built wheel would have shipped the new console script without the package
it calls. The editable install hid this — its path hook exposes the whole of
`src/`, so `import streamreader` worked. Added, with `py-modules` for the entry
module. `pdfreader`, `mathlayer`, `mathgold` and `passes` are **also** absent
from that list and were deliberately left alone: they predate this task, and
what a wheel should carry for them is a separate measurement.

### Where the reader's file lands (audited 2026-10-28)

The coordinator's clone audit of 2b raised it, and it is a cwd artifact rather
than a defect. `cli` defaults `--out` to `./<stem>/`; pdfdrill looks for
`<stem>.lines.json` beside the PDF. Measured both ways through the installed
script:

| cwd and command | file written | beside the PDF? |
|---|---|---|
| library root, `pdf2mmd2 1702.06385/1702.06385.pdf` | `1702.06385/1702.06385.lines.json` | **yes, no copy** |
| a loose PDF, `pdf2mmd2 1702.06385.pdf` | `1702.06385/1702.06385.lines.json` | no, one level down |

The library's layout IS `<name>/<name>.pdf` (the dropped `drillcheck.py`
documented exactly that), so the manual route over the library needs no copy.
The default is not changed, for the same reason `--refine` is not injected: the
caller's `--out` is the caller's. The fix is a pdfdrill layer that runs the
reader and names the path, not a cleverer default; until then a loose PDF takes
`--out .`.

Still open from the same audit: a lines.json with `source` REMOVED still builds
a model (exit 0), so 2d rule 5 is not enforced. That is the `""` entry in
`_TYPED_GEOMETRY_SOURCES` and it is pinned, deliberately, by
`test_an_undeclared_file_passes_only_through_the_loophole` — the behaviour is
recorded as a hole rather than left to be discovered. Closing it waits on the
owner's decision about the 168 legacy files (stamp them, or detect the producer
from content at read time).

## A reading is read because it is identified, not because it is silent (2d rule 5, 2026-10-28)

`_TYPED_GEOMETRY_SOURCES` began with `""`, so a lines.json that named no
producer passed the geometry gate for naming nothing. Its own docstring called
that an accident. The owner's decision (option 4a, relayed by
pdfdrill-pdf2mmd2-migration): **pdfdrill identifies those readings from their
content at read time and writes nothing into the library.** The alternative was
to stamp a `source` onto every one of them — editing the owner's corpus so a
test would pass.

### First, the size of the thing, because three numbers were in circulation

| source of the number | says |
|---|---|
| `_is_typed_geometry_lines`' docstring | 168 legacy files |
| `_TYPED_GEOMETRY_SOURCES`' docstring | 1,579 of 1,747 readings |
| **measured 2026-10-28, 1,811 readings** | **1,452 declare nothing** |

Closing `""` without a detector would have refused four readings in five.

### What the content says — all measured before any of it was coded

* **MathPix names a converted PDF with a UUID** (its `pdf_id`) and builds every
  `image_id` as `<pdf_id>-<page>`. **1,450 of the 1,452** undeclared readings
  carry that shape, and **no** reading that declares a source carries it.
  Nothing of ours generates a UUID — our writers use the document's stem.
* **An integer `page_width` is a pixel frame; a float is PDF points.** The split
  is total: 1,451 of 1,451 parseable undeclared readings are integers, every
  point-frame reader in the library writes a float (612.0, 595.28).
* **No size threshold**, deliberately: 11 undeclared readings have a page under
  1000 px, 9 of them long scanned books whose smallest page is 816 px, so a
  "big enough to be pixels" test would refuse real MathPix readings.

Two undeclared readings are outside the UUID rule: one 0-byte file
(`2308.06374/mmd-out/`, refused before this change too) and
`texbook-appendix-g-generating-boxes`, whose ids name the document — one of our
own readers, from before they declared anything.

### The result, measured over all 1,811 readings

| gate | old → new |
|---|---|
| typed geometry | **0 answers changed** — 1,438 admitted before and after, 373 refused before and after |
| is-MathPix | **1 answer changed** — `texbook-appendix-g-generating-boxes`, True → False |

So the loophole closes with **no reading lost**, and every admission is now a
positive identification instead of an absence.

### The one changed answer is a defect being fixed

`_is_mathpix_lines` read "has no `source` key" as the evidence of a PURCHASE.
That is true of 1,450 readings and false of our own earliest output, so pdfdrill
called a file it had generated itself a bought MathPix reading. A reading wrongly
believed to be paid is a reading nothing will regenerate, and four call sites
spend or protect money on this answer. The detector separates them: a UUID id is
MathPix (`mathpix`), document-stem ids are ours (`mathpix-shaped`, same geometry
contract by the `mathpix-` prefix, not a purchase).

### The probe was not cheap, whatever it said

`_lines_json_source`'s docstring said "without loading the whole file" while
doing `read_text()[:8192]` — the whole file, then discarded, on every call,
across 4.9 GB of readings up to 12 MB each. It now reads 8 KB from each END: the
head for the top-level keys and the first `image_id`, the tail because
`page_width` sits AFTER its page's lines and is megabytes in on a long document
(1,451 of 1,452 undeclared readings carry one in their last 8 KB).

### Acceptance: the refusal is visible and names the next step

Same command, same document (`1707.00189`, whose library reading declares
nothing), two copies of the reading:

    identified (UUID ids, pixel frame)
      $ pdfdrill steps inspect 1707.00189.pdf
      model → geometry → inspect
      ... already done: gemmaocr, glyphlines, mathpix          # no paid step

    unidentifiable (float page size, ids that are neither)
      $ pdfdrill steps inspect 1707.00189.pdf
      model → geometry → mathpix → inspect
      ... mathpix (paid — run `pdfdrill mathpix` yourself; or `pdfdrill
          gemmaocr`, which satisfies the same prerequisite)

The refusal is not silent, and it names both the paid command and the free one.

### Call sites deliberately left reading the DECLARED source only

`_lines_source` (declared, else detected) is used by the two gates and by the
recorded `lines_source` evidence. Four others still ask only what a file
declares, each for a reason: the `--force` staleness check asks what the file
CLAIMS about its lane (a detected value is never `pdfminer*`); `prefers_merged_route`
is already handed `_is_mathpix_lines` separately; and two message formatters
would change their wording without changing a decision. `_has_usable_math` was
the one that looked risky, and it is not: it asks the source string only through
`_is_keyless_textonly_source`, which is exact membership in `("tesseract",
"pdfminer-chars", "pdfplumber-chars")`. Neither `""` nor `"mathpix"` nor
`"mathpix-shaped"` is in that tuple, so the answer is identical whichever is
passed — checked rather than assumed, which is why that call site could be left
alone without a measurement hanging over it.

### Four tests the closure turned around, and the one that was a real question

The suite came back `4 failed, 6129 passed, 82 skipped` on the first run after
the change. Three were fixtures abridged past the point where the content is
identifiable, and one was a semantic question worth answering rather than
patching.

| test | why it failed | what changed |
|---|---|---|
| `test_model_reader_flag.py::test_a_forced_glyph_read_backs_up_a_mathpix_reading` | its fixture is two lines and no page at all; its own comment said MathPix is "identified by the ABSENCE of a `source` key" — the definition this change replaced | the fixture now carries what a real MathPix page carries: a UUID `image_id` and an integer page size |
| `test_model_selfheal.py::test_latex_model_with_mathpix_lines_is_stale_without_caps` | same, through `_source_model_trap` → `_is_typed_geometry_lines` | same, in `_MATHPIX` |
| `test_pagelines.py::test_it_stays_a_mathpix_shaped_reading` | asserted `_is_mathpix_lines` on pdf2mmd2's OWN assembled reading, from when one detector answered both questions | asserts what `inspect` actually requires (`_is_typed_geometry_lines`, `planner.detect`'s `lines:typed-geometry`), that the detector says `mathpix-shaped`, and that the money question says **no** |
| `test_pagelines.py::test_a_declared_reader_still_carries_typed_geometry` | asserted `_is_mathpix_lines` is False for a reading that declares `source: "mathpix"` | now True — see below |

`test_it_stays_a_mathpix_shaped_reading`'s docstring named the `lines:mathpix`
prerequisite, which no longer exists: 897 moved `inspect` onto
`lines:typed-geometry`. The test was still asserting the old wiring, so it was
the last place in the repo that required pdf2mmd2's own reading to be called a
purchase. Measured on `0902.0431` (209 real page files, 4.5 MB assembled): ids
`0902.0431-001`, page 2125×2750 integers → `mathpix-shaped`, typed geometry
True, is-MathPix False.

**The real question: what is a reading that DECLARES `source: "mathpix"`?** The
old code answered "not a purchase", because only MathPix leaves `source` out, so
any declaration at all was taken as proof of a free reading. Measured: **0 of the
library's 1,811 readings declare `mathpix`** (1,452 declare nothing, 174
`pdfminer-chars`, 171 `pdfminer-docmodel`, 8 `tesseract`, 3 `visionocr`, one each
`yolo-geometry`, `pdftotext`, `pdfminer`). So the case is about the rule, not
about a file on disk — and the old rule was one stamp away from losing the
protection entirely: anything that ever wrote `source: "mathpix"` onto a bought
reading would have turned the four money sites off, silently. It now answers
**yes**: a reading that says it was bought is protected. Over-protection costs a
`.mathpix.bak.json`; under-protection costs the reading.

### Environment: a worktree test run can silently test the MAIN checkout

`python3 -m pytest` from `.worktrees/<branch>/` imports `pdfdrill` from
**`/home/wkolbe/MX/PDFDRILL/src/`**, not from the worktree. The `~/.local`
editable install points at the primary tree, and `tests/` adds nothing to
`sys.path`, so the suite runs against another branch's source while every path in
the output names the worktree. It is not a skip and not an error — the tests
pass or fail against code that is not the code under test.

The four failures above "passed" that way before being looked at properly.
Checked, not assumed:

    $ cd .worktrees/t-0045-pdf2mmd2-into-pdfdrill
    $ python3 -c 'import pdfdrill; print(pdfdrill.__file__)'
    /home/wkolbe/MX/PDFDRILL/src/pdfdrill/__init__.py          # the MAIN tree

    $ /home/wkolbe/MX/venv-pd-t0045/bin/python3 -c 'import pdfdrill; print(pdfdrill.__file__)'
    …/.worktrees/t-0045-pdf2mmd2-into-pdfdrill/src/pdfdrill/__init__.py

So a worktree needs its own venv (`/home/wkolbe/MX/venv-pd-t0045`, full install,
349 packages, with its own `pdfdrill` and `pdf2mmd2` console scripts), and every
suite number and acceptance line from a worktree must come from it. One probe
settles it before trusting a run: print `pdfdrill.__file__`.

### Recorded, not fixed: the docmodel's `meta.source` still defaults to `mathpix`

`docmodel/main.py` sets `doc.meta["source"] = declared_source(lines_json) or
"mathpix"`, and that default is deliberately NOT the new content detector —
docmodel does not import pdfdrill, and 2d puts the docmodel on pdfdrill's side
of the boundary, not the reader's. The consequence: for an undeclared reading of
our own, the sidecar's `lines_source` evidence now says `mathpix-shaped` where
the model's `meta.source` says `mathpix`. Nothing downstream breaks — that field
selects a COORDINATE SYSTEM and both names mean page pixels — but anyone
comparing the two will find them disagreeing, so it is written down here rather
than discovered.

A sibling discriminator already existed and was left alone:
`mathpix_conformance.reference_for` separates MathPix's own reading from ours by
looking for `deferred_glyphs`, a field MathPix has no concept of. Same idea,
different evidence, narrower job (it picks a conformance reference, not a lane).

## The gate had a blind side: the planner refused and the consumer read anyway (2026-10-28)

The coordinator's audit of `6c8e3891` found it, and it reproduces: on a reading
whose producer cannot be named, `pdfdrill steps inspect` correctly names the
paid step — and `pdfdrill model <pdf> --no-source` exits 0 and builds the whole
model from it. Measured on the library's `1707.00189` reading with its page
frame turned to floats: 317 objects, and the report said **"1 equations carry a
MathPix CDN image"** — a CDN crop claimed from a reading whose regions are in
PDF points. The wrong-frame hazard the gate exists to prevent, arriving through
the gate's own blind side. `pdfdrill inspect` then rendered 308 elements from it.

So the rule is one rule in two places: the planner says the prerequisite is
unsatisfied, and `model` refuses to build. `cmd_model` now returns
`Report(refusal, EXIT_LANE_NOT_RUN)` — exit 3, the status the owner chose in
2026-10-21 for "a lane was reported and not run", for the same reason: the
command promises a model and there is none, and a caller should not have to
parse prose to find that out.

### The refusal names the file and the missing evidence, not a generic complaint

    $ pdfdrill model 1707.00189.pdf --no-source
    1707.00189.lines.json declares no producer and its content identifies none,
    so pdfdrill will not build a model from it: its page size is written as a
    float, which is PDF points — a page-pixel frame is written as an integer,
    and every consumer of this reading's regions expects pixels.
    … and the two shapes that WOULD identify it, then `glyphlines` (free),
      `gemmaocr` (metered), `mathpix` (paid, never run for you)
    exit=3

`_unidentified_lines_reason` returns the specific failing half — nothing
readable, no typed line in the first three pages, or a float page frame.

### Writing the refusal first would have refused 75 of the owner's PAID readings

This is the measurement that changed the design, and it is the reason to count
before coding. The refusal set is "readings whose `_lines_source` is ''", and
over the library that was **76** — not the 2 the earlier counts implied. Of
those 76, **75 carry MathPix's UUID `image_id` AND an integer pixel frame**:
they are genuine MathPix conversions. The detector was failing them on its
line-type half, which looks at the first three pages — and a book opens with a
cover, a title page and a colophon, all plain `text`. Among them: *A Primer of
Analytic Number Theory* (13 MB), *An Invitation to Applied Category Theory*
(15 MB), *Entropy and Diversity* (17 MB), `Geometric_topology` (18.8 MB),
`dmoi4` (22 MB), `BirgitRichter_book` (12 MB), `Baker12PhD` (4.9 MB).

The defect was mine, in the ORDER of the evidence: **who wrote a file and what
the file can do are two questions.** An id is provenance and is conclusive on
its own; the line types are a capability, and `_is_typed_geometry_lines` asks
them separately. `_detect_lines_source` now tests the ids FIRST and does not
require the line types to name a producer, so:

| | |
|---|---|
| typed geometry | unchanged — the line types are still required there |
| is-MathPix | unchanged — it still asks for the line types too |
| `_lines_source` | now names the producer of 75 more readings |
| `model` refuses | **1** reading, the 0-byte `2308.06374/mmd-out/` file |

Both gates were re-measured over all 1,811 readings against the `6c8e3891`
baseline to confirm the first two rows rather than argue them.

### Deliberately narrower than the geometry gate

A DECLARED keyless reader (`pdfminer-chars`, 174 readings; `tesseract`, 8) fails
the geometry gate because its regions are points, and it is still a legal input
to `model` — that is the merged route, where the author's LaTeX supplies the
mathematics. What `model` refuses is a reading that names nobody AND shows
nothing. Every reading it refuses is already refused by the geometry gate; the
converse does not hold, and that asymmetry is the point.

### Recorded, not fixed: 75 paid readings are still not PROTECTED as MathPix

`_is_mathpix_lines` is `_lines_source(...) == "mathpix"` **and**
`_has_mathpix_line_types(...)`, so those 75 books still answer False to the
money question — as they did before any of this. Dropping the line-type half
there would protect them (a displaced reading would be parked as
`<stem>.mathpix.bak.json` instead of overwritten, which only ever adds
protection), but it also feeds `prefers_merged_route`, so it would change the
ROUTE CHOICE on 75 real documents. That is a decision, not a cleanup, so it is
measured and left for the owner.

### Also recorded: the cheap probe does not make the gate cheap

`_lines_probe` reads 8 KB from each end, but `_has_mathpix_line_types` still
does `read_text()` + `json.loads` on the WHOLE file — up to 22 MB here, 4.9 GB
across the library. That is unchanged from before (both detectors always called
it), so it is not a regression, but the gate is only as cheap as its most
expensive half, and the id tests now short-circuit ahead of it for every
identified reading.

### Eight more tests the gate caught, which is the rule having teeth

`test_folder`, `test_tiddler_update` (six tests) and `test_codelisting_bibkey`
each build a model from a stand-in reading written

    {"pages": [{"page": 1, "image_id": "i",
                "lines": [{"type": "text", ...}]}]}

— no declared source, an `image_id` that is neither a UUID nor the document's
stem, and no typed line anywhere. They stand for "some reading exists", not for
a particular reader, and nothing in them was ever about provenance.

An undeclared text-only reading is not a real shape: over the library's 1,811
readings the only one is a 0-byte file, because every real text reader declares
itself (`pdfminer-chars` 174, `pdfminer-docmodel` 171, `tesseract` 8). So each
fixture now declares `pdfminer-docmodel`, with that measurement in a comment
beside it. The gate finding them is the rule working — a fixture that could not
exist on disk was standing in for one that can.

### An id says who wrote a file; only the file says what frame it is in

The coordinator's audit of `d2185ac3` found the regression the previous fix
introduced, with a plant no library file has: **stem-shaped ids on a float page
frame**. It was admitted as `mathpix-shaped` with typed geometry True — point
regions served as pixel geometry, which is the hazard this gate exists to stop.
Under the committed code the report said it in so many words:

    $ pdfdrill model 1707.00189.pdf --no-source        # ids 1707.00189-001,
                                                       # page 2125.5 x 2750.5
    Built unified model: 316 objects … 1 equations are located in OUR
    coordinate system (the reading's own page pixels, source='mathpix-shaped')
    exit=0

"the reading's own page pixels" about a float page size. Their diagnosis is
right: letting an id excuse the LINE-TYPE half is what saved the 75 books, but
letting it excuse the FRAME test is a different claim. A UUID is MathPix's and
MathPix always writes pixels; a stem-shaped id only says "one of ours", and ours
write BOTH frames — pdf2mmd2 pixels, `pdfminer-*` points.

**It generalises one step further than the audit tested.** A UUID id on a float
frame was admitted the same way, and as a PAID reading on top
(`_is_mathpix_lines` True). So the rule is not "the stem branch needs the frame"
but **the frame is never taken on trust, from any id**; what an id may excuse is
the line-type half, and only that. Measured, the uniform test costs nothing:
every reading the detector identifies across the library carries an integer page
size.

Six shapes, measured through the detector after the fix:

| reading | `_lines_source` | typed geometry | is-MathPix | `model` |
|---|---|---|---|---|
| stem id, integer frame (pdf2mmd2's own) | `mathpix-shaped` | yes | no | builds |
| stem id, **float** frame (the audit's plant) | `''` | no | no | **refused** |
| UUID, **float** frame (the second shape) | `''` | no | no | **refused** |
| UUID, integer frame (real MathPix) | `mathpix` | yes | yes | builds |
| UUID, integer frame, no typed line (a book's cover) | `mathpix` | no | no | builds |
| no id, float frame | `''` | no | no | **refused** |

The fifth row is the 75 books, still identified — the line-type exemption is
intact, and the geometry gate still declines them, which is the two questions
staying apart.

**Why the library counts cannot show this, and what does instead.** No library
file has stem ids with a float frame, so every count was identical before and
after — the audit's point exactly. What catches it is a plant, and the test now
carries both plants (`test_an_id_never_vouches_for_the_FRAME`, and the
parametrised command-line pair). The detector test was verified red against
`d2185ac3` by running it with that commit's `commands.py` on `PYTHONPATH`; the
command-line test cannot be made red that way, because it deliberately ignores
the parent's environment and runs the installed script — which is the property
that makes it worth having, so its red evidence is the run above instead.

## The fresh clone was innocent: a free command satisfied a paid prerequisite and was never named (2026-10-28)

The owner drilled the 15 YACCLAB papers (bib.txt refs [2], [4], [9], [13],
[17], [21]–[24], [26], [29], [31]–[33], [35]) plus `dorst2005conformal` with a
fresh clone and reported two symptoms: no LaTeX in the markdown, and wrong
geometry. Both are real. Neither was the clone.

### What the clone was accused of, and the measurement that cleared it

The build stamp in those models reads `19e097d1`, `dirty: true` — the
2026-10-21 commit *"the free lane was behind an extra, and the fresh install
never built the fork"*, so the install-side defect was already fixed there. And
the hypothesis was testable directly: the same command on this machine, with
the patched pdfminer and all 349 packages, produces the same file.

    $ pdfdrill drill 2016icpr.pdf            # this machine, every extra
    source 'pdfminer-chars'   frame 595.28 POINTS   types {'text': 274}
    # ser7's fresh clone: identical

`hasattr(LTChar, "glyphname")` is False here too — it is an INSTANCE attribute,
so that probe was never the discriminator it looks like. Checked, not assumed.

### What actually happened: two free readers, and `drill` takes the weaker one

`drill` → `cmd_model(pdf)` with no reader → step 2 of the acquisition chain,
`_write_born_digital_lines`, which writes `pdfminer-chars`: PDF POINTS, untyped.
The glyph reader is only reached by naming it. On the owner's own `2018jrtip.pdf`:

| free reader | source | frame | lines |
|---|---|---|---|
| `drill`'s default | `pdfminer-chars` | 595.28 × 841.89 points | 1240, all `text` + 1 `math` |
| `pdfdrill glyphlines` | `pdfminer-docmodel` | **2067 × 2923 pixels** | **1172 typed** — 11 math, 128 list_item, 12 code, 7 section_header, 2 title, 15 authors, 65 rotated_text |

So "the geometry is wrong" is the points frame, and `pdfminer-chars` is excluded
from `_TYPED_GEOMETRY_SOURCES` for exactly that reason. The free fix existed the
whole time.

### The defect, and it has a price

`lines:typed-geometry` is satisfiable by three commands:

    mathpix     done_when: lines:typed-geometry        PAID
    gemmaocr    done_when: lines:typed-geometry        metered
    glyphlines  done_when: file:{stem}.lines.json      FREE, offline

`planner.equivalent_commands` grouped satisfiers by **string equality** of
`done_when`, so the free command never joined the class, and every missing-
prerequisite message named only the two that cost money — for all 16 documents.
Fixed by letting a command declare `also_satisfies`, grouping on what commands
satisfy rather than on one spelling, and listing free alternatives first and
marked free:

    mathpix (paid — run `pdfdrill mathpix` yourself; or `pdfdrill glyphlines`
    (free, offline), `pdfdrill gemmaocr`, which satisfies the same prerequisite)

**Why `glyphlines`' own `done_when` was NOT changed to the condition.** Sampled
over 40 of the library's `pdfminer-docmodel` readings, 35 carry a typed-family
line in their first three pages and **5 do not**, so the stronger condition
would report `glyphlines` unfinished on about an eighth of documents after a
perfect run. A command declares what it ALSO satisfies instead.

### A test that protected the omission

`test_paid_lane_guards.py::test_commands_that_satisfy_the_same_condition_are_known_to_be_alternatives`
asserted `alts["mathpix"] == {"mathpix", "gemmaocr"}` — the MEMBERSHIP on the
day it was written — while its own first sentence states the requirement
("which command produces it is the operator's choice"). The membership was
wrong, and exact equality then held it wrong. Rewritten to assert the
requirement. This is the second recorded instance of the shape:
`test_pdfminer_fork_survives_pip.py` pinned 905o's mechanism and passed while a
fresh clone had no fork at all.

### What is still true about the markdown

`glyphlines` fixes the frame and the typing; it does NOT produce math LaTeX.
Across the 15 papers the markdown holds 661 KB of text, 40 `math` lines and 40
display blocks, and 6 of the 15 have no math at all — these are algorithm and
benchmark papers. LaTeX needs `visionocr` (keyless, delegated) or `mathpix`
(paid); the free author-LaTeX lane does not exist for them, as none is an arXiv
e-print.

### Recorded, not fixed: `--ensure` still cannot substitute the free command

`planner.ensure` runs the missing OFFLINE prerequisites and skips the paid ones;
it does not consult `equivalent_commands`, so it will not run `glyphlines` in
place of a refused `mathpix`. The message now names it and the operator runs it.
Making `--ensure` substitute means auto-running a reader that rewrites an
existing `lines.json`, which is a decision about the owner's data, not a
cleanup.
