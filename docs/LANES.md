# The lane contract

Which reading a document gets, decided once, in one pure function, and reported
in the same words by `route`, `drill` and `doctor`.

The decision lives in **`src/pdfdrill/ocr_router.py:choose_route`**. It is pure:
it reads no file and makes no call. Everything it needs is passed in, which is
why `PDFDRILL_SANDBOX=1` can ask a keyed machine what the keyless one will do
and get a true answer.

```
pdfdrill route <pdf>                  # the lane, and why
pdfdrill route <pdf> --run            # …and run it
PDFDRILL_SANDBOX=1 pdfdrill route <pdf>   # the answer the fresh sandbox gives
pdfdrill drill <pdf>                  # the whole way, by this contract, to an inspect.html
```

## Five lanes, in a fixed order

The order **is** the contract. A lane is taken only because every cheaper one
above it is unavailable, so the same document always gets the same answer and
the answer never depends on who asked.

| # | lane | when | cost | command |
|---|---|---|---|---|
| 1 | `born_digital` | the PDF carries its **own** text layer, and is not a scan with somebody's OCR underlaid | free | `pdfdrill model` |
| 2 | `source` | no text layer, but an arXiv e-print — the author's LaTeX | free | `pdfdrill model` |
| 3 | `gemma` | a scan, and `MAKORA_API_KEY` / `NOVITA_API_KEY` | **metered** | `pdfdrill gemmaocr` |
| 4 | `mathpix` | a scan, no Makora key, `MATHPIX_APP_ID/KEY` | **paid** | `pdfdrill mathpix` |
| 5 | `geometry` | a scan, **no reading key at all** — the sandbox's default | free | `pdfdrill gemmaocr --geometry-only` |

1. **`born_digital`** wins at any page count: a text layer beats a page count.
   The glyphs are the author's, with their coordinates. On an arXiv document the
   author's LaTeX merges into it, so this lane gives geometry **and** gold math.
2. **`source`** is gold structure and gold math with no page geometry of its
   own; `geometry --layout` supplies the boxes (see below).
3. **`gemma`** is metered at a measured **0.000718 EUR per printed page** (390
   pages, 1,711,193 tokens, 0.28 EUR) and refused against
   `PDFDRILL_OCR_BUDGET_EUR` before the first call.
4. **`mathpix`** is the richest reading there is. It is lane 4 and not lane 3
   because `gemmaocr` measured **88 % of its boxes on penev_A at about a
   fortieth of the price**.
5. **`geometry`** reads no words. The detector is offline and free, so the
   page's *structure* can still be had — typed boxes, a page map — and saying
   what is missing beats refusing the document.

**OCR is the last resort, not the first.** Lanes 3–5 are reached only when the
document has neither a text layer of its own nor an author's source.

## What the previous version got wrong

Two things, both now fixed, both worth keeping written down because each looked
reasonable when it was written:

- **MathPix stood above the free source lane.** `model` called `cmd_mathpix`
  whenever a key was present and no `lines.json` existed, which made `model` a
  paid command reachable from about forty places that do not say so. It bought
  9 pages of arXiv 2402.13444v1 during a session whose whole purpose was to
  measure the free lanes. The project's own rule — a paid layer is DECLARED in
  a chain and never auto-run — had been written for `--ensure` and did not
  reach one level down. `model` now names the paid lane and does not run it;
  `model --mathpix` is the explicit opt-in.
- **The scan lanes split on page count**: "≤ 20 pages → Gemma, > 20 → MathPix".
  That threshold was set when the only alternative to MathPix was a 50 s/page
  vision call, and it was left standing after `gemmaocr` made the large book
  the *cheap* case. Page count no longer selects a lane.

## The OCR path used for nothing but geometry

A reading has two halves and only one of them costs money. The words come from
a model; the **shape** — where the lines are, which is a formula, which is a
running head, which is a figure — comes from the page's own ink and from a
detector that runs offline. The second half is available on a document that
will never be OCR'd, and on an install with no key at all.

Three places this is already used:

### 1. `geometry --layout` — boxes for a model built from something else

A model built from the author's LaTeX knows what every object **is** and has
never seen a rendered page. `merge_page_geometry` joins the two by matching an
object's opening words against the page's text, which works for prose and
cannot work for anything whose printed form is not its text: an inline
formula's text is `ax^2+bx+c = 0` and the page carries a picture of it.

`src/pdfdrill/layoutgeom.py` gives those objects the detector's boxes, by a
**monotone walk between the objects the text match did place**. Each unboxed
object may only take a box of its own class lying between its neighbours'
anchors, and each box is taken once — the same discipline
`gemma_reader.align_anchored` uses on the ink, for the same reason: a single
monotone pass accumulates its errors and an anchor is what stops one wrong box
from shifting every box below it. Where the window holds no box of the right
class, **the object keeps none**: a wrong box cannot be detected downstream.

Measured on arXiv 2402.13444v1 (9 pages, keyless, cold):

| | elements | with no box |
|---|---|---|
| `drill` as it was (source model, no geometry) | 131 | **131** |
| + `merge_page_geometry` (the text match) | 131 | 54 |
| + `raw_text` consulted, so `.bbl` entries are matched | 131 | 29 |
| + `geometry --layout` | 131 | **8** |

0 boxes outside their page frame, 0 zero-area, furthest edge 0.949.

### 2. `gemmaocr --geometry-only` — the keyless install's scan lane

Splits the sheets, detects the layout, and writes a `lines.json` in which every
line has a box and a **type** and no text: the ink gives the rows, the detector
gives each row its type, and a figure or a table is one object rather than the
sixty ink rows its strokes form. Free, offline, and it refuses to overwrite a
reading that was paid for.

Measured on 3 sheets of penev_A: **12 printed pages, 273 typed boxed lines,
0.0000 EUR.**

`model` is **not** its consumer — a model keeps what has prose, and 273 boxless
words come out as ten empty Paragraphs. Its consumers are `linescmp` (score the
geometry against a reading), `geometry --layout`, and the detector cache, which
makes the metered read cheaper when a key arrives.

### 3. The display anchors inside `gemmaocr`

Already shipped: the detector's display boxes anchor the ink alignment, which
took display formulas from 5 of 116 to 110 of 116 on penev_A.

### Further ideas, not built

- **Type the born-digital lane's lines.** `chars_to_lines` emits `text` for
  nearly everything; the detector's class for the box a line sits in would give
  a born-digital document MathPix-grade line types for free. That is the
  geometry-only lane's `_type_for_row` applied to glyph rows instead of ink
  rows, so most of it exists.
- **Grid detection for tables.** collatz14 has 522 non-empty cells with no
  boxes. The detector's `table` box plus the drawn rules (`inkmeasure` at 800
  dpi) would bound them without a reading.
- **A geometry-only reading as a CHECK on a bought one.** Both are boxes over
  the same page; `linescmp` already scores one against the other, so a page
  whose paid reading disagrees with the free geometry is a page to look at.
- **The table of contents.** The remaining gap on penev_A: 49 of 79
  `table_of_contents_row`. Neither reader *types* a contents list, so this is
  geometry on two sheets — a leader-dot run is a measurable thing and nothing
  looks for it.

## Simulating the sandbox

The work ships to an install with no keys; the machine it is built on has
seven, so every lane decision is a different decision on the two machines.

```
PDFDRILL_SANDBOX=1 pdfdrill doctor      # says it is answering as a keyless install
PDFDRILL_SANDBOX=1 pdfdrill route <pdf>
PDFDRILL_SANDBOX=1 pdfdrill drill <pdf>
```

Under `PDFDRILL_SANDBOX=1` every name in `env.CREDENTIAL_NAMES` answers empty
and `.env` is never read. Nothing else changes: the same code runs, it is simply
told the truth about a different install. `PDFDRILL_OCR_BUDGET_EUR` keeps
working — a budget of nothing is not the same as no budget.
