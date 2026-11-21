# The diagram filter class: depth before code (group rule 6)

T-0154/T-0156, 2026-11-21. The queued "30 lost glyphs on 0864 p4" item. The
mechanism is now proven, the class is **twenty times larger than the item
said**, and the cheapest experiment is **encouraging but not sufficient** —
so there is no code here.

The code this is about: `_diagram_regions` and the `_in_diagram` filter in
`pdfreader.docmodel_six.build`.

---

## 1. The mechanism, proven to the glyph

`build` detects figure regions and then removes every glyph whose centre lies
inside one:

    upright_glyphs = [g for g in upright_glyphs if not _in_diagram(g)]

On 0864 p4 page 2 that is **34 glyphs, all 7pt**, and their characters match
the judge's lost set exactly:

    inside a diagram region   5 x14, 0 x8, 1 x5, . x5, 2 x2   = 34
    the judge's side A loss    5 x14, 0 x8, 1 x5, . x5, 2 x2   = 34

Five regions are detected on that page. The glyphs are the y-axis tick
labels of its three charts — `0.05`, `0.15`, `0.25`, `0.5`, `0.75`.

Localised before being named: of 226 seven-point glyphs constructed on that
page, only **192 ever reach `_group_lines`**, so the loss is before grouping,
and the filter above is the only thing between.

## 2. The class is 680 glyphs, not 30

Census over the 24 board-14 extracts, counting glyphs WITH TEXT that the
filter removes:

    2312.11532 p7            364
    lib:5a5c76391c9c p4      264
    0864 p4                   38
    lib:c57ac038ae5f p293     14
    ---------------------------------
    TOTAL                    680   on 4 of 24 pages

688 glyphs fall inside a region in all; 680 of them carry text. So the
queued item was one page's worth of a filter that deletes 680 glyphs of text
across the set.

## 3. The filter is deliberate, and right about most of it

Its own comment: a figure's internals are not prose, "the rectangle is
projected as a crop instead". That is correct for a scatter plot's point
labels and for the ink of a drawing. It is wrong for a chart's **axis labels
and legend**, which are text a reading should carry.

Of the 688, **235 sit within 3 em of a region's left or bottom edge** and 453
are in the middle. The edge is where an axis lives.

## 4. What the best existing system does — measured

| page | MathPix alnum chars | ours |
|---|---|---|
| 2312.11532 p7 | 12,618 | 9,625 |
| lib:5a5c76391c9c p4 | 7,666 | 6,270 |
| 0864 p4 | 14,279 | 12,536 |

MathPix carries more text on every page where this filter fires. On 0864 p4
page 2 its reading holds 29 decimals against our 19 before the experiment
below — the 10 missing ones are the tick labels.

## 5. The idea

Shrink each detected region by an edge band before the filter runs, so a
glyph at the left or bottom edge is no longer "inside" the figure. The
figure's ink stays out; its axis stays in.

## 6. The cheapest experiment, RUN FIRST — encouraging, not sufficient

A 3-em band, as a probe:

    page              decimals        alnum chars      lines
    0864 p4           25 -> 35        12536 -> 12567   423 -> 432
    2312.11532 p7     48 -> 53         9625 ->  9732   236 -> 244

On 0864 p4 that is exactly the ten tick labels returning, and nothing else.

On 2312 p7 it adds 9 lines, and **4 of them are wrong**:

    GOOD  '0.15'   '0.1'   '0.75'                     axis ticks
    GOOD  'LDA PLDA ETM BerTopic TVQ-VAE'             a legend
    BAD   '(d) NYT-NPMI. LDA PLDA ETM BerTopic TVQ-VAE(e) NYT-Diversity. …'
    BAD   '0.05 k=3 k=3 0.05 k=3'
    BAD   'k=1 k=1 k=1'
    BAD   '100 100'  and  '(b 100'

The content is right and the LINE STRUCTURE is not: three charts stand side
by side, so the row grouper merges their labels across the page, exactly as
it merges two charts' axis titles into `datasetIDsdatasetIDs` (T-0161 §8).

**So the idea is not refuted and not ready.** Admitting the glyphs is half of
it; the other half is grouping them PER REGION rather than per page row,
which is a second change and a larger one.

## 7. The expected change on the board

0864 p4: 34 glyphs stop being unpaired on side A. By the same arithmetic as
the accent class — each unpaired glyph counts once — that is about
34/1358 ≈ **0.025** off its residual, which is the largest single number
anything in this queue has offered. It is also the page whose experiment
came out clean.

2312 p7: unknown and possibly adverse, because 4 of the 9 admitted lines are
garbled and a garbled line can flag more glyphs than it recovers.

## 8. The decision

**Not started, and the queue order should change.** The honest shape is two
steps:

1. the edge band on pages where a region holds ONE chart, which is 0864 p4's
   case and is clean;
2. per-region grouping for admitted glyphs, without which a page of
   side-by-side charts gets garbled lines.

Doing (1) alone on 0864 p4 would earn about 0.025 there and risk 2312 p7.
Doing both is a day's work and wants its own ten lines for (2). My
recommendation is to measure (1) restricted to single-chart regions first,
since that is a rule the census can test — 4 pages, 688 glyphs, and the
region count per page is already in hand (0864 p4 has 5 regions, so even it
is not single-chart).

## 9. What this does NOT explain

The alnum gaps against MathPix in §4 are 2,993 / 1,396 / 1,743 characters,
far more than the 364 / 264 / 38 glyphs this filter removes. The filter is a
named part of the gap and not the whole of it.

## 10. Provenance of the number in the queue

The item was logged as "the 30 lost glyphs". The true figure on that page is
34, and the 30 came from my own earlier accounting, which attributed 4 of
them to `_merge_operator_names` consuming a run into one head glyph. That
accounting was beside the point: all 34 are removed by the diagram filter,
and `_merge_operator_names` consumes its 4 from a different population.
