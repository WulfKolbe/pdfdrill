# The line-type specification

**Status:** specification. The vocabulary is decided; the measurements for the
types marked *unmeasured* are not yet written.
**Date:** 2026-09-25

## Why this exists

796 gave the reader five line types where it had two, and the result read worse
than the count suggests. On `1107.2723`, measured:

| what it is | what we typed it |
|---|---|
| the paper's title, on three lines | three separate `Section`s |
| the running header `Signal & Image Processing … Vol.2, No.2, June 2011` | `Paragraph` |
| the authors and their affiliation | `Paragraph` |
| the abstract body, and the keyword list | `Paragraph` |
| each of the two text columns | `Sidenote` |

None of those is a bug in a function. Every one is a type that was never
defined, so the classifier had nowhere to put the line and `text` caught it —
and `text` becomes `Paragraph`.

The deeper fault is that the existing rules assume the reader already knows
what a document is. "A heading is larger than body text, or bold and short" is
a rule you can only check if you already agree what a heading is. This document
says what each type IS in terms a measurement can decide, so that two people —
or two passes — reach the same answer without either of them knowing LaTeX.

## The rule that governs every entry below

**A type is a measurement, not a reading.** Each entry names the property that
establishes it, and that property must be checkable on the page without
understanding the words. If the property does not hold, the line does not get
the type — it stays `text`. An unestablished type is ABSENT, never guessed.

Two corollaries, both learned by defect:

- **The softest test runs last.** A drawn rectangle beats a font-size rank
  beats an indent beats a glyph-family count. A later test may never overrule
  an earlier one.
- **The node's own verdict beats no verdict.** When nothing here establishes a
  type, a reader that already decided something (`LineNode.type == "formula"`)
  is more informed than a literal `text`. Dropping to `text` unconditionally
  lost all 23 formula lines of 1107.2723.

## The vocabulary

We adopt MathPix's names. Not because they are better — several are worse — but
because a shared vocabulary is worth more than a good private one, and every
consumer downstream (the twenty docmodel modules, the projectors, anyone
reading an export) already speaks it. Measured on `1909.00741`, MathPix emits
eighteen:

```
text 848        simple_cell 164    list_item 59      table_row 49
table_column 32 complex_cell 30    column 18         section_header 17
figure_label 10 diagram 8          equation_number 8 table 8
math 7          authors 4          footnote 4        page_info 1
title 1         abstract 1
```

We improve on it in exactly two places, both stated below: `code` (MathPix has
no code type and reads listings as prose) and `level` on a heading (MathPix
emits `section_header` with no depth).

## The types

### Established — a measurement exists

**`text`** — a line of running prose. The default, and the only type that needs
no evidence. Everything not established below is this.

**`math`** — a line whose glyphs are mathematics rather than prose.
*Established by:* at least 60% of the line's glyphs belong to a maths font
family, OR the span reader already produced LaTeX for the line.
*It is NOT:* a sentence with one inline expression in it. That is `text`
carrying a formula, and the formula is a separate object with its own
rectangle.

**`equation`** — display mathematics set on its own line.
*Established by:* the line is indented past the body margin of its own column
AND carries no prose. An equation number at the right margin is tolerated.
*It is NOT:* `math` on a line that happens to be short.

**`equation_number`** — the tag `(3.14)` belonging to a display.
*Established by:* the line is flush to the right margin of its column and its
glyphs are digits, dots and one pair of brackets.
*Never stands alone:* it is absorbed into its display before the stream is
written. A bare `(1)` reaching a consumer is the defect this prevents.

**`section_header`** — a heading.
*Established by:* the line's dominant type size ranks above the document's body
size, or it is bold and shorter than a line of body text.
*Carries:* `level`, from the size rank. MathPix does not emit a level; a
consumer that needs one has to re-derive it, and will disagree with us.
*It is NOT:* the document title. See `title`.

**`code`** — a line inside a listing.
*Established by:* the line falls within a `Listing` measured by the monospace
grid — a constant glyph advance, or a drawn frame enclosing the block.
*Why we have it and MathPix does not:* a listing read as prose loses its
indentation, and indentation is the semantics in Python. Measured 674/676.

**`diagram`** — vector art with no glyphs of its own.
*Established by:* a cluster of drawing operations with no text inside it.
*Shape:* a typed line with empty text, exactly as MathPix ships one, so a
consumer walking lines for prose skips it without being taught to.

**`column`** — the text column that holds other lines.
*Established by:* a cluster of line-starts separated from the next by more than
eight times the body type size, holding at least five lines, at least eight
lines to be a real share of the page, and at least a fifth of the page wide.
*It is NOT content.* It carries no text and `conversion_output: False`. It must
not become an object: pdfdrill's `SidenoteProcessor` claims any `column` with
text children, which is how the two text columns of a paper become 18
"Sidenote" objects whose bodies are ordinary prose (`1909.00741`, a MathPix
model — the mis-reading is not ours and predates us).

**`rotated_text`** — text set at an angle to the page: an arXiv stamp down the
left margin, a spine title, a margin note.
*Established by:* the glyphs' text matrix. `(a, b, c, d, e, f)` with `a` and
`d` at zero is a quarter turn, and the sign of `b` decides which way. This is
one of the few types that needs no language, no font ranking and no threshold —
the matrix either is rotated or it is not.
*Carries:* `rotation` in degrees, because a reader cropping the region needs it
and cannot recover it from a rectangle. An angle that was not established is
ABSENT, not `0` — `0` is a claim that the text is upright.
*It is NOT prose.* `arXiv:1909.00741v1 [cs.MM] 2 Sep 2019` belongs to the
archive, not to the paper, and typed `text` it arrived inside the running text
of the section it sits beside.
*MathPix has no name for this;* the name is ours and matches the property
`pdfdrill profile` already reports (`rotated-text`).
*Known defect elsewhere:* pdfdrill's own `chars_to_lines` groups by baseline,
and a rotated run has a different baseline per glyph — so on that reader the
same stamp arrives as SINGLE-CHARACTER lines (`'2'`, `'1'`, `'9'`, `'v'` on
1909.00741), which become single-character paragraphs standing in a column of
their own. The type does not fix that reader; grouping along the rotated axis
would.

**`authors`** — the author block and its affiliation.
*Established by:* the run from the line after the `title` to the first heading
on that page.
*Abstains when the bound is missing:* a front matter with no heading after the
title has no measurable end, and taking "the rest of the page" would swallow
the paper's first section.

**`abstract`** — the abstract body.
*Established by:* the run from the line after a heading that READS as an
abstract label, to the next heading. The label set is `_ABSTRACT_LABELS` —
words a publisher actually prints, in the languages we have met, extended by
adding one rather than by translating.
*The label is not the abstract:* the heading stays `section_header`. A consumer
that wants it gone can drop it; one that needs it back cannot invent it.
*Abstains* with no closing heading, for the same reason `authors` does.

### Specified, not yet measured

These are the types the 1107.2723 failures name. Each states the property that
would establish it; none is implemented, and until one is, its lines stay
`text`.

**`title`** — the document's title.
*Would be established by:* the largest type size on page 1, above the first
`authors` or `abstract` line, and — the part 796 got wrong — **merged across
consecutive lines at that size**. A title on three lines is one title. We
emitted three `Section`s.

**`authors`** — the author block.
*Would be established by:* the lines between `title` and the first `abstract`
or `section_header`, at a size between title and body.
*Contains:* one `text` child per author, which is how MathPix nests it.

**`abstract`** — the abstract body.
*Would be established by:* the block following a `section_header` whose text
matches an abstract label in the document's language, up to the next heading.
*The label is not the abstract:* the heading stays `section_header`.

**`page_info`** — running header, running footer, folio.
*Would be established by:* a line in the top or bottom margin band whose text
repeats across pages, modulo digits. `Signal & Image Processing … Vol.2, No.2,
June 2011` appears on all 16 pages of 1107.2723 and became 16 Paragraphs.
*This is the cheapest one to add and the most visibly wrong today.*

**`list_item`** — one item of a list.
*Would be established by:* a leading bullet or enumerator glyph, or a hanging
indent repeated by its neighbours.
*Contains:* `text` children — MathPix nests 185 such pairs on 1909.00741.

**`barcode`** — a barcode, QR code or similar machine-readable block.
*Would be established by, in order of certainty:*
1. **The content stream.** A barcode drawn by a PostScript library (BWIPP and
   its kin) is a PROCEDURE CALL, and the payload is a literal string argument
   to it — `(9781234567897) (includetext) /ean13 … exec`. `psstream.tokenize`
   already reads operators and their operands, so where the call survives into
   the PDF the payload is read exactly, not decoded. This is the only route
   that returns the true value rather than a best guess, and the user has
   offered a fixture produced this way.
2. A dense cluster of parallel rules of equal height in a small rectangle —
   establishes that a barcode IS there, says nothing about what it says.
3. An image region whose decode succeeds.
*The honest limit of route 1:* a PS-to-PDF step often flattens the procedure to
vector paths, and then the call is gone and only 2 and 3 remain. So the route
is checked, never assumed, and its absence is not evidence that the graphic is
not a barcode.
*It carries no text of its own,* so unlike `rotated_text` it is a GRAPHIC with
a payload.
*Why it matters here:* on the readers that group by baseline it currently
arrives the same way rotated text does — as a column of single-character
fragments — and it is the second half of the same report.

**`footnote`** — the note at the foot of a column. ESTABLISHED (808).
*Established by:* the line sits below the lowest body-size line **in its
column**, and its type size is smaller than the page's modal body size.
*The rule this entry originally demanded is not there.* 2510.04618 draws no
footnote separator — its only rules are the table's, 300pt higher — so a rule
corroborates and is never the evidence. Two things had to be measured rather
than assumed: PER COLUMN, because on a two-column paper the left column's
footnote is not below the right column's last body line (1909.00741 has four and
yielded zero); and the body line's TOP, not its bottom, because the line reader
merges rows and the lowest body line on 2510.04618 page 8 is 28pt tall with its
bottom ABOVE the footnote.
*Tested after `caption`,* because a figure at the foot of a page puts its
caption below the last body line at a smaller size too, and a caption has a
label.

**`figure_label`** / **`caption`** — a figure's number and its caption.
*Would be established by:* a line beginning with a figure/table label in the
document's language, adjacent to a `diagram` or an image region.

**`table`, `table_row`, `table_column`, `simple_cell`, `complex_cell`** — the
table subtree. The largest missing structure: MathPix emits 164 `simple_cell`
on one paper and we emit none.
*Would be established by:* the ruled grid measured at 800 dpi, with
`_cell_split` for the unruled case.
*Nesting is the point:* a table whose cells are not addressable is a rectangle,
not a table, and cannot project to `tabular`.

## Floats are not placed by reading order

`Table`, `Picture`, `Diagram`, `Figure`, `Chart`. LaTeX places these, not the
author: the object can land on another page entirely, so its position in the
text says nothing about its rectangle. Interpolating one produces a box on
whatever prose happened to fill the gap — measured on 2510.04618 page 8, the
Table's box held its caption plus four lines of running prose and not the
tabular grid at all.

No box is worse to look at and better to trust than a wrong one, because a
wrong one cannot be detected downstream: not one of those boxes overlapped
another, so an overlap check saw nothing. The measurement that showed it was
reading the LINES inside each box.

A float's rectangle therefore comes from a measurement or not at all — the drawn
rules and the caption (`table_regions`), or a crop a source lane recorded.

And a caption belongs to its float, not to the prose that follows it: with
floats no longer interpolated, the gap where a table sat fell to the next
paragraph, whose box then began on `Table 2: Results on…`.

## Containment

One parent, by geometry, never by guess.

- A line belongs to the `column` whose bounds its x-range **overlaps most**.
  Overlap, not midpoint: a full-width title straddles both columns and belongs
  to the one it covers most, which is the answer a reader would give.
- A container's rectangle is the **union of its children**, so a reader can
  draw it and check it against the page. A container whose rectangle is
  asserted rather than measured is a label, and labels cannot be falsified.
- Containers are emitted **before** their children, so a one-pass tree builder
  meets a parent before the children it names.
- Depth is currently 1 (`column -> line`). MathPix reaches 2
  (`table -> cell`, `list_item -> text`). We do not invent the second level
  until the types that need it are measured.

## What this specification refuses to do

Guess. Every failure in the table at the top of this document is a line that
got a type it had not earned, because the alternative — leaving it `text` —
felt like doing nothing. It is not doing nothing: `text` is the honest answer
for a line whose kind has not been established, and a `Paragraph` containing a
page number is worse than a paragraph that is missing one, because the first
cannot be detected downstream and the second can.
