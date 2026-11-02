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

Measured 2026-11-02T15:08:30+0100 over `/home/wkolbe/pdfdrill-library`, read only. Nothing in the library was
written. Every count below comes from `measured.json`; none is typed in by
hand.

## 1. The population, and why it is reported per producer

The library holds **5460** `*/*.lines.json` files totalling 6.3 GB. Only
**1475** of them are MathPix readings. The rest are our own readers'
output written in the same shape, and counting them together would produce a
"MathPix contract" that describes pdfdrill's own output back to us — the
same trap that inflated the `.tex` font census twice (T-0107's own note of
2026-10-31).

| producer                 | files | pages  | lines   | types |
|--------------------------|-------|--------|---------|-------|
| reader:pdfminer-chars    | 3929  | 150495 | 6943846 | 2     |
| mathpix                  | 1475  | 69412  | 3853360 | 41    |
| reader:pdfminer-docmodel | 32    | 544    | 30843   | 16    |
| unknown-shape            | 17    | 49     | 560     | 9     |
| reader:visionocr         | 3     | 45     | 2567    | 4     |
| reader:tesseract         | 3     | 21     | 768     | 4     |
| reader:yolo-geometry     | 1     | 1      | 1       | 1     |

The producer is taken FROM THE FILE, in this order:

1. the top-level `source` field, where a writer sets one — `pdfminer-chars`
   is pdfdrill's glyph reader, and `source` WINS even if MathPix markers are
   also present, because a file our reader wrote is our reader's output
   whatever it copied;
2. otherwise `is_printed` or `confidence` on a line, which MathPix sets and
   our readers do not → `mathpix`;
3. otherwise `unknown-shape`, counted and listed, never folded into MathPix.

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
| mathpix                  | -                                                    |
| reader:pdfminer-docmodel | source (32)                                          |
| unknown-shape            | -                                                    |
| reader:visionocr         | source (3), math_lines_typed (3)                     |
| reader:tesseract         | source (3), ocr (2)                                  |
| reader:yolo-geometry     | source (1), geometry_only (1), ocr (1), sanitize (1) |

## 4. Page fields

| page field         | pages | share  |
|--------------------|-------|--------|
| image_id           | 69412 | 100.0% |
| page               | 69412 | 100.0% |
| page_height        | 69412 | 100.0% |
| page_width         | 69412 | 100.0% |
| languages_detected | 68982 | 99.4%  |
| parse_status       | 3411  | 4.9%   |
| fallback_count     | 3411  | 4.9%   |
| page_confidence    | 3411  | 4.9%   |
| px_per_pt          | 803   | 1.2%   |
| source             | 803   | 1.2%   |
| diagrams           | 803   | 1.2%   |
| fills              | 803   | 1.2%   |
| links              | 803   | 1.2%   |

## 5. Line fields

| line field        | lines   | share  |
|-------------------|---------|--------|
| cnt               | 3853360 | 100.0% |
| region            | 3853360 | 100.0% |
| line              | 3853360 | 100.0% |
| font_size         | 3853360 | 100.0% |
| is_printed        | 3853360 | 100.0% |
| is_handwritten    | 3853360 | 100.0% |
| id                | 3853360 | 100.0% |
| type              | 3853360 | 100.0% |
| conversion_output | 3853360 | 100.0% |
| text              | 3853360 | 100.0% |
| column            | 3853339 | 100.0% |
| text_display      | 3849565 | 99.9%  |
| confidence        | 3471137 | 90.1%  |
| confidence_rate   | 3463736 | 89.9%  |
| parent_id         | 2199816 | 57.1%  |
| subtype           | 1411593 | 36.6%  |
| cell_column       | 797638  | 20.7%  |
| cell_col_span     | 797638  | 20.7%  |
| cell_row          | 797633  | 20.7%  |
| cell_row_span     | 797633  | 20.7%  |
| children_ids      | 195514  | 5.1%   |
| text_confidence   | 155836  | 4.0%   |
| layout_confidence | 155836  | 4.0%   |
| parse_status      | 149028  | 3.9%   |
| selected_labels   | 65601   | 1.7%   |
| complete          | 32163   | 0.8%   |
| gaps              | 32158   | 0.8%   |
| rules             | 32158   | 0.8%   |
| deferred_glyphs   | 32158   | 0.8%   |
| _i                | 31527   | 0.8%   |
| level             | 432     | 0.0%   |
| rotation          | 118     | 0.0%   |
| label             | 110     | 0.0%   |
| number            | 110     | 0.0%   |
| caption_id        | 21      | 0.0%   |
| caption_number    | 21      | 0.0%   |

`cnt` is a four-point polygon `[[x,y],[x,y],[x,y],[x,y]]` in the pixel space
of §2; `region` is the same box as `{top_left_x, top_left_y, width, height}`.
Both are present on every line. `line` is a 1-based running index within the
page and `column` a 0-based column number.

`conversion_output` is a boolean and it is NOT a quality flag: it is false on
CONTAINER lines, whose own `text` is empty and whose children carry the
content (`authors`, `abstract`), and true on the lines that contribute text.
`confidence` and `confidence_rate` are absent on exactly those containers,
which is why their presence share is ~90% rather than 100%.

**Confidence is not a correctness signal.** MathPix gives 1.0 to fragments
and to CJK misreads (GLYPHDRILL2 T-0113). The only proven signals are
inkdrill's confirmed distance 0 and the author's own LaTeX.

## 6. The type vocabulary

| type                        | lines   | docs | parent(s)                                                                                                                                                                                                                                                               | coverage      | meaning                                                                                                             |
|-----------------------------|---------|------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------|---------------------------------------------------------------------------------------------------------------------|
| text                        | 2178196 | 1459 | abstract,authors,chart,column,complex_cell,diagram,figure_label,footnote,form_field,list_item,multiple_choice_block,multiple_choice_option,page_info,quote,rotated_container,section_header,table_of_contents_container,table_of_contents_row,table_spanning_cell,title | read          | a run of prose on one baseline; the workhorse type                                                                  |
| simple_cell                 | 749810  | 782  | diagram,table,table_spanning_cell,table_split_cell                                                                                                                                                                                                                      | read          | one table cell with a single value                                                                                  |
| table_row                   | 159008  | 750  | table                                                                                                                                                                                                                                                                   | read          | a row container; its children are the cells                                                                         |
| page_info                   | 130890  | 1378 | column,diagram,rotated_container                                                                                                                                                                                                                                        | read          | running head, folio, arXiv stamp -- page furniture, not content                                                     |
| math                        | 122616  | 1157 | abstract,column,complex_cell,diagram,figure_label,footnote,list_item,multiple_choice_block,multiple_choice_option,page_info,quote,rotated_container                                                                                                                     | read          | a display or inline equation, text carrying the LaTeX in the dialect below                                          |
| list_item                   | 88275   | 1005 | abstract,column,complex_cell,diagram,figure_label,footnote,list_item,multiple_choice_block,multiple_choice_option,rotated_container                                                                                                                                     | read          | one item of an enumerated or bulleted list                                                                          |
| code                        | 51162   | 252  | chart,column,diagram,list_item                                                                                                                                                                                                                                          | read          | a line of a verbatim/listing environment                                                                            |
| equation_number             | 50597   | 849  | column,complex_cell,diagram,figure_label,footnote,list_item,page_info                                                                                                                                                                                                   | read          | the tag beside a numbered equation, e.g. (3.14)                                                                     |
| table_column                | 48954   | 750  | table                                                                                                                                                                                                                                                                   | read          | a column container; a second grouping over the same cells                                                           |
| section_header              | 48392   | 1351 | abstract,column,diagram,figure_label,footnote,list_item,page_info,section_header                                                                                                                                                                                        | read          | a heading at any level; level, when present, says which                                                             |
| complex_cell                | 36377   | 511  | table,table_spanning_cell,table_split_cell                                                                                                                                                                                                                              | read          | a table cell whose content is itself structured (list, equation, nested table)                                      |
| diagram                     | 27616   | 1039 | abstract,column,complex_cell,diagram,figure_label,footnote,list_item,multiple_choice_block,multiple_choice_option,page_info,rotated_container,section_header,table_spanning_cell                                                                                        | read          | a region MathPix read as a drawing rather than text                                                                 |
| figure_label                | 24874   | 1017 | chart,column,complex_cell,diagram,figure_label,footnote,list_item,multiple_choice_option,page_info,rotated_container,section_header                                                                                                                                     | read          | the 'Figure 3' label of a figure, separate from its caption                                                         |
| table_of_contents_item      | 22104   | 174  | diagram,table_of_contents_container,table_of_contents_row                                                                                                                                                                                                               | read          | the title part of a TOC row                                                                                         |
| table_of_contents_row       | 19791   | 174  | column,table_of_contents_container,table_of_contents_row                                                                                                                                                                                                                | read          | one TOC row; children are the item and the number                                                                   |
| table_of_contents_number    | 19130   | 173  | list_item,table_of_contents_row                                                                                                                                                                                                                                         | read          | the page number part of a TOC row                                                                                   |
| column                      | 18041   | 762  | abstract,authors,chart,column,complex_cell,diagram,figure_label,footnote,list_item,multiple_choice_block,page_info,rotated_container,section_header,table_of_contents_container                                                                                         | read          | a page-column container                                                                                             |
| table                       | 12361   | 801  | column,complex_cell,diagram,figure_label,list_item,multiple_choice_option,page_info,rotated_container,table_spanning_cell                                                                                                                                               | read          | the table container; children are rows and columns                                                                  |
| qed_symbol                  | 10236   | 247  | column,footnote,list_item                                                                                                                                                                                                                                               | read          | the end-of-proof mark                                                                                               |
| table_spanning_cell         | 10126   | 474  | column,diagram,table,table_spanning_cell                                                                                                                                                                                                                                | read          | a cell spanning several columns or rows (cell_col_span / cell_row_span)                                             |
| pseudocode                  | 7883    | 213  | diagram                                                                                                                                                                                                                                                                 | read          | a line of an algorithm environment; pdfdrill has NO algorithm object (T-0120)                                       |
| footnote                    | 5813    | 841  | column,figure_label,footnote,list_item,rotated_container,table_of_contents_row                                                                                                                                                                                          | read          | a footnote body at the foot of the page                                                                             |
| authors                     | 2495    | 1093 | authors,column,diagram                                                                                                                                                                                                                                                  | read          | the author block container; its children carry the names                                                            |
| chart                       | 2365    | 427  | chart,column,complex_cell,diagram,figure_label,footnote,list_item,multiple_choice_option,page_info,rotated_container,table_of_contents_container                                                                                                                        | read          | a region read as a chart; subtype carries the analytical kind                                                       |
| title                       | 1941    | 1123 | column                                                                                                                                                                                                                                                                  | read          | the document title                                                                                                  |
| abstract                    | 1072    | 873  | column                                                                                                                                                                                                                                                                  | read          | the abstract container; its children carry the prose                                                                |
| table_of_contents_container | 744     | 172  | column,table_of_contents_row                                                                                                                                                                                                                                            | read          | the TOC block; children are rows                                                                                    |
| form_field                  | 722     | 58   | column,complex_cell,diagram,figure_label,list_item,multiple_choice_block,multiple_choice_option                                                                                                                                                                         | DECLARED ONLY | a fillable form field                                                                                               |
| quote                       | 483     | 114  | column,complex_cell                                                                                                                                                                                                                                                     | read          | a block quotation                                                                                                   |
| multiple_choice_block       | 457     | 26   | column,list_item,multiple_choice_option                                                                                                                                                                                                                                 | DECLARED ONLY | a multiple-choice question block                                                                                    |
| formula                     | 166     | 3    | -                                                                                                                                                                                                                                                                       | read          | a chemical formula region (NOT mathematics -- see the note below)                                                   |
| rotated_container           | 161     | 25   | column                                                                                                                                                                                                                                                                  | DECLARED ONLY | a container for sideways material                                                                                   |
| multiple_choice_option      | 125     | 12   | list_item,multiple_choice_block,multiple_choice_option                                                                                                                                                                                                                  | DECLARED ONLY | one option of such a block                                                                                          |
| rotated_text                | 118     | 8    | column                                                                                                                                                                                                                                                                  | read          | sideways text; rotation gives the angle                                                                             |
| icon                        | 108     | 27   | column,diagram,page_info                                                                                                                                                                                                                                                | DECLARED ONLY | a small pictogram                                                                                                   |
| equation                    | 105     | 2    | column                                                                                                                                                                                                                                                                  | read          | a numbered display equation; rare, 105 lines in 2 documents                                                         |
| table_split_cell            | 22      | 10   | table                                                                                                                                                                                                                                                                   | read          | a cell continued across a page or column break                                                                      |
| molecule                    | 11      | 5    | diagram                                                                                                                                                                                                                                                                 | read          | a chemical structure region                                                                                         |
| diagram_info                | 7       | 2    | diagram                                                                                                                                                                                                                                                                 | DECLARED ONLY | metadata emitted beside a diagram                                                                                   |
| caption                     | 5       | 2    | column                                                                                                                                                                                                                                                                  | read          | a caption line; MathPix types most captions plain text instead, which is why caption_anchors() exists in line_types |
| x_axis_tick_label           | 1       | 1    | -                                                                                                                                                                                                                                                                       | DECLARED ONLY | one tick label of a chart axis                                                                                      |

### Containers and children, as measured

`parent_id` points at the container; `children_ids` lists the other
direction. The pairs actually present in the corpus:

| parent                      | child                    | lines  |
|-----------------------------|--------------------------|--------|
| table                       | simple_cell              | 741004 |
| column                      | text                     | 534411 |
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
| column                      | section_header           | 13555  |
| column                      | math                     | 13541  |
| page_info                   | text                     | 10765  |
| table                       | table_spanning_cell      | 10117  |
| table_spanning_cell         | simple_cell              | 8771   |
| list_item                   | math                     | 7992   |
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

`formula` is a CHEMICAL formula, not mathematics — 166 lines in 3 documents,
beside `molecule`. Mathematics is `math` (and, in 2 documents, `equation`).
A reader that maps `formula` to an equation object is wrong about every one
of those lines.

## 7. The text dialect

`text` carries LaTeX inline, in exactly two delimiters:

- `\( ... \)` for inline mathematics;
- `\[ ... \]` for display mathematics, newline-separated from its content.

`text_display` carries the same content with the document's own LaTeX
structure around it (`\title{...}`, `\author{...}`) and leading newlines;
it is a presentation string, not a parse target. A dollar sign in prose
arrives escaped as `\$`.

## 8. Coverage — who reads each type

Every one of the 41 types is named somewhere in `src/`, but a mention
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

- declared by pdfdrill but NOT in the contract: none
- in the contract but NOT declared by pdfdrill: `formula`, `equation`, `caption`

The second list is the live one. Those types ARE in the corpus — the table
above gives their counts — and pdfdrill's own type declaration does not
mention them, so nothing in the type contract's own checks can notice them.
`formula` matters most: it is a CHEMICAL formula, and a reader that meets it
undeclared is one guess away from filing it as mathematics.

## 9. The shared vocabulary, for every reader

glyphdrill, pdf2mmd2 and Gemma emit THE SAME type names as MathPix. A reader
emits a SUBSET and states which subset in its own output; it never invents a
name that means something MathPix already names. Measured today, pdfdrill's
own glyph reader emits **2** of the 41 (`text`, `math`) over
6943846 lines — which is the whole of the keyless lane's structural
poverty in one number, and the reason the twenty modules that build Table,
Diagram, CodeListing and Section have nothing to work with on that route.

## 10. What is NOT established

- The MEANING column is written from the measured examples and from the
  module that reads each type. For the 7 declared-only types
  there is no reader to check against, so those meanings are inferred from
  the name and the example line, and are marked here rather than in the JSON.
- `conversion_output`'s full rule is stated from containers versus content
  lines; other cases may exist.
- No claim is made about MathPix's own versioning: the contract describes
  what the library holds, not what the API will return tomorrow.
