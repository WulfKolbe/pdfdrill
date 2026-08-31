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
423's subject.

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

## `report.html` — does not exist

**On disk: 0.** No command writes it.

`pdfdrill report` writes **`formula-report.html`** (35 on disk): a full
inline+display math report rendered with KaTeX, `--scale N` matching each
render to the CDN image height. Its audience is a reader who wants the
mathematics in a browser at reading size, not a QC auditor.

`cmd_artifacts`' own docstring says it lists "report.html", which is a name
nothing has produced. Left as found and recorded here; renaming it is a
change, and 422 is a description.

---

## Which artefact answers which question

| question | artefact |
|---|---|
| Is this reading right? | `report.pdf` |
| Did MathPix see this region at all? | `<bibkey>.inspect.html` |
| What do the tables say, without a key? | `tables.html` |
| Show me the maths in a browser | `formula-report.html` |
| Show me the diagrams as vectors | `svg/` |

Two of them are cheap and rare (`tables.html` 31, `formula-report.html` 35)
against `report.pdf`'s 1,331. That asymmetry is not a defect — they answer
narrower questions — but it does mean a cross-reference from the universal
artefact to a rare one will usually dangle, which is exactly what 10,928
rows now do.
