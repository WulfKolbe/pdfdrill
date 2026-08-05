# L5 — Typed document-object level

Status: **implemented** · Tower: [README](README.md) · Semantics: [TOWER](TOWER.md)

The unified document model (`src/docmodel/`).

## Structure

```
Document{streams, objects, alignments, meta}
DocObject{type, id, props, realizations, children, parent}     # the tree
Realization{stream, range, region}    # one-to-many, ORDERED, not necessarily
                                      # contiguous binding to lower material
Alignment{kind, left, right, props}   # between stream ranges:
                                      # render | dehyphenate | geometry | …
```

`Realization` is already the TOWER's **support relation** for L5→L3/L4: an
object whose support has more than one fragment IS a split element (see
[TOWER](TOWER.md)).

### The ~16 concrete object types (`docmodel/modules/`)

Document, Page, Section, Abstract, Toc, Paragraph, ListItem (+ nested List via
`blocks.nest_list_items`), Table, TableRow/TableCell, Equation, Formula,
Picture, Diagram, Sidenote, Footnote, Citation — plus Reference (bibliography)
and EmbeddedImage.

### Mutators (operate here, in place)

| Mutator | Effect |
|---|---|
| `docops/mutators/dehyphenate.py` | the FIRST, dictionary-driven split repair (L5-level energy: dictionary membership) |
| `docops/mutators/promote_cleaned.py` | promote per-line cleaned text |
| `docops/mutators/stanza_nlp.py` (+ `docops/nlp_stanza.py`) | attach `props.nlp` (tokens/POS/lemma/deps/entities) to prose objects |

## Architecture invariants

- **Anchors are opaque identities, not positions** — inserts/deletes in one
  stream don't invalidate references elsewhere.
- **Source streams are immutable** — modules ADD objects/realizations/
  alignments; the raw MathPix payload stays recoverable verbatim.
- **Objects are stream-independent** — a MathExpression exists once with
  semantic props; realizations live in whichever streams it surfaces in.

## The serialized model — what `model.docmodel.json` actually contains

The dataclasses above are the concept; this is the file. Measured across 60
library models (30,102 objects), so the field lists are what is really there,
not what a reader might expect.

```
{ "meta": {...}, "streams": {...}, "objects": [...], "alignments": [...] }
```

**`objects` is a LIST, not a dict** — `.get("objects")` returns an array and
`objs.values()` fails on it. Every record has exactly these six keys:

```json
{ "id": "obj_d93357848b3b",
  "type": "Section",
  "props": { "level": 2, "caption": "Introduction", "flow_index": 3,
             "bibkey": "2209.00445v3", "section_number": "1" },
  "realizations": [],
  "children": ["obj_33bd0f19185c", "obj_286838354141"],
  "parent": "2209.00445v3" }
```

- **`children` / `parent` are ID STRINGS**, not nested objects — the tree is flat
  on disk and re-linked on load. `children` is an ATTRIBUTE of `DocObject`
  (`section.children`), *not* `props["children"]`; checking the wrong one reports
  an empty tree on a healthy model.
- **`realizations` is often empty.** A LaTeX-source model has no lower stream to
  bind to, so absence of realizations does not mean the object is unsupported.
- **`meta`** carries `bibkey`, `title`, `authors`, `root_id`, `source_path`, and
  route-specific extras (`latex_preamble`, `latex_source_dir`, `environments`,
  `source_counts`).
- **`streams`** maps a name to `{name, anchors, payload}`. Which streams exist
  depends on the build route: `mathpix_lines` on the MathPix route,
  `source_cites` on the LaTeX-source route, `dehyphenated_para_NNNN` per
  paragraph after the de-hyphenation mutator.

### `props` by type — a convention, not a schema

Nothing validates these; each processor writes what it knows. The common ones,
in frequency order over the sample:

| type | props seen |
|---|---|
| `Paragraph` | `text`, `bibkey`, `flow_index`, `parent_section`, `page`, `paragraph_index`, `from_line_index`, `to_line_index` |
| `Equation` | `latex`, `refnum`, `latex_raw`, `page`, `image_id`, `bibkey`, `flow_index`, `parent_section` |
| `Formula` | `latex`, `latex_original`, `display`, `page`, `bibkey`, `flow_index`, `parent_section` |
| `Page` | `page_number`, `page_width`, `page_height`, `image_id`, `languages_detected`, `is_blank` |
| `ListItem` | `marker`, `content`, `page`, `line_index`, `list_index` |
| `Citation` | `citekey`, `page`, `style`, `added_by` |
| `Section` | `level`, `caption`, `section_number`, `page`, `region`, `next_sibling` |
| `Table` | `cells`, `n_rows`, `n_cols`, `columns`, `header_rows`, `latex_code`, `raw_text` |
| `Reference` | `citekey`, `year`, `author`, `entry_type`, `bibtex`, `ref_source` |

Three that recur across types and are worth knowing:

- **`region`** — `{top_left_x, top_left_y, width, height}` in MathPix points,
  TOP-LEFT origin, y down. Present only where a route supplied geometry; the
  LaTeX-source route has none until `pdfdrill geometry` attaches it. `inspect`
  draws its boxes from this, so no `region` means no boxes.
- **`flow_index`** — document reading order, the key every projector sorts by.
- **`added_by`** — which pass created the object (`latex`, `bibliography`,
  `merge_page_geometry`), so a `--force` re-run can drop just that pass's output.

### Reading one

```python
from pdfdrill import model_io
doc = model_io.load_model(path)          # full Document (slow, mutable)
g   = model_io.load_docgraph(path)       # lazy indexed VIEW (~10x faster, read-only)
```

Use `load_docgraph` for read-only work; both expose `.type` / `.id` / `.props`,
so pure helpers written against one work on the other.

## Inter-layer notes

- α in: line grouping (L3→L4→L5 paragraph/list/table processors), block
  detectors, algorithm/pseudocode grouping, bibliography segmentation.
- γ out: `Realization` rows (axis=stream) + `region` (axis=pdf).
- α up: the math assembler and per-object structure builders produce L6
  content *inside* these objects; `ingest_docmodel` lifts them to L7.

## Open work

- Tiddler-canonical storage (stage 2+): make the tiddler array the editable
  store, rebuild the docmodel transiently for graph ops.
- Promote hyperlink annotations into first-class Link DocObjects (L0→L5).
