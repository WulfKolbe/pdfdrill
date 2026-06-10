# Span-aware table cells + HTML QA projection

Date: 2026-06-10 · Status: approved (user) · Test file: `~/Downloads/p2530-pereira.pdf`

## Problem

Tables are stored naively in both extraction routes, losing the layout
structure that carries meaning:

- **pdfplumber route** (`pdfdrill tables`): `extract_tables` returns a flat
  matrix; a header like `BiomedicalData` that covers 6 columns is stored in the
  leftmost cell with `""` placeholders in the covered slots (p2530-pereira p8).
  Row-group labels (`Classical`, `Ensemblers`) lose their downward span the
  same way.
- **MathPix route** (`TableProcessor`): lines.json cells carry `cell_row`,
  `cell_column`, `cell_row_span`, `cell_col_span` — ALL 3,574 cells in our
  corpus — and the processor keeps only `text`. Worse, `_CELL_TYPES` omits
  `table_spanning_cell`, so the 179 spanning cells (the structurally most
  important ones) are dropped entirely.
- **Projections** are flat pipes (`tables.md`) or images (SVG/CDN); no
  structured per-cell access, no QA view.

## Decisions (user-confirmed)

1. **No new object type.** The existing `Table` DocObject gains
   `props["cells"]` — a list of span-aware cell dicts — plus `n_rows`,
   `n_cols`, `columns`, `header_rows`. `TableRow`/`TableCell` children stay
   unchanged (anchor provenance).
2. **Both sources** populate the same shape in this cut: MathPix (read the
   coords; fix the `table_spanning_cell` drop) and pdfplumber (reconstruct
   spans from `find_tables()` cell rects — the test file has no lines.json).
3. **QA projection:** `pdfdrill tables` additionally writes `tables.html` —
   one real `<table>` per extracted table with `rowspan`/`colspan`.

## The cell shape

```python
{"row": 0, "col": 1, "row_span": 1, "col_span": 6,
 "text": "BiomedicalData", "region": {...}?}   # region optional, source coords
```

Covered slots are NOT stored — a cell exists once, at its anchor (top-left)
position, with the range it covers. This is HTML's table model, which is why
HTML is the natural QA projection.

## Components

### 1. `src/pdfdrill/table_structure.py` (new, pure — no I/O)

- `cells_from_mathpix(children)` — children = the TableProcessor's collected
  cell payloads; reads `cell_row`/`cell_column`/`cell_row_span`/`cell_col_span`
  (+ `region`, text) directly.
- `cells_from_plumber(table)` — from a pdfplumber `Table` (`find_tables()`):
  derive the row/col grid from the sorted unique cell-rect edges; a rect
  covering k grid columns ⇒ `col_span=k` (rows likewise); text from the
  table's own extraction (or page crop).
- `column_headers(cells, n_cols)` — one clean name per column:
  - header rows = row 0 through the first **all-leaf** row (every cell
    `col_span == 1`) following the span-bearing rows; no spans at all ⇒ row 0
    only.
  - per column: join the header-cell texts covering it, top→bottom, a
    rowspan'd cell once; whitespace-normalized (linefeeds/space runs → one
    space; `xxx-\nyyy` → `xxx-yyy` soft-break join).
  - returns `(columns: list[str], header_rows: int)`.
- `grid(cells, n_rows, n_cols)` — expand back to the naive matrix
  (compatibility; `tables.md` keeps working).
- `to_html(cells, n_rows, n_cols, caption="", columns=None)` — `<table>` with
  `rowspan`/`colspan`; header rows as `<th>` in `<thead>`, each carrying its
  flattened column name as `title`; covered slots skipped.
- `check(cells, n_rows, n_cols)` — validation: overlapping cells / out-of-grid
  spans → warning strings for the QA caption (never raises).

### 2. MathPix route — `src/docmodel/modules/table.py`

- `_CELL_TYPES` += `table_spanning_cell`.
- `_collect_children` keeps `cell_row`, `cell_column`, `cell_row_span`,
  `cell_col_span`, `region`.
- `create_object` stores `props["cells"]`, `n_rows`, `n_cols`, `columns`,
  `header_rows` via `table_structure` (import via a small local copy of the
  helpers if cross-package import is undesirable — decision: import from
  `pdfdrill.table_structure` is acceptable; docmodel already runs with `src/`
  as import root).

### 3. Keyless route — `src/pdfdrill/pdf_reading.py`

- `extract_tables` uses `page.find_tables()`; each entry keeps `rows` (compat)
  and gains `cells`, `columns`, `header_rows`.

### 4. QA output — `cmd_tables`

- additionally writes `tables.html` (one styled `<table>` per table; caption =
  page, `n_rows×n_cols`, spanning-cell count, `check()` warnings). `tables.md`
  and `tables.json` keep their shape (json entries gain the new keys).

## Tests (TDD)

`tests/test_table_structure.py`:
- span reconstruction from synthetic rect grids (merged 6-col header, merged
  row-label);
- `cells_from_mathpix` incl. a `table_spanning_cell`;
- `column_headers` on the 3-level header (flattening + linefeed
  normalization + rowspan-once);
- `to_html` emits `rowspan`/`colspan`, skips covered slots, `<th>` titles;
- `grid` round-trip; `check` catches an overlap.

`tests/test_pdf_reading.py` (extend): built `\multicolumn`/`\multirow` tabular
fixture → `extract_tables` yields a `col_span=2` cell; `tables.html` written.

Existing `tests/test_basic.py` guards the TableProcessor change.

## Verification on real files

- `pdfdrill tables p2530-pereira.pdf` → `tables.html` shows `BiomedicalData`
  with `colspan=6` and the `Classical` row-group as a rowspan; column names
  like `BiomedicalData Acronym P` queryable in `tables.json`.
- ocrtest (lines.json with tables incl. spanning cells) → rebuilt model's
  Table objects carry `props["cells"]`.

## Out of scope (later)

Tiddler/formula-report HTML rendering of tables; semantic-graph TABLE entity
enrichment from cells; header-ROLE inference beyond the leading-rows
heuristic; LaTeX `\multicolumn` parsing from MathPix `text_display`.
