# Evidence and residuals — the report surface, redrawn

Date: 2026-09-06. Approved in chat, section by section, before writing.

## Why

The published `report.pdf` grew by accretion: an HTML report first, then a
LaTeX twin, then ink measurement bolted onto the equations, then a findings
shape that omits the sections the reader wanted for lookup. Two reports on
the live site still show a five-column "Inline formulas (first occurrence)"
table; the other twenty omit the section. The host-line picture of an inline
formula exists only in the B report, and B has three columns. Nothing in the
path forced a look at what the reader wanted.

The user's reasoning, which this spec follows:

1. **Evidence reports** hold EVERY LaTeX/image line of the document. Not
   reading matter — a lookup surface. One file per kind: equation, formula,
   table, image. HTML (lazy-loaded, KaTeX-limited) and PDF (the document's own
   preamble, the rendering that counts).
2. **Residuals** is the action list: only the open points, sorted so the
   worst is first. Ink measurement of the equations feeds it. It is what B
   was trying to become.
3. The publish gate must not demand a re-measurement when only the layout
   changed. There is no measurement of inline formulas today; that is a
   later task.

**Amended 2026-09-06 (user correction, during implementation).** The
reports read `docmodel.core.Document` directly, as every projector in this
repo does; `tiddlers.json` is not materialised in drilled documents and is
not an upstream stage. The TiddlyWiki projector is the NAMING AUTHORITY —
`math_titles` for EQ/FO, and the TAB/DIA/PIC numbering extracted from its
`_assign_titles` into a public `region_titles` — which the reports import,
never re-implement. Approach 3 is therefore built now; the row model is
source-independent and `from_document.py` is its only model-aware module.

## Package: `src/pdfdrill/reports/`

| module | responsibility | reads |
|---|---|---|
| `rows.py` | frozen dataclasses `EvidenceRow` (identifier, page, latex, trailing_punct, confidence, crop, notes) and per-kind `EquationRow` (+eqnum, ink), `FormulaRow` (+host_line: page, line_type, confidence, region), `TableRow` (+dims), `ImageRow` (+texzip crop) | nothing |
| `from_document.py` | builds the four row lists from the `Document` via `objects_of_type`, named by `tiddlywiki.math_titles`/`region_titles`; host lines via `inlinectx` from `doc.meta.source_path` | model, lines.json, report.ink.json |
| `crops.py` | `ensure_crops(rows, doc_dir, pdf)`: CDN download (equations), PDF region render (tables, images), host-line render (formulas); moved from `report_tex` and the B command; cached files reused | report-crops/ |
| `html.py` | `render(rows, kind, meta) -> str`, KaTeX client-side, relative image links, the existing caveat banner | — |
| `tex.py` | `render(rows, kind, meta, widths) -> str`, imports `report_tex` cell helpers (`esc_text`, `renderable`, `crop_cell`, `breakable_ident`, `preamble`) | — |
| `evidence.py` | `build(pdf, kind, fmt)`; full listing, unbounded, six columns | rows, crops |
| `residuals.py` | findings classes ported over rows, selection and ordering of open points; `--measure` runs the existing ink chain (measure build stays `report.pdf`; the evidence-equation measure build is deferred with inline-formula measurement) | rows, ink |
| `gate.py` | the timestamp gate and the row-subset check for `publishready` | ink, model stamp |

The six columns, in both renderers and every kind: Identifier, Page, Conf.,
LaTeX source, Rendered, Image. For a formula row the Page, Conf. and Image
are the HOST LINE's, and the file header says so in one sentence.

## Commands

    pdfdrill evidence <pdf> --kind equation|formula|table|image [--pdf] [--all-kinds]
    pdfdrill residuals <pdf> [--pdf] [--measure] [--conf 0.1]

Outputs beside the PDF: `evidence-<kind>.html|.pdf` (+ `.tex`, `.log`),
`residuals.html|.pdf`.

`evidence`: every object of the kind, unbounded. Equations sort by confidence
ascending; other kinds keep document order. No ink bullets, no legend, no
findings sections, no cell-rect marks.

`residuals`: sections Corrected, Unresolved, Flagged, Low confidence
(< `--conf`, default `CONF_THRESHOLD` 0.1), Doubted but correct. Within a
section, confidence ascending. Same six columns plus the ink bullet and code in
the Conf. cell, plus the legend. Page-bounded at 10 by default. A formula row
can reach Unresolved only.

`--measure`: runs the existing ink chain (measure build of `report.pdf` with
cell-rect marks, inkdrill compare, inkmeasure, inkconvert) and then selects
from the resulting `report.ink.json`, whose `measured_against` carries
`built_at`, the model's sha256 and mtime. Moving the measure build to
`evidence-equation.pdf` is deferred with inline-formula measurement. Without
`--measure` the existing ink is used as it stands. **Nothing re-measures the
21 documents in this task.**

### Aliases (thin, removal is a later task)

| old | now |
|---|---|
| `report` | `evidence --kind formula` and `--kind equation`, HTML; `formula-report.html` written as a copy of the formula file |
| `reporttex` | `evidence --all-kinds --pdf` |
| `breport` | `residuals --pdf` |
| `inkreport` | `residuals --measure --pdf` |

Each alias prints one line naming the command it ran. Old artefacts on disk
(`report.pdf`, `B.pdf`) are left in place.

### Manifest

`evidence` and `residuals` join `commands.yaml` with `requires:` naming what
they READ (`model`; `cdncrops` as a declared network layer; `mathpix`
declared, never auto-run; `residuals` also the ink) and `done_when:` the output
present and newer than the model. `tools/skillsync.py all .` regenerates
the help. Alias entries stay and gain an "alias of" note.

## The gate

`publishready` per document:

1. **artefacts** — the four evidence PDFs and `residuals.pdf` exist.
2. **glyphs** — zero dropped glyphs in each compile log.
3. **ink** — `report.ink.json` present, not quarantined.
4. **timestamp** — the measurement's recorded model mtime and sha256 match
   the model on disk: nothing it measured has been rebuilt since. Fails when
   the model is newer and names `residuals --measure` as the fix. The PDF
   checksum is recorded and never compared, so a layout change never
   invalidates a measurement.
5. **coverage** — every equation row shown in `residuals.pdf` carries an ink
   row by identifier, straddlers (633) excepted.

The residuals header prints "equations measured <built_at> against the model
of <model_mtime>".

`tools/publishcheck.py` compares the five files against the site.

## Tests

- `rows`: a formula row without a host line renders a dash; an equation row
  carries its ink code.
- `crops`: a formula crop is the host line's region.
- renderers: six columns in both, same rows in the same order.
- `residuals`: section membership and ordering on a fixture with one row per
  section; a host-line confidence never flags a formula.
- `gate`: passes on a matching model, fails when the model is newer, message
  names the fix.
- `test_every_pdf_writer_holds_the_lock` covers the two new handlers.

## Rollout on the 21

`evidence --all-kinds --pdf` and `residuals --pdf` for each; no measurement.
Compare row counts against today's `report.pdf` and B. `publishready`,
`publishcheck`, push. Scripts and counts under `~/pdfdrill-library/out/NNN/`
with `INSPECT.txt`.

## Next

Inline-formula measurement, and moving the ink chain's measure build from
`report.pdf` to `evidence-equation.pdf`, are separate tasks.
