# The six HTML/PDF artefacts — what each one is for

Written for 422, from what is on disk today rather than from what any of
them was meant to do. Four artefacts accumulated with no written contract
between them, and the tables section drifted into a different shape because
nothing said which artefact answers which question.

Counts are over `~/pdfdrill-library` on 2026-08-31.

---

## `report.pdf` — the QC surface

**Made by** `pdfdrill reporttex --compile` (via `pdfdrill inkreport`).
**On disk** 1,331 documents. The only one of the four that is nearly
universal.

One boxed row per object: identifier, page, MathPix confidence as a coloured
square, the escaped LaTeX source, the mathematics **rendered**, and the
MathPix **scan crop** at pixel-exact original size. With a residual measured
it also carries a coloured bullet and a class code (`C|+81`).

**Audience: someone auditing an OCR reading.** It is the only artefact that
puts two independent instruments — MathPix's confidence and inkdrill's
residual — in adjacent cells on the same row, which is the whole point (147).
It is also the artefact the published site serves.

It has FOUR sections and they do not share a shape:

| section | cols | header |
|---|---|---|
| Display equations | 6 | Identifier · Page · Conf. · LaTeX source · Rendered · Scan image |
| Inline formulas | 5 | Identifier · Page · Conf. · LaTeX source · Rendered |
| **Tables** | **4** | Identifier · Page · **Content (LaTeX source if any)** · Scan image |
| Image regions | 7 | Identifier · Page · Class · Source · Author source · Rendered · Scan |

The tables section is the odd one: no `Conf.`, no `Rendered`, and its third
column merges "LaTeX source" with an apology when there is none. That is
423's subject. (423 gave it the equations' six columns; 429 filled its
`Conf.` from the minimum over the table's cells.)

### Two profiles, and the only thing either one sets (469)

`report.pdf` is built twice for two audiences and the difference is one field.
`pdfdrill inkreport --profile <internal|published>`:

| profile | formula rule | the section holds |
|---|---|---|
| `internal` (default) | `unresolved` | the formula rows that did not render |
| `published` | `none` | nothing — the section is omitted |

**It sets the formula rule and nothing else.** Not the paper, not the legend,
not the crop column, not the confidence bounds. A profile that quietly set a
second thing would turn "which profile built this" from one field into a
question about behaviour; a test parses `cmd_inkreport` and fails if `rule`
is ever read anywhere but as the `formulas=` argument of its two builds.

**Both builds take the same rule.** Step 2 is the measure build and step 3
measures its pages; setting the rule on the reading build alone would produce
a measurement of pages that no longer exist.

**Omitting the section does not omit the count.** Under `none` the header
still reads *"4,061 inline formulas (section omitted; 1 did not render)"*, or
*"(section omitted; all rendered)"* when there is nothing owed. Dropping the
rows is a judgement about what deserves a page; dropping the fact would be a
claim of cleanliness the document has not earned.

`report.build.json` records `formula_rule`, so the shape of a report is a
field rather than something inferred by parsing its own `.tex` — which is what
456 had to do.

Why `published` omits rather than restricts: `report.pdf` puts two independent
instruments in adjacent cells — MathPix's confidence and inkdrill's residual —
on every equation, table and image-region row. A formula row carries neither.
It is the one part of the artefact that is not QC, and over the 22 published
documents it was 37,624 rows of it.

### The Tables Scan column comes from the PDF, not the CDN (461)

`download_crops` filters for `_EQ` or `_TAB` — the intent was always both —
and then skips any tiddler whose `canonical_uri` is not http. **MathPix
records no crop uri for a table.** Across the 21 published documents that is
8,718 of 8,718 EQ tiddlers fetched and **0 of 351 TAB tiddlers**, so 423's
six-column Tables section shipped with its Scan column empty in every row of
every document.

The region is on the tiddler — page, `top_left_x/y`, `width`, `height` — so
`render_crops` crops it out of a Ghostscript render of that page. 348 of 351
rows now carry a scan; the 3 that do not are TAB objects the model recorded
with **no region at all** (`page: "000"`, every coordinate `None`) in
1510.06699, penev_A and penev_B, which is a different defect and not this
one's to fix.

Three things it would be easy to get wrong, each guarded by a test:

- MathPix regions are in ITS page-image pixels. Coordinates are scaled by
  (raster width / that page's `page_width`), read **per page** — 11 of 305
  documents carry more than one `page_width`, and a page scaled by another
  page's width lands on the wrong part of the page and still looks plausible.
- A page with no recorded width is **skipped, not defaulted**.
- The crop is resized back to the region's MathPix pixel size. `crop_cell`
  sizes an image as `jpg_width x px2mm` and `px2mm` is mm per MathPix pixel,
  so a 400-dpi crop left at its own width would compute ~1.6x too wide, hit
  the column cap, and stop being pixel-exact without saying so.

Rendering runs in `cdncrops` (the layer that owns `report-crops/`) and again
in `reporttex`, where it costs one stat per row once the layer has run. Cost
for the whole published set: ~45 s for 351 rows, the largest single document
(kohlhase-omdoc, 103 rows) 20 s.

### The formulas section is a report of problems, not a catalogue (460)

`report.pdf` shows problems and their solutions. A list of every inline
formula the document contains is not that. Measured over the 22 published
documents: **37,624 formula rows, of which 7 do not render.** The section was
99.98% inventory.

`--formulas` chooses what it holds, and the default changed:

| rule | what the section holds |
|---|---|
| `unresolved` (default) | only rows whose Rendered cell would say *(not rendered)* — and the section, with its manifest record, is omitted when none do |
| `none` | nothing; the section is dropped outright |
| `all` | every first-occurrence formula — the behaviour before 460 |

A row qualifies as unresolved when it **has** LaTeX and `renderable` refuses
it. A row with no LaTeX is not unresolved, it is absent, and shows as a dash.

The caption states the rule (`Inline formulas that did not render (1 of
4,061)`) and so does the header line, because a one-row table would otherwise
read as a one-formula document. `build_report` returns `formulas` (shown),
`formulas_total` (held) and `formula_rule` for the same reason.

Omitting the section is safe for the measurement: `inkmeasure` joins on the
`Display equations` caption alone, and that table comes first, so its page
range does not move.

---

## `<bibkey>.inspect.html` — what MathPix saw on the page

**Made by** `pdfdrill inspect`. **On disk** 72 documents.
**Requires** model, geometry, mathpix.

Self-contained: page images inlined at 120 dpi (`--dpi` changes it), every
DocObject drawn as a hover/click box over the page, plus a DOM-like ELEMENTS
tree, an INSPECTOR pane (region, LaTeX, props, realizations, alignments) and
a reading-order REFLOW.

**Audience: someone asking "did MathPix see this region, and what did it call
it?"** It answers a question about the MODEL — coverage, geometry, object
kinds — not about reading quality. It is the only artefact showing the page
as a page.

`publishready` requires it, which is why `inkreport` builds it (413).

---

## `tables.html` — the keyless table extraction

**Made by** `pdfdrill tables`. **On disk** 31 documents, most of them empty
(the first sampled reads `Tables (0)`).

Plain HTML `<table>` elements from **pdfplumber**, written beside
`tables.json` and `tables.md`. **It contains no SVG and no LaTeX.** It is a
different extractor's output, not a rendering of anything in the model.

**Audience: someone who wants the paper's tables as DATA, without a MathPix
key.** That is a real and separate need, and this file serves it.

### The drift, measured

`report.tex`'s tables section writes, for a row with no LaTeX:

```
(no LaTeX source; 1493 × 434 px region — see tables.html)
```

    documents whose report points at tables.html   680
    rows doing so                                10,928
    of those documents, tables.html EXISTS           17
    ...does NOT exist                               663

**97.5% of those pointers lead to a file that is not there.** And where it
does exist it is pdfplumber's extraction of the page — a different route with
a different failure mode — not that row's table rendered. The report is
citing an artefact as if it were the same object's better view, and it is
neither the same object's view nor usually present.

The SVG the message implies lives elsewhere again: `pdfdrill svg` renders
TikZ and tables through `latex → dvisvgm` into `svg/`, which exists for 10
documents.

---

## `formula-report.html` — the mathematics, in a browser

**Made by** `pdfdrill report`. **On disk** 35 documents.
**Requires** model.

Three sections, from a real one (bh2, 1.9 MB, 5,218 rows):

| section | columns |
|---|---|
| Inline Math — MathExpression tiddlers (4,870) | Tiddler · LaTeX source · Rendered (KaTeX) |
| Display Equations (344) | Tiddler · LaTeX source · Rendered (KaTeX) · MathPix image |
| TikZ & Tables (1; 0 rendered to SVG) | — |

**Audience: someone reading the mathematics**, at reading size, in a
browser, without a LaTeX toolchain. `--scale N` matches each render to the
CDN image height so the two can be compared at a glance.

### How it differs from `report.pdf`, which is the distinction the tables section lost

They are both formula surfaces over the same objects, and they answer
different questions:

| | `formula-report.html` | `report.pdf` |
|---|---|---|
| renderer | **KaTeX**, in the browser | **xelatex**, compiled |
| confidence | not shown | coloured square, per row |
| residual | not shown | coloured bullet + class code |
| scan crop | on display equations only | every row, at pixel-exact size |
| on disk | 35 | 1,331 |
| question | *what does this say?* | *is this reading right?* |

The renderer is the substantive difference, not the file format. KaTeX and
xelatex fail on different inputs, so a row that renders in one and not the
other is evidence about the LaTeX rather than about either tool — which is
worth having, and is not what either artefact is built to report.

`report.pdf` is the only one carrying two independent instruments in
adjacent cells. `formula-report.html` carries neither, and should not: a
reading surface that showed a confidence square would invite the reader to
treat it as a QC surface at half the evidence.

**Note.** `report.html` — the bare name — is written by nothing and exists
nowhere. `cmd_artifacts` named it in its docstring; corrected in 427.

## `corrections.html` — every accepted correction, corpus-wide

**Made by** `pdfdrill corrections`. **On disk** one file, published at
`reports/corrections.html`. 33 rows over 6 documents today.

One row per ACCEPTED correction: MathPix's reading above, the accepted one
below, **both against the same scan** — it is one region, so the crop spans
both halves and the reader compares two readings of one picture rather than
two pictures (437). The basis is a COLUMN, not a filter: 438 found 32
corrections verified by ink and one verified against the author's e-print by
counting, and filtering to `verified_by: ink` would have dropped the
strongest correction in the corpus. Both ink numbers are shown, because a
correction accepted on a fall of 398→397 can only be judged if both are on
the page.

**Audience: someone asking what pdfdrill has corrected.** That is the whole
of the distinction from `report.pdf`, which under 509's rule is also a
corrections document — but PER DOCUMENT. The two answer different questions:

| question | artefact |
|---|---|
| how did this book do? | `report.pdf` |
| everything pdfdrill has corrected, across the corpus | `corrections.html` |

**It was a `tools/` script until 510, and that cost exactly what audit A4
says it costs.** Code in `tools/` is invisible to the planner, to `status`
and to `--ensure`, so nothing rebuilt this file and nothing published it: it
shipped to the site UNTRACKED and went stale within a week, still showing the
`\mathcal{J}` reading for `0707.4470_FO0175` that 502 withdrew. `reporttex`
was promoted out of `tools/` for the same reason and is the worked example.

---

## `compare.html` — the readings side by side

**Made by** `pdfdrill compare` (`docops.projectors.comparison_html`).
**On disk** 27 of 2,818 library folders; **6 of the 21 published**
(johnston, lyche, mielke, penev_A, penev_B, voloshin).

One row per display equation that carries a MathPix crop, with a baseline of
three columns — **LaTeX (mathpix) · KaTeX (mathpix) · MathPix image** — and
then, for every COMPETING reading the object carries, another LaTeX + KaTeX
pair with that candidate's score. The competing readings come from
realizations whose provenance is not MathPix's own: `tex` (the author's
e-print source, put there by `injectlatex`), `snip` (MathPix /v3/text),
`llm`.

**Audience: someone deciding which of two readings is right.** That is the
whole of it, and it is why the artefact only earns its place when a second
reading exists.

### 521 changed these numbers — read this first

521 injected the author's LaTeX into the six published documents that had a
real e-print and lacked one, and rebuilt `compare.html` for the seven that
now carry a second reading. **Twelve of the 21 published documents now have
`compare.html`, and eight of those twelve show a genuine second reading.**

| document | rows | `tex` candidates |
|---|---|---|
| `0902.0431` (withheld from the site) | 1,215 | 649 |
| `1510.06699` | 279 | 268 |
| `penev_A` | 232 | 111 |
| `penev_B` | 124 | 59 |
| `2501.06662` | 60 | 57 |
| `0707.4470` | 62 | 53 |
| `2106.07890` | 51 | 46 |
| `1605.05775` | 26 | 26 |
| `2010.14265` | 16 | 13 |

The four baseline-only files (johnston, lyche, mielke, voloshin) are
unchanged and are still duplicates of `formula-report.html`, for the reason
below: those books have no author source, only MathPix's own `tex.zip`.

Two corrections to what this section said when it was first written:
`1510.06699` already carried 268 `tex` realizations and simply had no
`compare.html` built, so the count was three and not two; and penev_A/B were
injected from `penev_diss.tex` supplied explicitly with `--tex`, the
author's dissertation, not from an arXiv e-print.

### Why not all 21, and why that is a real reason now

The subset is not principled today, and the honest statement of it is:

| documents | what compare.html shows there | count |
|---|---|---|
| penev_A, penev_B | a real comparison: MathPix against the author's `tex` | **2** |
| johnston, lyche, mielke, voloshin | the baseline three columns only | 4 |
| the other fifteen | nothing — never built | 15 |

Measured, not assumed: penev_A's model carries 111 realizations of
provenance `tex`; johnston's and voloshin's carry none (only `change` from
accepted corrections, and `bibliography`). So on four of the six the extra
columns are absent and the file degenerates to **LaTeX source, rendered
maths, and the crop — which is exactly what `formula-report.html` already
shows**. On those four it is a duplicate.

**All 21 have a `tex.zip`, and that is not the same as having a second
reading.** `<stem>.tex.zip` is MathPix's OWN reconstruction —
`cmd_injectlatex`'s docstring says it is "redundant with the mathpix
column", and the source order prefers a real e-print over it precisely for
that reason. Injecting it would fill the second column with the same
engine's output and manufacture a comparison that cannot disagree.

Only **7 of the 21** have an author source: the arXiv e-prints, plus
penev_A/B whose author `.tex` was supplied by hand. The other **12** have
nothing but MathPix's reconstruction, and that is why they get no
`compare.html` — a stated property of the corpus, not of which command
happened to be run.

So the artefact belongs to documents carrying a second reading. 521 made
that set as large as the corpus allows — nine documents, eight of them
published — by injecting every author source that exists. It cannot grow
further without author sources we do not have.

### How it differs from `report.pdf`'s Corrected pairs

Both put two readings against one scan, and they are not the same thing:

| | `compare.html` | `report.pdf` Corrected |
|---|---|---|
| the second reading is | a CANDIDATE, unjudged | the ACCEPTED correction |
| how many rows | every equation with a crop (3,332 for johnston) | only the corrected ones (8) |
| what the reader does | decides which is right | sees what was already decided, and the basis |
| carries a score | yes, per candidate | no — it carries the basis and the ink before/after |

`compare.html` is the artefact you read BEFORE a decision; the Corrected
section is the record AFTER one. A row leaves the first and enters the
second by being accepted, and 509's rule is why the second is short.

---

## Which artefact answers which question

| question | artefact |
|---|---|
| Is this reading right? | `report.pdf` |
| Did MathPix see this region at all? | `<bibkey>.inspect.html` |
| What do the tables say, without a key? | `tables.html` |
| Show me the maths in a browser | `formula-report.html` |
| Show me the diagrams as vectors | `svg/` |
| Which of these two readings is right? | `compare.html` |
| What has pdfdrill corrected, corpus-wide? | `corrections.html` |

Two of them are rare (`tables.html` 31, `formula-report.html` 35) against
`report.pdf`'s 1,331. That asymmetry is not a defect — they answer
narrower questions — but it does mean a cross-reference from the universal
artefact to a rare one will usually dangle, which is exactly what 10,928
rows now do.
