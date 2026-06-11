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
