# The multi-baseline row

A display row carrying several baselines at once — terms each with their own
scripts, stacked column vectors, a sum's limits above and below its operator —
which `_attach_scripts` (one baseline with scripts hung around it) cannot
describe. Rule 6's ten lines, with the measurements they rest on.

## 1. What two existing systems do, and how well they measure

**INFTY** (Suzuki, Tamari, Fukuda, Uchida, Kanahori, DocEng 2003) — an
integrated OCR system for mathematical documents. Structure analysis is a
separate pass over recognised symbols. Reported: a **perfect analysis rate of
89.6%**, rising to **97.9% on the subset of expressions free of symbol
misrecognition**, over about 500 pages of mathematical documents.

That gap is the useful number, not the 89.6. It says structure accuracy is
dominated by symbol errors — and we have none: our symbols come from the PDF's
own text layer with exact boxes and exact identities. So the regime we should
land in is the 97.9 one, and anything far below it is our structure pass, not
our characters.

**DRACULAE** (Zanibbi, Blostein & Cordy, *Recognizing Mathematical Expressions
Using Tree Transformation*, IEEE TPAMI 2002) — takes symbols with bounding
boxes and returns a **Baseline Structure Tree**: three passes, Layout, Syntax,
Semantics, evaluated on the UW-III database with two purpose-built baseline
structure metrics. A later comparison study reports **~80% expression recovery**
for the DRACULAE parser against 43.3% for an adjacency-matrix technique.

NOT VERIFIED: the 80% is from a secondary source. The TPAMI tables themselves
were not read, so that figure carries less weight than INFTY's.

## 2. The idea, and the mechanism by which it should reach that

Recursive baseline decomposition over the glyph boxes we already have, emitting
the relations **this repository already defines**: `Right, Sup, Sub, Above,
Below, Inside` (`src/mathgold/slt.py:25`). `_attach_scripts` is the one-level
case of exactly this algorithm — one dominant baseline, scripts hung around it.
The generalisation is three things it lacks:

1. partition a row into independent terms before assembling any of them;
2. recurse — each term extracts its own dominant baseline, and the remainder is
   classified relative to the nearest dominant symbol;
3. the **Above/Below** relation, which is what a stacked column vector and a
   sum's limits need and what nothing in the pass can currently express.

## 3. The cheapest experiment that could show it wrong — RUN FIRST

If the existing assembler already handles each term, mere partitioning would
suffice and no new relation is needed. That is the cheap version of this design,
and it is the one worth killing first, in minutes.

**Measured, lib:c57ac038ae5f p293, reader rows 27 and 28:**

    to_tex(whole row)                 -> REFUSED (both rows)
    to_tex(the alpha-0 term alone)    -> \alpha_{0} = \frac{1}{2} ,   CORRECT
    over both rows: 1 of 8 terms assembles alone

**So the cheap version is refuted.** Partitioning is NECESSARY — it is the whole
reason a term that assembles perfectly in isolation is lost inside its row — and
it is NOT SUFFICIENT. Of the seven terms that still refuse, six hold a column
vector (`\bigl[` 1 over -1/2 `\bigr]`), two genuinely stacked entries needing
Above/Below and array emission; the seventh is alpha-1, below.

A second measurement, same page: **alpha-1's value is lost outright** (`α1 = ,`
against MathPix's `\alpha_{1}=\frac{1}{2}`) because its fraction's numerator,
bar and denominator land on **three different reader rows** — `1` on row 29
(baseline 78.1), `2` on row 30 (64.1), the bar on rows 28 and 30 (y 73.5), and
`α1 =` on row 28 (71.2). The script fold in `_group_lines` refuses to fold them
because it only folds a row that is *clearly smaller* (`s_size < 0.85 *
o_size`), and **a display fraction's operands are full size** — 10.0 against the
row's 10.0. With the operands absent, `_rule_role` sees no glyph above or below
the bar and calls it an `overline`, which then merges to nothing.

Folding them in would turn "lost" into "flattened", which is what alpha-0
already shows (`α0 = 12`). Content present, structure still wrong. So alpha-1 is
not separable from this design; it is its smallest case.

## 4. The expected change on the board

- p293 (ours' worst row, 0.0864): **rule findings 11 -> <= 2.** 9 of the 11 are
  on these two rows, and they are fraction bars displaced by the flattening —
  one missing where the page draws it, three or four invented where we put ours.
  MathPix has 0 rule findings on this page.
- alpha-1's value present; no matrix flattened to a digit string.
- 1805.01788 p3: `\sum_{i=1}^{n}` instead of `$\sum^{n}$ i=1`, the six `barex`
  pieces as ONE delimiter, unpaired A 31 -> <= 10.
- Board-wide: zero characters lost, `not_compiled` 0, d68e gate exit 0.

## 5. What already exists and must not be rebuilt

- **`src/mathgold/slt.py`** — LaTeX -> Symbol Layout Tree in the Zanibbi/
  Blostein/Cordy formalism, with the LgEval `.lg` label-graph writer. The target
  representation and the relation vocabulary are already here.
- **`src/mathgold/floor.py`** — what the born-digital text layer alone recovers,
  "the number every recogniser has to beat".
- **`src/pdfreader/structure.py`** — `to_tex`, which the experiment above shows
  already assembles a term correctly once it is handed one term.

So this pass does not need a new representation or a new scorer. It needs a
partitioner, recursion, and Above/Below.

## 6. Two prior attempts this must not repeat

`_group_lines` records two folds that measured WORSE and were reverted
(695/696, and `_merge_stream_lines`): both folded script rows together by stream
containment, and both failed because `_attach_scripts` could not consume the
result — "The rows are right and the pass that consumes them is not."

That is the same trap in the other direction: changing the grouping before the
consumer can handle it. So the order here is fixed — **the consumer first**
(partition + recurse + Above/Below), and only then the fold that gives alpha-1
its operands. Rule 5: this idea has two failed attempts behind it already, and a
third failure means changing the idea, not the threshold.
