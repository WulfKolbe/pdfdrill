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
exactly the 22 new tests, so no existing test described the old rule. A page
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
