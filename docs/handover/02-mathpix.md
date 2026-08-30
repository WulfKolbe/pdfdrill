# The MathPix correspondence

Five months, roughly six exchanges. The admin has confirmed defects, corrected
himself twice, filed two bugs on his own side, and once reproduced a case to
show the fault was ours. He said the withdrawal ratio was worth as much as the
defects.

## The eight that stand

Each carries full LaTeX, the region, and the CDN crop URL of MathPix's own
scan. **The `pdf_id` is embedded in that URL** —
`cdn.mathpix.com/cropped/<pdf_id>-<page>.jpg` — which is a better handle than
either side had been quoting.

Six from a structural scan over 80,593 equations at confidence ≥ 0.9:

| identifier | page | conf | defect |
|---|---|---|---|
| `2103.01507_EQ0383` | 88 | 1.000 | CJK 久 mid-equation |
| `Geometrodynamics_EQ0857` | 278 | 0.925 | CJK 匕 — the Lie derivative ℒ |
| `Introduction to Graph_EQ0010` | 33 | 1.000 | letter `l` for digit `1` |
| `Introduction to Linear_EQ0219` | 103 | 0.940 | cells dropped, arrow absorbed |
| `Numerical Linear Algebra_EQ1052` | 359 | 0.936 | two cells merged |
| `Numerical Linear Algebra_EQ0722` | 257 | — | 4×4 matrix declaring 3 columns |

**Seventh**, found by reading rather than by any check:
`Geometrodynamics_EQ0873` p284, confidence **0.99951** — a slashed L emitted as
`\nvdash`. A turnstile takes no indices; this carries two.

**Eighth**, the first the ink found alone: `Introduction to Graph &
Hypergraph_EQ0133` — `\neq \mathbb{O}` where the page prints ∅. On MathPix's
own crop the glyph is holes 2 / χ −1, the same slashed ring as its neighbour's
`\emptyset`. A sweep of 1,101 documents finds exactly one such contradiction.

Also `0707.4470_FO0175` p29: `\mathscr{g}` where the author wrote
`\mathcal{J}` — proven by counting (29 = 28 + 1, nothing unaccounted) rather
than by judging letterforms.

## The five withdrawn as ours

- `0911.3722_EQ0019` — our tail-split stripped `Pack` and `-complete.`
- the dropped ⇒ arrows — our renderer could not set U+21D2
- the 78 `slide` values — our macro-expansion order, first-wins where TeX is last-wins
- the control characters — zero in any MathPix `lines.json`; all 2,190 sit in
  fields pdfdrill creates, the signature of a broken `/ToUnicode` map
- the `1206.0238` CJK — unreproducible from any artefact held

## What MathPix corrected

**`\nvdash` is their output, but the fix is harder than assumed.** The model
emits `\not \vdash`; their detokenizer contracts `\not X` to `\nX`, which
also erases the evidence that the model chose `\not` plus a base glyph.

It is **not** a missing vocabulary entry. `\not` is in the vocabulary and pairs
with letters routinely — 227 `\not X` uses across the 21 published documents.
`\not L` typesets as exactly the slashed L wanted. **`\not L` occurrences in
the whole corpus: zero.** The name existed and the model did not reach for it —
a recognition and training-coverage gap needing annotated examples.

**`2010.14265` shows it numerically.** One conditional-independence glyph, six
spellings, 104 occurrences: `\Perp_P` 57 correct, `\not \Perp_P` 31 correct,
then `\nVdash_P` 8, `\measuredangle_P` 3, `\nvdash_P` 3, `\not
\measuredangle_P` 2 — all wrong. Look-alike substitution, not absence of a
name.

**They apply no document-local vocabulary check.** The output alphabet is 2,098
tokens the model structurally cannot exceed, and training rows with
out-of-vocabulary tokens are dropped — but neither is document-local. On that
table, **document-local frequency beats arity**: frequency catches all 16 where
arity catches 11, because arity cannot see `\measuredangle`, which takes
indices legitimately.

**Their tex.zip does not have the `\mathbb{1}` bug** — they add
`\usepackage{bbold}` after `amssymb` whenever any `\mathbb{...}` appears. But
that preamble exists only in the tex.zip path, so anyone building from `.mmd`
or `lines.json` inherits it silently.

## The negative result worth sending

**The blind-spot question is answered and it is essentially negative.** Of 20
rows where the ink flagged a difference and MathPix's confidence was ≥ 0.9:
**18 purely typographic**, 1 typographic plus a crop overrun, 1 borderline,
**zero unambiguous content errors**.

So `ink ≥ 6 AND confidence ≥ 0.9` is a **rendering-difference detector, not a
defect detector**. Their confidence field does more work on that class than
either side expected.

And the ink cannot see a defect the scan also carries — the `(204)` equation
number pulled into a maths value is invisible to comparison because the number
really is printed on the page.

## Their open items

None. The last, the `(204)` case, is answered: `1510.06699`,
`obj_de54bf1e07b8`, page 35.

## Owed to them

The seven attached defects never arrived — the ticket had no attachments.
Resend, or send the report URLs and EQ ids.
