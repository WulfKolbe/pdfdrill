# The `decline` lane — refusing a document before it costs an hour

*2026-09-24. A design note, not an implementation. Written from four
documents that cost real time on a corpus run, with the measurements that
produced each number.*

## The question

A full-corpus `pdf2mmd` run spends most of its time on documents that
return nothing. Should pdfdrill refuse them early, and on what evidence?

## What the measurements actually say

The assumption going in — mine and the user's — was "scanned books are
slow". **That is false**, and measuring it first saved building the wrong
gate. 20 pages each:

| document | time | glyphs |
|---|---|---|
| Carroll, 520pp scan, 147 MB | **0.8s** | 0 |
| Red Book, 404pp scan, 203 MB | **1.0s** | 0 |
| Wolfram, 760pp, 205 MB | **178.2s** | 24,946 |

pdfminer never decodes image data unless asked, so a pure image scan is
among the **cheapest** documents we read. Four documents that did cost
time had four unrelated causes:

| document | cause | measurement |
|---|---|---|
| Wolfram, *Fundamental Theory of Physics* | vector graphics; cost tracks **diagram count**, not glyphs | 8,790 glyphs → 4.1s; 4,796 glyphs + 9 diagrams → **126.6s** |
| IT-Handbuch (Z-Library) | scan with a tesseract OCR layer; every page correctly refused | 1.9 s/page to produce `*[page N: OCR text layer; not projected]*` — **16 min for 504 pages of nothing** |
| *Mathematica Beyond Mathematics* | `(cid:N)` — a font whose encoding cannot be read | 26% of the markdown was a header block describing unreadable text |
| Handbuch Elektrotechnik, 1,175pp | **our own O(n³) bug**, not the document | 5.25 s/page → 2.9 s/page after the fix |

Two of those are now fixed at source (the `(cid:N)` refusal in
`listings.accumulate`, the baseline memo in `docmodel_six`). A gate would
have "solved" both by skipping good documents.

## The evidence ladder

Ordered by cost. Stop at the first rung that answers.

| rung | cost | catches |
|---|---|---|
| first 1 KB — `%PDF` magic | µs | the 143-byte nginx *410 Gone* named `.pdf` (**done**, 781p) |
| `pdfinfo` | ms | 0 pages, encrypted, absurd page count |
| `pdffonts` | ms | `GlyphLessFont` → OCR underlay; 7,962 subsets → pathological; no fonts → pure scan |
| one page of glyphs | ~0.5s | `(cid:N)` density, invisible text |
| marks on a sample page | ~1s | the vector-graphics cost class |

The first three are already read by `size`. `route` already consults them
to pick a lane. **The ladder is not new work; the verdict is.**

## The design

`route` is a state machine over `born_digital | gemma | mathpix |
unknown`, it reports *why*, and `producer_policy` can already **veto** a
lane in prose. What it cannot say is *"none — do not read this"*.

1. **Add a `decline` lane**, with a reason and an `--anyway` override.
   `producer_policy`'s rule governs it: *the machine must say why it
   skipped a lane, never skip it silently.*

2. **Refuse and budget are different verdicts.** The 410 page deserves
   refusal. The Wolfram book is **valid and readable**; it merely costs
   9 s/page on diagram clustering. Conflating them throws away good
   documents. Refusal is per **document**; a budget is per **page** —
   e.g. skip diagram clustering above a mark count, keep the glyphs, and
   say so in the output.

3. **Every expensive layer gets `requires: route`**, so `--ensure` cannot
   step past the gate.

4. **`profile` is most of the content already** (`unmapped-glyphs`,
   `invisible-text`, `no-text-layer`, `diagram`, with evidence per page) —
   but it runs pdf2mmd over the whole document, which is the cost we are
   trying to avoid. The cheap rungs belong *before* it; `profile` stays
   the instrument for documents that pass.

## The risk, stated plainly

**A gate makes slow code look like bad input.** The 1,175-page handbook
presented as pathological — 7,962 font subsets — and the real cause was
our O(n³) baseline recomputation. A cost gate would have skipped a
perfectly good book and hidden the defect indefinitely.

Therefore: anything declined **for cost** must record its measurement,
and someone must read that log, or the gate becomes the place where bugs
go to hide. Declining for *correctness* (not a PDF, 0 pages) carries no
such risk.

## Caveat on tuning data

The IUST corpus (6,141 PDFs, arXiv 1812.09961) is *designed* as header
edge cases, so a gate tuned on it is tuned on adversarial input. Of the
four documents that actually cost time — all from the user's own library
— **only one** would have been caught by header checks. The other three
needed font, glyph and mark evidence.

## Already done

- `size` refuses a file whose magic is not `%PDF`, naming what it is (781p)
- `listings.accumulate` refuses a block >30% `(cid:N)` (781p)
- `pageprofile` reports `unmapped-glyphs` / `invisible-text` / `no-text-layer`
- `pdfdrill profile` is a layer with `done_when: file:{stem}.profile.json` (781o)

## Open

- Thresholds for the cost rungs — **unmeasured**. Needs a per-document
  timing log over a real corpus run, not a guess.
- Whether `decline` should refuse or merely warn by default.
- Whether the per-page budget belongs in pdf2mmd (where the cost is) or
  in pdfdrill (where the decision is).
