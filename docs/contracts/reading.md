# contracts/reading.md — the reading contract (reading/1)

DESTINATION `~/drillgroup/contracts/reading.md`. This copy is pdfdrill's
draft, measured here because the corpus is here; the coordinator reviews it
and commits it to drillgroup, where every reader reads it (T-0107, TOP-03
deliverable 1). `reading-types.json` beside it is the machine-readable type
list, the file glyphdrill's drift test and `pdfdrill lines-check` (T-0109)
read. A reader pins the contract by path, or by a copy plus its sha256 —
never by keeping a private second list.

A reader turns a document into `lines.json` and nothing else (ENGINEERING
2d). This file says what that means, field by field and type by type.

## Reproducing every number here

```
python3 tools/reading-contract/measure.py        # reads the library, writes measured.json
python3 tools/reading-contract/coverage.py       # greps src/, writes coverage.json
python3 tools/reading-contract/gen_contract.py docs/contracts   # this file + the JSON
```

The three scripts are committed, not scratch: a count nobody else can
reproduce is an assertion, and this contract is read by four projects.

Measured 2026-11-02T17:54:23+0100 over `/home/wkolbe/pdfdrill-library`, read only. Nothing in the library was
written. Every count below comes from `measured.json`; none is typed in by
hand.

## 1. The population, and why it is reported per producer

The library holds **5460** `*/*.lines.json` files totalling 6.3 GB. Only
**1441** of them are MathPix readings. The rest are our own readers'
output written in the same shape, and counting them together would produce a
"MathPix contract" that describes pdfdrill's own output back to us — the
same trap that inflated the `.tex` font census twice (T-0107's own note of
2026-10-31).

**The first version of this section fell into that trap itself.** The
coordinator's review of commit `7a6dc1dc` caught it: the rule read `source`
only at the TOP level, so 34 of our own files were filed as
MathPix and their fields and types were reported as MathPix's. §1a records
exactly what moved. Every number in this contract is the corrected
measurement.

| producer                 | files | pages  | lines   | types |
|--------------------------|-------|--------|---------|-------|
| reader:pdfminer-chars    | 3929  | 150495 | 6943846 | 2     |
| mathpix-classic          | 1392  | 65172  | 3664533 | 37    |
| reader:pdfminer-docmodel | 66    | 1347   | 63834   | 19    |
| mathpix-newer            | 49    | 3437   | 155836  | 32    |
| unknown-shape            | 17    | 49     | 560     | 9     |
| reader:visionocr         | 3     | 45     | 2567    | 4     |
| reader:tesseract         | 3     | 21     | 768     | 4     |
| reader:yolo-geometry     | 1     | 1      | 1       | 1     |

MathPix as a whole is therefore **1441 files, 68609 pages,
3820369 lines, 37 types** — split in the table because the two
API vintages carry neither the same fields nor the same container nesting
(§4a).

The producer is taken FROM THE FILE, in this order. Each file records WHICH
rule classified it (`classified_by` in `measured.json`), so the rule is
auditable rather than merely asserted:

1. the top-level `source` field, where a writer sets one — `pdfminer-chars`
   is pdfdrill's glyph reader, and `source` WINS even if MathPix markers are
   also present, because a file our reader wrote is our reader's output
   whatever it copied;
2. otherwise a **page-level** `source`, which is where our writer put it
   before defect 846 moved it to the top, and the only place a merged reading
   can say it carries pages from two readers. 34 files are in this
   shape. If pages disagree the class is `merged:a+b`, never one of them;
3. otherwise a **writer signature** — a key our readers emit and MathPix does
   not: page `px_per_pt`, `diagrams`, `fills`, `links`; line `gaps`, `rules`,
   `deferred_glyphs`, `complete`, `_i`. Ownership was established by reading
   the writer (`docmodel_six.to_lines_json`, lines 4444-4524), not assumed;
4. otherwise `gemma_reader`'s tell — `furniture_retyped` present, or
   `image_id` equal to `""` → `reader:gemma`;
5. otherwise MathPix, split by vintage: a `page_confidence` DICT →
   `mathpix-newer`, else `is_printed`/`confidence` on a line →
   `mathpix-classic`;
6. otherwise `unknown-shape`, counted and listed, never folded into MathPix.

**`is_printed` and `confidence` do not prove MathPix.** Rule 5 reaches them
only after rules 1-4 have ruled our own writers out, because
`docmodel_six.to_lines_json` emits `is_printed: True`, `confidence`,
`confidence_rate`, `cnt` and `conversion_output` ON PURPOSE — its own comment
says "MathPix's own page keys first, so a consumer written against their
export reads ours unchanged". A shape test against a format built to be
copied can only fail.

**17 files name no producer at all**, and they are listed by name
in `measured.json` so they can be dealt with one by one: four `scan_*`, three
`loc*_slides`, two `overlay-*`, two `Qwen_postscript_*`, one
`deepseek_postscript_*`, `escher_complex`, `eschertest.dvi`, `flattened`,
`kp_output`, `5990011_W`.

A CORRECTION TO THE FIELD REPORT THAT PROMPTED THIS SECTION. glyphdrill2
reported `arxiv.1411.2995`, `arxiv.0704.2889` and `2403.14252v1` as
"look-alikes with no producer named". They are look-alikes — `image_id` is
null, `page_width` is in POINTS (612.0, 612.0, 595.28), and there is no
`cnt` and no `confidence` — but all three DO name their producer: each
carries top-level `source: "pdfminer-chars"` plus `math_lines_typed`
(42, 109, 0). They are pdfdrill's own glyph reader, correctly labelled, and
this contract's rule 1 classifies them from that field without ever looking
at their shape. The danger they illustrate is real and it is the other way
round: a consumer that decides MathPix-or-not by SHAPE would read them as
MathPix and then read points as pixels, every box out by 3.47x. Decide by
the declared producer, never by the shape.

Every reader from now on records its producer (T-0045 rule 5), so
`unknown-shape` should shrink to zero and never grow.

Note `reader:tesseract` (3 files): pdfdrill runs no OCR engine and installs
none (`tests/test_no_ocr_engine.py` enforces it). Those files predate that
rule; they are data in the library, not a live route.

## 1a. What the corrected rule moved, and what it invalidated

The first measurement classified by top-level `source` or else by shape.
34 files of ours declare `source` on each PAGE only — the shape our
writer used before defect 846 moved the key to the top — so all 34
were filed as MathPix. They are, by name:

> 2405.08011v1
> Axiomatizing_the_Logic_of_Comparative_Probability__Gärdenfors_2010
> On_the_extensions_of_S5__Gärdenfors_1973, SDU_test, arxiv.1102.1889
> dml-2011-baker-sexton-sorge, s41467-023-39995-0, s41467-024-47221-8
> s41467-024-54178-1, s41586-022-04731-z, s41598-023-32128-z
> s42005-020-0326-2, s42532-023-00153-x, sciadv.aax7163
> and sigma26-073 ... sigma26-092 (20 files).

Every one carries page-level `source: "pdfminer-docmodel"`, so they were never
ambiguous: the rule did not look where the answer was. The defect-846 comment
in `docmodel_six.py` records inkdrill hitting this same failure ("every
reading of ours looked like MathPix to it"), and this measurement reproduced
it. §1's own closing line already said *decide by the declared producer,
never by the shape*; rule 2 of the old list did the opposite.

What moved out of MathPix: **803 pages and 32991
lines**, leaving MathPix at 1441 files / 68609 pages /
3820369 lines.

Three consequences, each invalidating something the contract had stated:

**1. Four of the 41 "MathPix types" are not MathPix types.** `caption`,
`equation`, `formula` and `rotated_text` occur in NO MathPix file in the
library. They came entirely from those 34 files, in pdfdrill's
INTERNAL vocabulary, because those files also predate defect 844 — the commit
that added `_mp_type`, the translation from our type names into MathPix's. The
real MathPix vocabulary is **37 types**. `_mp_type`'s own docstring
says so for two of them: *"MathPix emits no `equation` at all"*, and `formula`
maps to `text`.

**2. One type name means opposite things on the two sides, and the old table
summed them.** Ours `math` = PROSE carrying inline maths; MathPix `math` =
DISPLAY maths. The old §6 row for `math` added 9093 of our lines to
MathPix's 117039. Defect 844 exists because that collision already cost
`inlinectx.load_spans` 79.2% of its inline spans; a contract that sums the
two re-creates the defect at the documentation level.

**3. Sixteen fields in §4/§5 were ours.** Page: `px_per_pt`, `source`,
`diagrams`, `fills`, `links`. Line: `complete`, `gaps`, `rules`,
`deferred_glyphs`, `_i`, `level`, `rotation`, `label`, `number`, `caption_id`,
`caption_number`. The review named five of the line fields; the other six had
the same cause and were in the same table.

Also corrected in passing: the first draft called `formula` "a CHEMICAL
formula, not mathematics", reasoning from `molecule` nearby. It is neither.
`_mp_type`'s docstring records what those 166 lines are — a glyph
run in a maths font that survived classification, e.g. an author line misread
as "Josef $\mathrm{Ba}\ker$ , Alan Sexton and $\mathrm{Vol}\ker$ Sorge".

The general rule, of which this is the second instance (§8's coverage finding
is the first): **a grep names who CAN write a field, never who DID.**
Ownership comes from reading the writer, or from the file declaring itself.

## 2. The pixel space — 250 dpi, and that is where PX_PER_PT comes from

`region` and `cnt` are in PIXELS of the raster named by `image_id`, not in
points. Measured on 30 MathPix documents, comparing `page_width`/
`page_height` against the PDF's own MediaBox from `pdfinfo`:

```
x ratio  median 3.4722  min 3.4722  max 3.4725
y ratio  median 3.4722  min 3.4722  max 3.4731
         3.4722 x 72 = 250.0 dpi exactly
```

30 of 30, both axes. So `PX_PER_PT = 3.4722222222222223` in
`pdfdrill.report_tex` is not a magic constant: it is 250/72, the dpi MathPix
rasterises at. `font_size` is in the same pixel space (a 10 pt body face
reads 36 px: 36 / 3.4722 = 10.4 pt).

A reader that emits points instead must say so in its own fields — that is
exactly what the three look-alikes above do, and it is why they are
unreadable by a consumer expecting pixels.

## 3. File-level fields

MathPix readings carry **no** file-level fields at all: the top level is
`{"pages": [...]}`. Every file-level key seen in the library belongs to a
reader:

| producer                 | file-level keys                                      |
|--------------------------|------------------------------------------------------|
| reader:pdfminer-chars    | source (3929), math_lines_typed (3929)               |
| mathpix-classic          | -                                                    |
| reader:pdfminer-docmodel | source (32)                                          |
| mathpix-newer            | -                                                    |
| unknown-shape            | -                                                    |
| reader:visionocr         | source (3), math_lines_typed (3)                     |
| reader:tesseract         | source (3), ocr (2)                                  |
| reader:yolo-geometry     | source (1), geometry_only (1), ocr (1), sanitize (1) |

Both MathPix classes carry nothing at the top level, which is why a top-level
`source` is a safe producer test in ONE DIRECTION ONLY: its presence proves a
reader, its absence proves nothing. **32 of the 66
`pdfminer-docmodel` files declare `source` at the top; the other
34 declare it per page** (§1a). A consumer reading only the top
level misreads those 34 as MathPix — which is what `cmd_ocr`'s
backup guard did (defect 846), and what this contract's first draft did.

## 4. Page fields

Per class, because the two vintages do not carry the same page fields. Only
fields MathPix writes appear here; the five the first draft listed
(`px_per_pt`, `source`, `diagrams`, `fills`, `links`) were ours, on
803 pages, and are gone (§1a).

**mathpix-classic** — 1392 files, 65172 pages:

| page field         | pages | share  |
|--------------------|-------|--------|
| image_id           | 65172 | 100.0% |
| page               | 65172 | 100.0% |
| page_height        | 65172 | 100.0% |
| page_width         | 65172 | 100.0% |
| languages_detected | 64768 | 99.4%  |

Five fields, and that is all: a classic page carries no confidence of its own.

**mathpix-newer** — 49 files, 3437 pages:

| page field         | pages | share  |
|--------------------|-------|--------|
| image_id           | 3437  | 100.0% |
| page               | 3437  | 100.0% |
| page_height        | 3437  | 100.0% |
| page_width         | 3437  | 100.0% |
| languages_detected | 3411  | 99.2%  |
| parse_status       | 3411  | 99.2%  |
| fallback_count     | 3411  | 99.2%  |
| page_confidence    | 3411  | 99.2%  |

## 4a. The two API vintages, and why the split is not cosmetic

**`parse_status`, `fallback_count` and `page_confidence` are GENUINE MathPix
fields**, from the newer API. glyphdrill2 reported seeing `parse_status` in a
real MathPix file and was right. The evidence is in the files, on all
49:

| discriminator       | mathpix-newer                                  | our `gemma_reader`  |
|---------------------|------------------------------------------------|---------------------|
| `image_id`          | real UUID + page suffix, e.g. `...-2651ee-01`  | `""`                |
| `page_confidence`   | dict, `method: "prototype_min_v1"`             | `None`              |
| `furniture_retyped` | absent                                         | always present      |
| line fields         | `text_confidence`, `layout_confidence` on 100% | neither             |

A grep is what made this look like ours: `gemma_reader.py` does write all
three names, because it mimics MathPix's shape like everything else here.
**It names who can write the field, not who did.** These files are MathPix.

Two differences a consumer must handle, not merely note:

1. **The newer API emits no `table_row` and no `table_column`.** Classic
   nests `table > table_row` (159000 lines) and `table > table_column`
   (48950); newer has 704 `table` lines over 34
   documents and **zero** of either, going `table > simple_cell`
   (20050) directly. Code that walks a table by its rows finds nothing
   in a newer reading and reports an empty table, not an error.
2. **Confidence moved onto every line.** `confidence` is on 89.6% of
   classic lines and 100.0% of newer ones, and newer adds
   `text_confidence` and `layout_confidence` on 100%. A threshold tuned on
   one vintage does not transfer.

Neither vintage is declared in the file. The only way to tell them apart is
`page_confidence` being a dict, which is what the producer rule tests.

## 5. Line fields

Per class again, and ours removed. The first draft's table mixed in eleven
fields of ours — `complete`, `gaps`, `rules`, `deferred_glyphs`, `_i`,
`level`, `rotation`, `label`, `number`, `caption_id`, `caption_number` — all
from the 34 files of §1a.

**mathpix-classic** — 3664533 lines:

| line field        | lines   | share  |
|-------------------|---------|--------|
| cnt               | 3664533 | 100.0% |
| region            | 3664533 | 100.0% |
| line              | 3664533 | 100.0% |
| column            | 3664533 | 100.0% |
| font_size         | 3664533 | 100.0% |
| is_printed        | 3664533 | 100.0% |
| is_handwritten    | 3664533 | 100.0% |
| id                | 3664533 | 100.0% |
| type              | 3664533 | 100.0% |
| conversion_output | 3664533 | 100.0% |
| text              | 3664533 | 100.0% |
| text_display      | 3664533 | 100.0% |
| confidence        | 3282310 | 89.6%  |
| confidence_rate   | 3282310 | 89.6%  |
| parent_id         | 2110174 | 57.6%  |
| subtype           | 1326646 | 36.2%  |
| cell_column       | 776670  | 21.2%  |
| cell_col_span     | 776670  | 21.2%  |
| cell_row          | 776665  | 21.2%  |
| cell_row_span     | 776665  | 21.2%  |
| children_ids      | 187788  | 5.1%   |
| selected_labels   | 64265   | 1.8%   |

**mathpix-newer** — 155836 lines:

| line field        | lines  | share  |
|-------------------|--------|--------|
| cnt               | 155836 | 100.0% |
| region            | 155836 | 100.0% |
| line              | 155836 | 100.0% |
| column            | 155836 | 100.0% |
| font_size         | 155836 | 100.0% |
| is_printed        | 155836 | 100.0% |
| is_handwritten    | 155836 | 100.0% |
| id                | 155836 | 100.0% |
| type              | 155836 | 100.0% |
| conversion_output | 155836 | 100.0% |
| text              | 155836 | 100.0% |
| text_display      | 155836 | 100.0% |
| confidence        | 155836 | 100.0% |
| text_confidence   | 155836 | 100.0% |
| layout_confidence | 155836 | 100.0% |
| parse_status      | 149028 | 95.6%  |
| confidence_rate   | 148435 | 95.3%  |
| subtype           | 84947  | 54.5%  |
| parent_id         | 58115  | 37.3%  |
| cell_row          | 20968  | 13.5%  |
| cell_column       | 20968  | 13.5%  |
| cell_row_span     | 20968  | 13.5%  |
| cell_col_span     | 20968  | 13.5%  |
| children_ids      | 6898   | 4.4%   |
| selected_labels   | 1336   | 0.9%   |

`cnt` is a four-point polygon `[[x,y],[x,y],[x,y],[x,y]]` in the pixel space
of §2; `region` is the same box as `{top_left_x, top_left_y, width, height}`.
Both are present on every line. `line` is a 1-based running index within the
page and `column` a 0-based column number.

`conversion_output` is a boolean and it is NOT a quality flag: it is false on
CONTAINER lines, whose own `text` is empty and whose children carry the
content (`authors`, `abstract`), and true on the lines that contribute text.

**`conversion_output` does NOT explain where `confidence` is missing.** The
first draft of this contract said it did — that the field is absent "on
exactly those containers", which is why its share sits near 90%. Measured
over all 3664533 classic lines (`probe_confidence.py`), that is false:

```
confidence missing            382223 of 3664533   (10.43%)
conversion_output false       1511726
   ... and confidence PRESENT 1160555   (76.8% of them)
conversion_output true
   ... and confidence ABSENT  31052
```

So three quarters of the lines the claim called "exactly those containers"
carry the field, and 31052 lines carry no confidence despite contributing
text. The absence is instead strongly TYPE-bound, and for some types
categorical:

| type                  | no confidence | lines  | share  |
|-----------------------|---------------|--------|--------|
| table_row             | 159008        | 159008 | 100.0% |
| list_item             | 56890         | 84896  | 67.0%  |
| table_column          | 48954         | 48954  | 100.0% |
| diagram               | 26395         | 26401  | 100.0% |
| table_of_contents_row | 18770         | 18770  | 100.0% |
| column                | 16619         | 16619  | 100.0% |
| figure_label          | 10183         | 24120  | 42.2%  |
| table_spanning_cell   | 10097         | 10097  | 100.0% |
| section_header        | 9890          | 46447  | 21.3%  |
| qed_symbol            | 9048          | 9048   | 100.0% |
| footnote              | 3857          | 5045   | 76.5%  |
| page_info             | 2852          | 124562 | 2.3%   |
| chart                 | 2316          | 2316   | 100.0% |
| authors               | 1703          | 2105   | 80.9%  |

A type at 100% never carries confidence; `list_item`, `footnote`, `authors`,
`figure_label` and `section_header` carry it on some lines and not others
within the same type. **No mechanism is offered here.** What a consumer may
rely on is only this: `confidence` may be absent on any line, its absence is
not predictable from `conversion_output`, and code must treat it as optional
rather than defaulting a missing value to 0.0 or to 1.0.

In `mathpix-newer` the question does not arise: `confidence` is on
100.0% of lines, with `text_confidence` and `layout_confidence`
beside it.

**Confidence is not a correctness signal.** MathPix gives 1.0 to fragments
and to CJK misreads (GLYPHDRILL2 T-0113). The only proven signals are
inkdrill's confirmed distance 0 and the author's own LaTeX.

## 6. The type vocabulary

| type                        | lines   | docs | parent(s)                                                                                                                                                                                                                                                               | coverage      | meaning                                                                        |
|-----------------------------|---------|------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------|--------------------------------------------------------------------------------|
| text                        | 2153705 | 1425 | abstract,authors,chart,column,complex_cell,diagram,figure_label,footnote,form_field,list_item,multiple_choice_block,multiple_choice_option,page_info,quote,rotated_container,section_header,table_of_contents_container,table_of_contents_row,table_spanning_cell,title | read          | a run of prose on one baseline; the workhorse type                             |
| simple_cell                 | 749810  | 782  | diagram,table,table_spanning_cell,table_split_cell                                                                                                                                                                                                                      | read          | one table cell with a single value                                             |
| table_row                   | 159008  | 750  | table                                                                                                                                                                                                                                                                   | read          | a row container; its children are the cells                                    |
| page_info                   | 130402  | 1349 | column,diagram,rotated_container                                                                                                                                                                                                                                        | read          | running head, folio, arXiv stamp -- page furniture, not content                |
| math                        | 117039  | 1128 | abstract,column,complex_cell,diagram,figure_label,footnote,list_item,multiple_choice_block,multiple_choice_option,page_info,quote,rotated_container                                                                                                                     | read          | a display or inline equation, text carrying the LaTeX in the dialect below     |
| list_item                   | 88275   | 1005 | abstract,column,complex_cell,diagram,figure_label,footnote,list_item,multiple_choice_block,multiple_choice_option,rotated_container                                                                                                                                     | read          | one item of an enumerated or bulleted list                                     |
| code                        | 51160   | 251  | chart,column,diagram,list_item                                                                                                                                                                                                                                          | read          | a line of a verbatim/listing environment                                       |
| equation_number             | 50597   | 849  | column,complex_cell,diagram,figure_label,footnote,list_item,page_info                                                                                                                                                                                                   | read          | the tag beside a numbered equation, e.g. (3.14)                                |
| table_column                | 48954   | 750  | table                                                                                                                                                                                                                                                                   | read          | a column container; a second grouping over the same cells                      |
| section_header              | 47960   | 1323 | abstract,column,diagram,figure_label,footnote,list_item,page_info,section_header                                                                                                                                                                                        | read          | a heading at any level; level, when present, says which                        |
| complex_cell                | 36377   | 511  | table,table_spanning_cell,table_split_cell                                                                                                                                                                                                                              | read          | a table cell whose content is itself structured (list, equation, nested table) |
| diagram                     | 27616   | 1039 | abstract,column,complex_cell,diagram,figure_label,footnote,list_item,multiple_choice_block,multiple_choice_option,page_info,rotated_container,section_header,table_spanning_cell                                                                                        | read          | a region MathPix read as a drawing rather than text                            |
| figure_label                | 24769   | 1002 | chart,column,complex_cell,diagram,figure_label,footnote,list_item,multiple_choice_option,page_info,rotated_container,section_header                                                                                                                                     | read          | the 'Figure 3' label of a figure, separate from its caption                    |
| table_of_contents_item      | 22104   | 174  | diagram,table_of_contents_container,table_of_contents_row                                                                                                                                                                                                               | read          | the title part of a TOC row                                                    |
| table_of_contents_row       | 19791   | 174  | column,table_of_contents_container,table_of_contents_row                                                                                                                                                                                                                | read          | one TOC row; children are the item and the number                              |
| table_of_contents_number    | 19130   | 173  | list_item,table_of_contents_row                                                                                                                                                                                                                                         | read          | the page number part of a TOC row                                              |
| column                      | 17234   | 731  | abstract,authors,chart,column,complex_cell,diagram,figure_label,footnote,list_item,multiple_choice_block,page_info,rotated_container,section_header,table_of_contents_container                                                                                         | read          | a page-column container                                                        |
| table                       | 12340   | 799  | column,complex_cell,diagram,figure_label,list_item,multiple_choice_option,page_info,rotated_container,table_spanning_cell                                                                                                                                               | read          | the table container; children are rows and columns                             |
| qed_symbol                  | 10236   | 247  | column,footnote,list_item                                                                                                                                                                                                                                               | read          | the end-of-proof mark                                                          |
| table_spanning_cell         | 10126   | 474  | column,diagram,table,table_spanning_cell                                                                                                                                                                                                                                | read          | a cell spanning several columns or rows (cell_col_span / cell_row_span)        |
| pseudocode                  | 7883    | 213  | diagram                                                                                                                                                                                                                                                                 | read          | a line of an algorithm environment; pdfdrill has NO algorithm object (T-0120)  |
| footnote                    | 5520    | 813  | column,figure_label,footnote,list_item,rotated_container,table_of_contents_row                                                                                                                                                                                          | read          | a footnote body at the foot of the page                                        |
| chart                       | 2365    | 427  | chart,column,complex_cell,diagram,figure_label,footnote,list_item,multiple_choice_option,page_info,rotated_container,table_of_contents_container                                                                                                                        | read          | a region read as a chart; subtype carries the analytical kind                  |
| authors                     | 2165    | 1071 | authors,column,diagram                                                                                                                                                                                                                                                  | read          | the author block container; its children carry the names                       |
| title                       | 1890    | 1093 | column                                                                                                                                                                                                                                                                  | read          | the document title                                                             |
| abstract                    | 1072    | 873  | column                                                                                                                                                                                                                                                                  | read          | the abstract container; its children carry the prose                           |
| table_of_contents_container | 744     | 172  | column,table_of_contents_row                                                                                                                                                                                                                                            | read          | the TOC block; children are rows                                               |
| form_field                  | 722     | 58   | column,complex_cell,diagram,figure_label,list_item,multiple_choice_block,multiple_choice_option                                                                                                                                                                         | DECLARED ONLY | a fillable form field                                                          |
| quote                       | 483     | 114  | column,complex_cell                                                                                                                                                                                                                                                     | read          | a block quotation                                                              |
| multiple_choice_block       | 457     | 26   | column,list_item,multiple_choice_option                                                                                                                                                                                                                                 | DECLARED ONLY | a multiple-choice question block                                               |
| rotated_container           | 161     | 25   | column                                                                                                                                                                                                                                                                  | DECLARED ONLY | a container for sideways material                                              |
| multiple_choice_option      | 125     | 12   | list_item,multiple_choice_block,multiple_choice_option                                                                                                                                                                                                                  | DECLARED ONLY | one option of such a block                                                     |
| icon                        | 108     | 27   | column,diagram,page_info                                                                                                                                                                                                                                                | DECLARED ONLY | a small pictogram                                                              |
| table_split_cell            | 22      | 10   | table                                                                                                                                                                                                                                                                   | read          | a cell continued across a page or column break                                 |
| molecule                    | 11      | 5    | diagram                                                                                                                                                                                                                                                                 | read          | a chemical structure region                                                    |
| diagram_info                | 7       | 2    | diagram                                                                                                                                                                                                                                                                 | DECLARED ONLY | metadata emitted beside a diagram                                              |
| x_axis_tick_label           | 1       | 1    | -                                                                                                                                                                                                                                                                       | DECLARED ONLY | one tick label of a chart axis                                                 |

### Containers and children, as measured

`parent_id` points at the container; `children_ids` lists the other
direction. The pairs actually present in the corpus:

| parent                      | child                    | lines  |
|-----------------------------|--------------------------|--------|
| table                       | simple_cell              | 741004 |
| column                      | text                     | 510390 |
| list_item                   | text                     | 177205 |
| complex_cell                | text                     | 160228 |
| table                       | table_row                | 159000 |
| diagram                     | code                     | 50327  |
| table                       | table_column             | 48950  |
| figure_label                | text                     | 39941  |
| table                       | complex_cell             | 35563  |
| column                      | list_item                | 22158  |
| table_of_contents_row       | table_of_contents_item   | 22076  |
| table_of_contents_row       | table_of_contents_number | 19127  |
| table_of_contents_container | table_of_contents_row    | 18965  |
| footnote                    | text                     | 18547  |
| abstract                    | text                     | 15630  |
| section_header              | text                     | 13821  |
| column                      | section_header           | 13123  |
| page_info                   | text                     | 10765  |
| table                       | table_spanning_cell      | 10117  |
| table_spanning_cell         | simple_cell              | 8771   |
| list_item                   | math                     | 7992   |
| column                      | math                     | 7964   |
| diagram                     | pseudocode               | 7883   |
| authors                     | text                     | 7299   |
| column                      | equation_number          | 4754   |

### Subtypes

| type        | subtype                  | lines   |
|-------------|--------------------------|---------|
| text        | continues_line_space     | 1061387 |
| text        | continues_line_newline   | 177035  |
| text        | continues_line_no_hyphen | 153347  |
| text        | continues_line_no_space  | 7625    |
| diagram     | algorithm                | 6931    |
| page_info   | margin_note              | 2144    |
| chart       | line                     | 1085    |
| diagram     | pseudocode               | 614     |
| chart       | analytical               | 489     |
| chart       | column                   | 348     |
| chart       | scatter                  | 280     |
| chart       | bar                      | 70      |
| form_field  | checkbox                 | 58      |
| form_field  | box                      | 36      |
| text        | big_capital_letter       | 32      |
| diagram     | triangle                 | 22      |
| form_field  | dotted                   | 18      |
| page_info   | qr_code                  | 18      |
| diagram     | chemistry                | 16      |
| diagram     | chemistry_reaction       | 12      |
| form_field  | parentheses              | 6       |
| form_field  | dashed                   | 6       |
| simple_cell | vertical                 | 5       |
| chart       | area                     | 4       |
| diagram     | logo                     | 2       |

**This table counts MathPix files only.** `caption`, `equation`, `formula`
and `rotated_text` are absent from it on purpose: no MathPix file in the
library carries them (§1a). Mathematics is `math`, and `math` ALONE —
MathPix emits no `equation` at all, which is what `_mp_type` exists to
translate. A reader that expects an `equation` type from MathPix will find
none in 1441 files.

`molecule` (11 lines) is a chemical structure region and has no
`formula` companion in MathPix's vocabulary.

## 7. The text dialect

`text` carries LaTeX inline, in exactly two delimiters:

- `\( ... \)` for inline mathematics;
- `\[ ... \]` for display mathematics, newline-separated from its content.

`text_display` carries the same content with the document's own LaTeX
structure around it (`\title{...}`, `\author{...}`) and leading newlines;
it is a presentation string, not a parse target. A dollar sign in prose
arrives escaped as `\$`.

## 8. Coverage — who reads each type

Every one of the 37 types is named somewhere in `src/`, but a mention
in `type_contract.py` or `line_types.py` is a DECLARATION, not a reader.
Excluding those two list modules, **7 types have no reader at
all**, carrying 1581 lines between them:

- `form_field` — a fillable form field
- `multiple_choice_block` — a multiple-choice question block
- `rotated_container` — a container for sideways material
- `multiple_choice_option` — one option of such a block
- `icon` — a small pictogram
- `diagram_info` — metadata emitted beside a diagram
- `x_axis_tick_label` — one tick label of a chart axis

That is the gap this contract exists to make visible, and
`tests/test_the_reading_contract_covers_every_type.py` fails if a type is
neither read nor listed here as dropped — so a new MathPix type cannot
vanish silently.

### Drift against pdfdrill's own declaration

`docmodel/type_contract.py` declares **38** line types in its
CLAIMED and IGNORED maps. Measured against this contract:

- declared by pdfdrill but NOT a MathPix type: `rotated_text`
- a MathPix type but NOT declared by pdfdrill: none

**The second list is empty: pdfdrill declares every one of MathPix's
37 types.** That is the direction that would hurt, and there is no
drift in it.

The first list is not drift either, and the first version of this section got
that wrong. `rotated_text` is pdfdrill's OWN type, emitted by our reader
(414 lines) and absent from every MathPix file in the library.
Two vocabularies meet here, and comparing them as one list produces a gate
that fails on a correct declaration — so the contract records the boundary
instead: `reading-types.json` carries `pdfdrill_only_types` beside `types`,
and `reading_contract.pdfdrill_only_types()` returns it. The drift test
checks that pdfdrill's declaration is covered by the UNION, so a genuinely
new name still fails it.

(The first draft also named `caption`, `equation` and `formula` here as
undeclared MathPix types and warned that `formula` was chemistry. All three
are pdfdrill-internal names from pre-844 files, `type_contract` declares none
of them, and `formula` is a misread author line — see §1a.)

## 9. The shared vocabulary, for every reader

glyphdrill, pdf2mmd2 and Gemma emit THE SAME type names as MathPix. A reader
emits a SUBSET and states which subset in its own output; it never invents a
name that means something MathPix already names. Measured today, pdfdrill's
own glyph reader emits **2** of the 37 (`text`, `math`) over
6943846 lines — which is the whole of the keyless lane's structural
poverty in one number, and the reason the twenty modules that build Table,
Diagram, CodeListing and Section have nothing to work with on that route.

## 10. What is NOT established

- The MEANING column is written from the measured examples and from the
  module that reads each type. For the 7 declared-only types
  there is no reader to check against, so those meanings are inferred from
  the name and the example line, and are marked here rather than in the JSON.
- `conversion_output`'s rule is stated for containers versus content lines.
  It does NOT explain `confidence`'s absence; §5 records the measurement that
  refuted that, and no mechanism is offered in its place.
- **Producer classification rests on declared fields and markers. A file
  carrying neither is `unknown-shape`** (17 files), and is counted
  and listed, never assigned. The signature lists in rule 3 were read off
  `docmodel_six.to_lines_json` on 2026-11-02; a writer that gains a field
  later makes that list stale, and the classifier will fall through to rule 5
  and call the file MathPix. The list is a snapshot of one writer, not a
  closed set.
- The two API vintages are inferred from `page_confidence`'s type, not from
  anything MathPix declares. A third vintage, or a newer file with no
  `page_confidence`, would be classed `mathpix-classic` and silently widen
  that class.
- No claim is made about MathPix's own versioning: the contract describes
  what the library holds, not what the API will return tomorrow.
