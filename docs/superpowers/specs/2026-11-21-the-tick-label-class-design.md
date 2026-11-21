# The tick-label class: depth before code (group rule 6)

T-0161, 2026-11-21. Asked for by the coordinator after I stopped short of a
threshold on 0864 p4's missing y-axis ticks. Ten lines, measured as a
population across the board-14 set, the way the fraction-bar class was
measured in `d98fa365`.

The code this is about: the script fold in
`pdfreader.docmodel_six._group_lines`.

---

## 1. The defect, measured

0864 p4, page 2 of the board extract. Of the PDF's **226 seven-point glyphs,
192 reach our lines and 34 are lost outright** — `5`×14, `0`×8, `.`×5, `1`×5,
`2`×2, which are the characters of `0.05`, `0.15`, `0.25`, `0.5`, `0.75`. The
survivors are shredded into one-to-three-glyph lines:

    p2l22  formula  '0.0'      p2l24  formula  '−0'
    p2l21  formula  '0.'       p2l20  text     '0'
    p2l18  formula  '0.1'      p2l15  text     '0'
    p2l16  formula  '0.'

## 2. The population, across all 24 board pages

Ground truth taken from pdfminer independently of our reader: glyph runs
sharing a baseline, split on a gap wider than 0.3 em. A run enters the fold's
field of view when it has **≤ 6 glyphs** (`len(r) > 6: continue`) and its size
is **under 0.85** of the page's dominant size (`s_size >= 0.85 * o_size:
continue`). 2,495 runs qualify.

Each was then classified by evidence the fold does not use: is there a glyph of
the page's dominant size **within one em horizontally and within 0.75 em of the
run's own baseline**?

| | runs | survive intact in one line |
|---|---|---|
| a larger glyph beside it — a **script** | 1,900 | **1,898 (100%)** |
| no larger glyph beside it — **standalone** | 595 | 513 (86%) |

**The fold is right about every script and wrong about 82 standalone runs**, on
5 of the 24 documents:

    lib:5a5c76391c9c p4   39      BH1-9add65ca p113   4
    2312.11532 p7         23      BH3 p91             2
    0864 p4               14

and they are chart furniture, nothing else: `k=1`, `k=3`, `k=5` (legend
labels, 6 each), `0.05`, `0.15`, `0.75`, `1.0`, `−0.05` (tick labels).

## 3. Why it happens

The fold's own guard already asks whether the host is near:

    if rx1 < ox0 - o_size or rx0 > ux1 + o_size:
        continue                  # nowhere near it horizontally

but `ox0`/`ox1` are the **host row's whole extent**. A prose row spans the text
column, so a tick label at x=79 is "near" a sentence running from x=54 to
x=550. The census above asks the same question of the host's **glyphs**, and
that is the entire difference between 1,900 right answers and 82 wrong ones.

## 4. What the two best existing systems do — measured, not assumed

MathPix and Gemma4 on the two pages, from the board's own reference files:

| | 2312 p7 decimals | 0864 p4 decimals | `k=` labels |
|---|---|---|---|
| MathPix | 57 | 14 | 0 |
| Gemma4 | 57 | 14 | 0 |

Byte-identical, and in both cases the decimals are **table values only** —
`0.309`, `0.231`, … on 2312; `0.5`, `0.66`, `5.1`, … on 0864. **Neither reads a
chart tick label or a legend label at all.**

So this is not catching up with anybody. Our reader has these labels for free,
because they are real text in the PDF's own layer, and both comparands discard
them. That matters for what the gain can honestly be claimed to be (§6).

## 5. The idea, and the mechanism

**A run is a script only if the thing it is a script of is beside it.**
Replace the host row's extent with the host row's glyphs in the nearness test:
require a glyph of the host row within one em horizontally of the run, as the
census does. Nothing else about the fold changes.

Mechanism: a script is set immediately beside its base, by definition — that is
what makes it a script rather than a line. A tick label has the plot's white
space beside it and its nearest ink is a rule or a data mark, not a glyph. The
distinction is the one the fold is already trying to make; it is measured
against the wrong object.

## 6. The expected change on the board

**Not from reading the labels.** §4 shows neither comparand reads them, so a
CER reference that omits them gains nothing when we add them — and 0864 p4 has
just shown (seventeenth board state) that a reading can be *more* right and
score worse when the judge and the reference disagree about what belongs on the
page.

The gain is that **a prose line stops carrying a foreign digit**. 102 of 644
mixed-size lines of 8+ glyphs on the board set carry a small glyph with no
larger glyph of their own beside it — e.g. `p2l60` on 0864 p4, which reads
`equal^F0,16ofthemhave(cid:11)=1,...` with one 7pt tick digit among 49 10pt
glyphs. That count is an **upper bound**: the probe behind it tests x-adjacency
only, without the baseline half of the test, so it will over-count real
subscripts. I quote it as a bound, not a prediction.

Expected: a residual improvement on the 5 documents in §2, concentrated on
2312 p7 and 0864 p4 (the two worst `ours` rows). **Honest magnitude: unknown
until measured, and possibly zero on the judge** for the same reason 0864 p4
did not move when `standard` and `tie-breaker` were repaired.

## 7. The cheapest experiment that could show the idea is wrong — run FIRST

Already run, and it is §2's table. If scripts had depended on the row-extent
test, tightening it to the host's glyphs would break them — and 1,898 of 1,900
script candidates have a dominant-size glyph within one em of their own
baseline, so the tightened test keeps every one. Had that figure come back at,
say, 1,400, the idea would have been dead before any code was written.

The second cheapest, not yet run and the first thing to do: apply the tightened
test, rerun `pdfdrill glyphlines` over the 24 extracts, and diff word by word.
The 1,900 script rows must be untouched; only the 82 may move.

## 8. What this does NOT fix, and should not be expected to

- The **34 glyphs lost outright** on 0864 p4. They disappear somewhere other
  than the fold, and this change will not bring them back. Separate task.
- The **rotated** grouping: small-cap axis titles splitting into `rndOO` +
  `PUSPUS` + `monspc`, three rotated lines 20× too tall merging x-axis labels,
  and `datasetIDsdatasetIDs` (two charts' titles in one line). Different pass.
- `(cid:11)` / `(cid:0)` in two 0864 p4 captions — unmapped glyphs, not layout.

## 9. Risk, and the ratchet

`_group_lines` carries five documented attempts that measured worse, including
two in this same fold (695/696 on stream containment, and the listing-label
case that produced `(a)45 /V/arTiil0i,ngj0a,ndi1p,arja1l;lelization.`). Any
change here is pinned in the same commit by `tests/test_the_board_counts_only_improve.py`
and by a word-by-word diff of all 24 extracts, both directions.

## 10. Decision

Worth doing, on §2's evidence: one test changed, 1,900 right answers kept,
82 wrong ones addressed, no threshold introduced — the census uses the em the
page already states. **Not started in this session**, deliberately: rule 6 asks
for these ten lines first and the coordinator asked for them explicitly.
