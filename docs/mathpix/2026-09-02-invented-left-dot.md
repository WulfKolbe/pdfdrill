# A ninth defect: an operator read as a closing fence

pdfdrill / inkdrill — 2026-09-02. 26 rows, 4 documents, 3 `pdf_id`s.

## The mechanism

MathPix reads the interior-product / contraction operator (`⌟`, U+231F) as
a **closing delimiter** rather than as a binary operator, and then invents a
`\left.` at the front of the expression to make the `\right` legal.

`\left.` is a NULL delimiter: it prints nothing. It can never correspond to
anything on the page. Its only possible purpose is to balance a `\right`
that should not be there — so a value beginning with `\left.` and carrying
a `\right\lrcorner` is, on its face, a fence the model invented.

The result is valid LaTeX that compiles, renders almost identically to the
page, and **means something different**: the bracket group moves.

## The clean example

`mielke-geometrodynamics_EQ0294`, p101, confidence 0.510
`https://cdn.mathpix.com/cropped/b173365e-9184-4902-bd66-732270e80db9-101.jpg`

The page prints `⌋` three times, each time as a binary operator:

    Σ_α = e_α ⌋ L − (e_α ⌋ DΨ) ∧ ∂L/∂DΨ − (e_α ⌋ Ψ) ∧ ∂L/∂Ψ .

MathPix returned the same printed glyph three different ways:

| occurrence | returned | arity |
|---|---|---|
| 1st | `\downharpoonleft` | operator — wrong glyph, right arity |
| 2nd | `\downharpoonleft` | operator — wrong glyph, right arity |
| 3rd | `\right\lrcorner` | **fence — wrong arity** |

    \left.\Sigma_{\alpha}=e_{\alpha} \downharpoonleft L-\left(e_{\alpha}
    \downharpoonleft D \Psi\right) \wedge \frac{\partial L}{\partial D \Psi}
    -\left(e_{\alpha}\right\lrcorner \Psi\right) \wedge
    \frac{\partial L}{\partial \Psi} .

The third term's `\left(` is now closed by the corner, and the parenthesis
that the page prints after `Ψ` has become the `\right)` at the very end of
the equation. So the group is no longer `(e_α ⌋ Ψ)`; it runs from the start
of the equation to just after `Ψ`. Compiled with xelatex: **0 errors.**

## Why this is not a glyph-ambiguity problem, and not a vocabulary gap

Four rows emit the SAME printed symbol BOTH ways inside ONE expression.

`Complex_Analysis..._EQ0851`, p241, confidence 1.000
`https://cdn.mathpix.com/cropped/c1ec8e32-46ee-4385-a2a3-8e7902116925-241.jpg`

The page prints

    ∂̄_b(A_{r−p}(g + Φ⌟∂_b v)) = g + Φ⌟∂_b v.

and MathPix returned

    \left.\left.\bar{\partial}_{b}\left(A_{r-p}(g+\Phi\lrcorner \partial_{b} v
    \right)\right)=g+\Phi\right\lrcorner \partial_{b} v .

The first `Φ⌟∂_b v` is `\Phi\lrcorner \partial_{b} v` — **correct, bare
operator**. The second, eight tokens later and visually identical, is
`\Phi\right\lrcorner \partial_{b} v` — **a fence**. The model has the right
token and used it correctly in the same equation, so this is neither a
missing vocabulary entry nor an ambiguous glyph. It is a decoding decision
that flipped mid-expression.

Note also the collateral damage: `\left(A_{r-p}(g+...\right)` now closes in
the wrong place, and TWO `\left.` were invented to keep the whole thing
balanced.

## Why neither side's existing checks catch it

- **It compiles.** 0 errors under xelatex with the full amssymb preamble.
- **Your confidence is high.** Median confidence over the 16 rows that carry
  one is **1.000**; 11 of 16 sit at 1.000. Range 0.351–1.000.
- **Our ink comparison cannot see it.** The rendered image is nearly
  identical to the scan — the corner shrinks to fence size and hugs the
  preceding symbol, and a closing bracket still appears further right. All
  four measured rows read as agreement: three `N|+0` (noise, zero component
  delta), one `K|+0` (clean).

This is the shape we reported as a negative result earlier: high confidence
plus an ink difference is a rendering-difference detector, not a defect
detector. Here there is not even an ink difference. **A grouping error is a
small-ink error**, which is why it needs to be caught at decode time.

## A cheap structural check

A value that begins with `\left.` and contains `\right\lrcorner` (or any
corner) is almost certainly this defect: the null delimiter has no possible
referent on the page. Over 634,258 equations in 1,349 documents the pattern
occurs 26 times, so the check is nearly free and the precision looks high.

## The 26 rows

| identifier | page | conf | crop (pdf_id embedded) |
|---|---|---|---|
| `1-s2.0-S039304401100026X-main_EQ0015` | 005 | 1.000 | `https://cdn.mathpix.com/cropped/18d08393-1b9c-49f5-b391-22a727fe6f06-05.jpg` |
| `1-s2.0-S039304401100026X-main_EQ0018` | 005 | 0.983 | `https://cdn.mathpix.com/cropped/18d08393-1b9c-49f5-b391-22a727fe6f06-05.jpg` |
| `1-s2.0-S039304401100026X-main_EQ0019` | 005 | 1.000 | `https://cdn.mathpix.com/cropped/18d08393-1b9c-49f5-b391-22a727fe6f06-05.jpg` |
| `1-s2.0-S039304401100026X-main_FO0096` | — | — | — (inline formula: no page, no crop) |
| `1-s2.0-S039304401100026X-main_FO0121` | — | — | — (inline formula: no page, no crop) |
| `1205.5935v1_FO0614` | — | — | — (inline formula: no page, no crop) |
| `1205.5935v1_FO0615` | — | — | — (inline formula: no page, no crop) |
| `Complex_Analysis_-_Peter_Ebenfelt__et_al.___Birkhauser__2010__WW_EQ0844` | 238 | 1.000 | `https://cdn.mathpix.com/cropped/c1ec8e32-46ee-4385-a2a3-8e7902116925-238.jpg` |
| `Complex_Analysis_-_Peter_Ebenfelt__et_al.___Birkhauser__2010__WW_EQ0851` | 241 | 1.000 | `https://cdn.mathpix.com/cropped/c1ec8e32-46ee-4385-a2a3-8e7902116925-241.jpg` |
| `Complex_Analysis_-_Peter_Ebenfelt__et_al.___Birkhauser__2010__WW_EQ0857` | 242 | 1.000 | `https://cdn.mathpix.com/cropped/c1ec8e32-46ee-4385-a2a3-8e7902116925-242.jpg` |
| `Complex_Analysis_-_Peter_Ebenfelt__et_al.___Birkhauser__2010__WW_EQ0859` | 242 | 1.000 | `https://cdn.mathpix.com/cropped/c1ec8e32-46ee-4385-a2a3-8e7902116925-242.jpg` |
| `Complex_Analysis_-_Peter_Ebenfelt__et_al.___Birkhauser__2010__WW_EQ0860` | 242 | 1.000 | `https://cdn.mathpix.com/cropped/c1ec8e32-46ee-4385-a2a3-8e7902116925-242.jpg` |
| `Complex_Analysis_-_Peter_Ebenfelt__et_al.___Birkhauser__2010__WW_EQ0861` | 242 | 1.000 | `https://cdn.mathpix.com/cropped/c1ec8e32-46ee-4385-a2a3-8e7902116925-242.jpg` |
| `Complex_Analysis_-_Peter_Ebenfelt__et_al.___Birkhauser__2010__WW_EQ0862` | 242 | 1.000 | `https://cdn.mathpix.com/cropped/c1ec8e32-46ee-4385-a2a3-8e7902116925-242.jpg` |
| `Complex_Analysis_-_Peter_Ebenfelt__et_al.___Birkhauser__2010__WW_EQ0863` | 242 | 1.000 | `https://cdn.mathpix.com/cropped/c1ec8e32-46ee-4385-a2a3-8e7902116925-242.jpg` |
| `Complex_Analysis_-_Peter_Ebenfelt__et_al.___Birkhauser__2010__WW_EQ0864` | 242 | 1.000 | `https://cdn.mathpix.com/cropped/c1ec8e32-46ee-4385-a2a3-8e7902116925-242.jpg` |
| `Complex_Analysis_-_Peter_Ebenfelt__et_al.___Birkhauser__2010__WW_FO3301` | — | — | — (inline formula: no page, no crop) |
| `Complex_Analysis_-_Peter_Ebenfelt__et_al.___Birkhauser__2010__WW_FO3330` | — | — | — (inline formula: no page, no crop) |
| `Complex_Analysis_-_Peter_Ebenfelt__et_al.___Birkhauser__2010__WW_FO3334` | — | — | — (inline formula: no page, no crop) |
| `Complex_Analysis_-_Peter_Ebenfelt__et_al.___Birkhauser__2010__WW_FO3352` | — | — | — (inline formula: no page, no crop) |
| `mielke-geometrodynamics_EQ0294` | 101 | 0.510 | `https://cdn.mathpix.com/cropped/b173365e-9184-4902-bd66-732270e80db9-101.jpg` |
| `mielke-geometrodynamics_EQ0306` | 103 | 0.406 | `https://cdn.mathpix.com/cropped/b173365e-9184-4902-bd66-732270e80db9-103.jpg` |
| `mielke-geometrodynamics_EQ0579` | 186 | 0.351 | `https://cdn.mathpix.com/cropped/b173365e-9184-4902-bd66-732270e80db9-186.jpg` |
| `mielke-geometrodynamics_EQ0686` | 222 | 0.497 | `https://cdn.mathpix.com/cropped/b173365e-9184-4902-bd66-732270e80db9-222.jpg` |
| `mielke-geometrodynamics_FO0894` | — | — | — (inline formula: no page, no crop) |
| `mielke-geometrodynamics_FO1309` | — | — | — (inline formula: no page, no crop) |

`FO` rows are inline formulas; our projection carries no page, confidence or
crop for those, which is our limitation and not yours.

Documents: Complex Analysis (Ebenfelt et al., Birkhauser 2010) 13 ·
Geometrodynamics (Mielke) 6 · 1-s2.0-S039304401100026X 5 · 1205.5935v1 2.
Ten of the 26 begin with TWO invented `\left.`. All 30 corner occurrences
after `\right` are `\lrcorner`.

## One unrelated question: the render is 250 dpi

We measured this rather than asking blind, in case it has simply never come
up. For every one of 21 documents we have both a `lines.json` and the source
PDF for, `page_width`/`page_height` divided by the PDF's own page size in
points comes to **250 dpi**, on both axes:

| page size (pt) | lines.json (px) | implied dpi |
|---|---|---|
| 612.0 x 792.0 | 2125 x 2750 | 250.0 x 250.0 |
| 595.3 x 792.0 | 2067 x 2750 | 250.0 x 250.0 |
| 453.5 x 683.1 | 1575 x 2372 | 250.1 x 250.0 |
| 411.4 x 619.9 | 1429 x 2153 | 250.1 x 250.1 |
| 235.0 x 364.0 | 816 x 1264 | 250.0 x 250.0 |

21 of 21, page sizes from 235 pt to 612 pt wide, every one between 250.0 and
250.2. So it is a fixed rasterisation target, not a per-document choice.

Is 250 dpi configurable, per request or per account? We are not asking you to
change the default. We ask because the geometry we compare against is derived
from it: our own rasteriser runs at 400 dpi and above, and every region we
take from you is scaled by 72/250 into PDF points before it can be compared
with anything. Knowing whether that constant is a constant — rather than
something we have inferred from 21 documents that happen to agree — decides
whether we can treat it as a contract or must keep re-deriving it per
document. This is the kind of thing an admin can probably confirm in one
line.

## What would help

1. Confirm whether the decoder can emit `\right` before a symbol that the
   training data only ever shows as a binary operator.
2. If the detokenizer contracts or re-fences, whether that step can be made
   to check that a `\right` has a `\left` that came from the image rather
   than from balancing.
3. Whether `\left.` is ever a legitimate output of the model for a printed
   page, or is always inserted to balance.
