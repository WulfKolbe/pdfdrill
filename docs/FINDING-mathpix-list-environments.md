# A list should be a container, the way a table already is

> **SUPERSEDED IN PART, 2026-10-05.** MathPix has shipped an **"Itemize
> lists"** option — *"Format lists as LaTeX itemize environments. Turn off to
> return them as flat lines with inline markers."* The proposal below was
> written from readings that predate it, or were taken with it off. What
> remains useful is the MEASUREMENT of the flat-line mode (which is still
> selectable, and is what our references contain) and the argument for why
> the container form is the right default. The proposal itself is answered.
>
> Also shipped: **"Enhanced Diagram Data"** — chemical data (SMILES/SVG/MOL)
> and embedded text in charts and figures. That bears directly on our Phase 3.

*Measured 2026-10-05 against MathPix `lines.json` readings held in
pdfdrill-library. One finding, one proposal, no new concept required.*

## What MathPix emits for a list today

On `sigma26-075` (26 pages, 1,068 lines, a SIGMA journal paper), MathPix emits
**55 `list_item` lines**. Of those:

| | |
|---|---|
| carry `\begin{itemize}` or `\begin{enumerate}` anywhere | **3** |
| carry `children_ids` | **40** |
| carry `parent_id` | **0** |

The environment is present, but as **fragments glued to individual items**,
split across different lines:

```
line A   text_display: "\n\begin{itemize}\n\item[(ii)] Clearly, \(\det I = XY/\sin^2\phi\), …"
line B   text_display: "\n\item[(iii)] This can be seen by comparing (2.8) and (8.1).\n\end{itemize}"
```

Take any one `list_item` in isolation and you get an unmatched
`\begin{itemize}`, an unmatched `\end{itemize}`, or neither. Reassembly
requires concatenating siblings in document order and hoping the opener and
closer are both present — on this document they are present on 3 lines of 55.

Meanwhile a `list_item` that *does* carry `children_ids` has an **empty**
`text` and `text_display`; its content lives in the children (`text`, `math`,
`equation_number`, …). The structure exists. The environment is not expressed
by it.

## MathPix already does this correctly — for tables

In the same file, same reading:

| type | `children_ids` | `text` |
|---|---|---|
| `table` | 27 | `\begin{tabular}[t]{\|l\|l\|l\|}\n\hline symmetry …` — complete |
| `list_item` | 40 | `''` |

A `table` line is a **container**: it points at its `simple_cell` /
`table_row` / `table_column` children *and* carries the whole environment as
one self-contained string. A consumer can take either representation and both
are correct on their own.

## The proposal

Emit a list the same way.

```
type          "list"                       (container, as `table` is)
children_ids  [ …the list_item ids… ]
text          "\begin{itemize}\n\item[(ii)] …\n\item[(iii)] …\n\end{itemize}"
text_display  the same, display-wrapped
```

and leave each `list_item` carrying only its own item, without environment
fragments.

**Why this costs little.** It introduces no concept that is not already in the
schema — `table` is the precedent, in the same output, for the same reason.
It is a detokenizer-level change: the information needed is already present
(the items are already grouped, since 40 of 55 carry `children_ids`), so it
is a question of where the environment is written, not of recognising
anything new.

**Why it matters.** A list is the one structure where LaTeX's own semantics
are *entirely* in the environment. `\item` outside `itemize` is an error, not
a degraded list. So an output that scatters `\begin{itemize}` across sibling
lines does not merely lose formatting — it produces LaTeX that will not
compile unless a consumer reassembles it correctly, and nothing in the output
says which lines must be concatenated to make it whole.

A secondary benefit: `enumerate` versus `itemize` versus `description` is
decided by the container, and today that decision is only recoverable from
whichever fragment happens to carry the opener.

## What we do on our side

`pdfdrill` marks such text with a `generated` property beside the MathPix
type, because LaTeX produced the labels from counters rather than the author
writing them:

```
generated  "list_label"      latex  "\item"
generated  "bib_entry"       latex  "\bibliography{}"
generated  "toc_entry"       latex  "\tableofcontents"
```

The `latex` field carries the **generating command**, not the expansion — a
table of contents round-trips as `\tableofcontents`, never as the expanded
entries, because re-typesetting rebuilds them from the counters with the new
layout's page numbers.

The container proposal above is the missing half of that: the counter is the
item's, and the *environment* is the list's.
