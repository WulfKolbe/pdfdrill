# The orphaned accent class: depth before code (group rule 6)

T-0156, 2026-11-21. Asked for by the coordinator after p174 was counted:
`lib:6d90e8d27b8b p174` is `ours`' worst board row at 0.0920, and 23 of its
25-point gap against MathPix is unpaired glyphs, 9 of the 19 on side A being
accents that were never composed.

The code this is about: `_compose_text_accents` and the row grouping in
`pdfreader.docmodel_six`.

**The named experiment was run first and it REFUTES the proposal.** §7.

---

## 1. The defect, measured

On p174 our reader holds the accent glyphs with the right LaTeX — `acute`
×8 → `\acute`, `circumflex` ×7 → `\hat` — and the reading contains **no**
`\acute`, `\hat` or `\dot` at all. 15 bare accent characters are emitted
instead, in maths spans of their own: line `p1l18` is two bare accents with
no base letter, written `'$´ ´$'`.

They count unpaired twice over: the ink's accent sits over a letter we never
composed (side A), and our stray `´` sits where the ink has nothing (side B).

Board-wide the class is **12 orphaned accent glyphs on 2 pages** — 10 on
p174, 2 on 0864 p4 — where an "orphan" is a row whose live glyphs are all
accents.

## 2. What the two best existing systems do — measured, not assumed

| | accent commands on p174 | bare accent characters |
|---|---|---|
| **MathPix** | **22** (`\dot` ×22) | **0** |
| ours | 0 | 15 |
| Gemma4 | no reading on this page in board28 | — |

MathPix composes every one and writes them all as `\dot`. That is the
comparand, and it is a long way ahead.

Note the disagreement about WHICH accent: MathPix reads 22 dots, the judge's
side A lists `˙` ×5 together with `´` ×2 and `ˆ` ×2, and our font subset
(`Gdvdkgesint10`) names its glyphs `acute` and `circumflex`. So composing
what our glyph names say would produce `\acute{x}` and `\hat{x}` where the
page may well show `\dot{x}`. Composition alone would fix the PAIRING and
could still leave the accent misnamed; that is a second question and it is
not answered here.

## 3. Where it is NOT blocked

Both type gates of `_compose_text_accents` already pass, measured:

    name=acute        family=text   in _TEXT_ACCENT_MARK=True   tex.kind=accent
    name=circumflex   family=text   in _TEXT_ACCENT_MARK=True   tex.kind=accent

So the blocker is neither the family test nor the accent table. And it is not
the 0.08-em row window either, which is what the module's own accent comment
blames — see §7.

## 4. Where it IS blocked

The third gate: "THE BASE IS THE NEXT GLYPH IN THE ROW, and only if it sits
under the accent." On p174 the base is not the next glyph in the row, and
cannot be made so by the content stream. MEASURED, for each of the 15
accents, its stream neighbours:

    accent x=195.6   next '´' x=195.6  OVERLAP    prev 'e' x=334.4  no
    accent x=256.9   next '´' x=256.9  OVERLAP    prev '.' x=383.3  no
    accent x=154.0   next 'ˆ' x=154.0  OVERLAP    prev ':' x=377.6  no
    accent x=198.3   next 'ˆ' x=198.3  OVERLAP    prev 't' x=357.8  no
    accent x=127.9   next 'ˆ' x=127.9  OVERLAP    prev 'c' x=229.1  no
    accent x=182.7   next 'ˆ' x=182.7  OVERLAP    prev 'c' x=267.2  no

**Every accent's stream neighbour is another accent at the same x**, and the
nearest non-accent glyph in the stream is 130 to 180 points away. This
producer emits the accents in a run of their own; it does not put an accent
beside its base.

## 5. The idea that was proposed, and why the mechanism cannot work

Proposed (coordinator, and named by me): stream adjacency restricted to
accent glyphs alone — move an accent that sits in a row of accents into the
row holding its immediate stream neighbour, then let
`_compose_text_accents` run.

The mechanism rests on the premise in the module's accent comment: "the
accent at stream 2635 and the `O` at 2636 — adjacent in the stream". That
premise is true for the `\widetilde{O}` case the comment was written from and
**false for p174's producer** (§4). So the move cannot deliver a base to
compose against, whatever is done with the rows.

This also tells us something about `_merge_stream_lines`, which is written
but not called because enabling it measured worse (display blocks 817 → 98
against a gold of 421, crops 548 → 1303): on this page it would not have
helped either, independently of that measurement.

## 6. The expected change on the board

If all 10 of p174's orphans composed, each stops counting twice, so the
residual would fall by about 20/1358 ≈ **0.015**, from 0.0920 to roughly
0.077 — the coordinator's own estimate, and I agree with the arithmetic.
Nothing in §7 earns it.

## 7. The cheapest experiment that could show the idea is wrong — RUN FIRST

Run as a probe, not a change: `_group_lines` wrapped so that an accent in an
accents-only row is moved into its stream neighbour's row, inserted
**immediately before** that neighbour.

    page                    bare accents   accent commands   display lines
    p174 before                      15                 0              21
    p174 after (13 moved)            15                 0              18
    0864 p4 before                    2                45              14
    0864 p4 after (0 moved)           2                45              14

**13 accents moved, 0 composed, and p174 lost 3 display lines.** Refuted on
both of the coordinator's clauses: it composes fewer than 10 of the 12, and a
count moves away from gold.

A FALSE REFUTATION CAME FIRST, and is recorded because the lesson is the
expensive one. The probe's first version `append`-ed the accent to the
destination row instead of inserting it before its base, so composition could
not fire for a reason that was the probe's own. The numbers were identical to
the honest run — 13 moved, 0 composed — and I would have reported "refuted"
on a broken experiment had the two gates in §3 not been checked and found
passing, which made 0 compositions impossible to explain. Same class as the
empty-glob error earlier today: a measurement that cannot distinguish a
negative result from a broken instrument.

## 8. The alternative, named rather than started

If neither the row window nor the stream can find the base, GEOMETRY can: TeX
sets an accent directly over its base, so the base is the glyph whose x-range
contains the accent's centre and whose baseline sits about an em below. §4's
table shows those boxes DO overlap in x — with each other, because the pairs
share an x, which means the search has to look DOWN rather than along.

`structure._merge_accents` already composes a maths accent and may hold this
search already; whether it does, and why it does not reach these glyphs, is
the next thing to read. That is a different proposal from the one refuted
here and needs its own ten lines.

## 9. The second question, unanswered

Even composed, `\acute{x}` or `\hat{x}` from our glyph names may not be what
the page prints, since MathPix reads 22 dots on it (§2). A fix that pairs the
glyphs and names the accent wrongly would move the unpaired count and leave a
glyph finding. Worth settling before building, by reading the page.

## 10. Decision

**Not started.** The proposal is refuted by its own cheapest experiment, and
the alternative in §8 is a different idea that needs its own ten lines and a
look at `structure._merge_accents` first. The class is 12 glyphs on 2 pages;
the 30 lost glyphs on 0864 p4, next in the queue, are a larger population.

---

## 11. CORRECTED: they were never accents (same day)

inkdrill-10 rendered the glyphs and the coordinator read them. The glyphs
named `acute` and `circumflex` in `TUJKXG+Gdvdkgesint10` are **integral
signs** from the `esint` package. The font carries no ToUnicode, so pdfminer
falls back to a standard encoding and names whatever sits at those codes; the
names are the subsetter's and they are wrong.

**This explains §4's own measurement, which I had in hand and read wrongly.**
"Every accent's stream neighbour is another accent at the same x, and the
nearest non-accent glyph is 130 to 180 points away" is `∫ x dx = ∫` — two
integrals — and "no base nearby" is simply what an integral looks like. I
took the glyph names as the identity and reasoned about composition; the
decisive evidence was already on the page and needed an outline, not more
inference.

So §1–§7 stand as a refutation of stream adjacency for accent composition,
and their SUBJECT was wrong for p174: that page has no orphaned accents of
this kind. What it has is

1. 15 esint integrals read as bare `´`/`ˆ` — fixed in the commit that
   carries this correction: the `esint` font is a maths-extension family and
   its glyph names are not evidence, so cid 30 and cid 31, both verified by
   rendering at 600 dpi, map to `\int`;
2. 5 real dot accents in `JSLHNA+DlgbwdCMR9` (`dotaccent`), missing from the
   reading — a separate class, not yet measured.

§8's downward base search is **withdrawn** by the coordinator and replaced by
those two. The board-wide "12 orphaned accent glyphs" of §1 is therefore also
wrong: 10 of the 12 were these integrals.

THE RULE THAT CAME OUT OF IT, and it is the useful part: where a glyph name
and the printed outline disagree, **the outline decides**. Both of us
inferred an identity from the name — I inferred "accent" and the coordinator
first inferred "dot" — and only rendering settled it.
