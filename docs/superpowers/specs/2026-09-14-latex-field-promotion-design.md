# Promotion of competing LaTeX readings into the standard field names

**Decision recorded 2026-09-14, by the user.** Not implemented; this is the
shape the next change follows.

> The best available gets the standard name and all other get another field
> name. We can keep a copy of all different versions and only copy the actual
> to the standard field names. We will shortly get the pdfminer latex also,
> that has always correct symbol names.

## Why now

A third reading is arriving. pdfminer over the PDF's own `/Encoding
/Differences` yields glyph NAMES — `floorright`, `similarequal`, `Lslash` —
which is the identity information task 679–688 spent this week reconstructing
by hand: 48 census-verified repairs across 6 documents, 30 overprints, and a
`NAME_TOKENS` table whose every entry had to be measured off a row because one
entry written from memory (`similarequal` → `\cong`, actually `\simeq`) put 29
false positives into a manifest. pdfminer hands that over directly.

Under today's shape a third reading has nowhere to go that any reader will
look at.

## What is actually there today

Not two fields. Ten, across 1,350 models in `~/pdfdrill-library`
(`docmodel/corpus_props.json`):

| objects | docs | prop | types |
|---|---|---|---|
| 643,364 | 2,286 | `latex` | Equation, Formula |
| 112,066 | 955 | `latex_raw` | Equation |
| 41,665 | 325 | `latex_original` | Diagram, Equation, Formula, Table |
| 29,571 | 1,135 | `latex_code` | Diagram, LtxCommand, Table |
| 1,400 | 50 | `latex_prepunct` | Equation, Formula |
| 241 | 2 | `latex_expanded_by` | Equation, Formula |
| 51 | 12 | `latex_fragment` | MathTail |
| 47 | 12 | `latex_pretail` | Equation, Formula |
| 44 | 14 | `latex_overlaid` | Table |
| 31 | 6 | `latex_refined` | Equation, Formula |

They are not one kind of thing, and the promotion rule applies to only some of
them:

**Competing values for the same maths** — the promotion set: `latex`,
`latex_raw`, `latex_original`, `latex_refined`, `latex_code`, `latex_overlaid`.

**Parts deliberately held OUT of the value** — never promoted, never merged in:
`latex_prepunct`, `latex_pretail`, `trailing_punct` (025 — punctuation printed
after the maths, set beside it), `latex_fragment` (a MathTail partial).
Putting any of these back into `latex` changes what renders.

**Provenance, not a value**: `latex_expanded_by`.

Two standard names already exist, split by object type: `latex` for
Equation/Formula, `latex_code` for Diagram/LtxCommand/Table. The rule has to
name both.

## The flat namespace is the defect

`latex` today means *three* things at once: the MathPix reading, macro-expanded,
un-refined. Those are three independent axes flattened into one name, which is
why `latex_original` and `latex_refined` had to be invented as siblings and why
neither composes: there is no field for "the author's reading, unexpanded, with
the verified repair applied," and there is nowhere to put pdfminer.

The scheme needs two axes, not a list:

- **source** — which reader produced it: mathpix, eprint (author), pdfminer,
  refined (our verified repair), overlay.
- **expansion state** — macros intact, or expanded (289: original+author scored
  70/176 against expanded+generic 151/207, which is why the renderer compiles
  the expanded one and needs no author preamble).

`latex_original` is not a competing source. It is the unexpanded axis of
whichever source won. Treating it as a source is the mistake to avoid carrying
forward.

## What the rule buys: rule 24, at write time

This is the strongest argument for the user's scheme, and it is measured.

`latex_refined` is read only through `refine.REFINED_FIELD`, behind a
`--prefer-refined` projection flag (233). A flag means two projections of one
document read *different fields for one record* — exactly the shape rule 24
(HANDOVER-RULES) was earned on: `inlinectx` read `ln["text"]` while the model
read `text_display or text`, and 27 rows silently lost their host line. Any
consumer reading `latex` alone today ignores every accepted repair.

Promotion at write time deletes the flag. Every reader becomes correct by
default, because there is one field and the writer already decided. That is the
point of the change, and it is worth more than the disk it costs.

## Four constraints the scheme must respect

Each of these is measured, and each one breaks a naive reading of "only copy
the best to the standard field."

**1. ink must measure the UNPROMOTED MathPix reading.** The measure build runs
`prefer_refined: False` deliberately: ink measures what MathPix output against
the ink on the page, not what we corrected it to. If the standard field holds
the best reading, ink cannot use the standard field. So `latex_mathpix` is not
an archival copy — it is a field a named reader needs by name, and it must
survive promotion as a first-class prop. Any design that treats the non-winning
copies as history breaks the measurement chain.

**2. Overwriting `latex` reverses 232, so the promotion must be recorded.**
232's rule was that `latex` is never overwritten, and 233 exists because of it.
The user's scheme deliberately changes that. What made "never overwrite" safe
was that a wrong refinement stayed visibly separate; under promotion a wrong
promotion is invisible unless the winner is stamped — which source won, on what
evidence, and when. 685/686 had to withdraw 12 wrong refinements and demote 17
ink-only ones; without a stamp naming the evidence class, that withdrawal would
have had nothing to key on. `withdraw_one` needs an inverse that also demotes.

**3. pdfminer is authoritative on SYMBOL IDENTITY, not on structure.** It gives
glyph names and positions; it does not give layout. MathPix gives structure and
misreads symbols. So "best available" is **not a total order over sources** —
it is per-property, and the merge is per-symbol. The 48 census repairs are
exactly that merge performed by hand: MathPix's structure, pdfminer-class
evidence for the symbol. A rule that promotes a whole value from the
highest-ranked source would take pdfminer's symbols and lose MathPix's
structure. `justifies()` already encodes the narrow version of this (a repair
must be a substitution, not a rewrite) and refused three of my own repairs on
it.

**4. The gate is "renders", not "looks better".** MiniMax returned
`\slashed{J}`, which passes `display_safe` — that check does not ask whether a
command exists — and fails at xelatex because the package is not loaded
(`cancel` is, at `report_tex.py:811`). Eight rows across six documents carry an
empty mandatory argument (4 `\text{}`, 3 `\frac`, 1 `\sqrt`). A promotion gate
that compares strings will promote those. It has to compile.

And the negative result that rules out the obvious shortcut: **no magnitude
threshold separates correct repairs from wrong ones.** A correct repair sat at
delta −95 with similarity 0.039. Promotion cannot be decided by how different
the candidate is.

## Sketch, for the change that implements it

Not settled; recorded so the next session starts from the constraints rather
than rediscovering them.

- `latex` / `latex_code` stay the standard names and hold the current best,
  expanded, renderable.
- one source-named copy per reader that ran: `latex_mathpix`, `latex_eprint`,
  `latex_pdfminer`, `latex_refined`. Written once, never rewritten by a later
  promotion — constraint 1 depends on this.
- `latex_original` keeps its meaning (macros intact) and becomes a property of
  the winner, so a promotion rewrites it too or explicitly marks it stale.
- a stamp beside the winner: source, evidence class
  (`IDENTITY_EVIDENCE = {census, eprint, source}` vs ink), and whether it
  compiled. Without it, constraint 2 has nothing to key on.
- `latex_raw` (112,066 objects, no reader — PROPS.md calls it a GAP: "kept so a
  normalisation defect is recoverable, and nothing has ever recovered one") is
  the precedent to avoid repeating. A copy no reader is named for is not an
  audit trail, it is 112,066 objects of weight. Every source-named copy in this
  scheme must name its reader, or not be written.
- the pipeline goes subtractive next week (each pass reads the previous pass's
  result). Promotion is the natural place for that seam: each pass promotes, the
  next reads the standard name.

## Relation to other docs

- `docmodel/prop_contract.py` — the PAIRS docstring is the SSOT for the
  hand-written rows of `docs/layers/PROPS.md`; the promotion rule is stated
  there so a reader adding an eleventh latex field sees it.
- `docs/HANDOVER.md` — open item.
- `docs/layers/PROPS.md` — generated; do not hand-edit.
