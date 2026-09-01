# The four HTML/PDF artefacts — what each one is for

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

## Which artefact answers which question

| question | artefact |
|---|---|
| Is this reading right? | `report.pdf` |
| Did MathPix see this region at all? | `<bibkey>.inspect.html` |
| What do the tables say, without a key? | `tables.html` |
| Show me the maths in a browser | `formula-report.html` |
| Show me the diagrams as vectors | `svg/` |

Two of them are rare (`tables.html` 31, `formula-report.html` 35) against
`report.pdf`'s 1,331. That asymmetry is not a defect — they answer
narrower questions — but it does mean a cross-reference from the universal
artefact to a rare one will usually dangle, which is exactly what 10,928
rows now do.
