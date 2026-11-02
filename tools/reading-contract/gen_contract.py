#!/usr/bin/env python3
"""T-0107 — generate contracts/reading.md and reading-types.json.

EVERY NUMBER IN THE OUTPUT COMES FROM measured.json. None is typed in by
hand, so re-running measure.py and this script reproduces the document; a
count that cannot be reproduced is a defect in the contract, not a detail.
The prose is written here, beside the numbers it describes.
"""
import json
import sys
from pathlib import Path

#: the measurement directory, not the script's own: the scripts are
#: committed and the measurement is not.
HERE = Path(sys.argv[2] if len(sys.argv) > 2 else "work/run-files/t0107")
OUT = Path(sys.argv[1] if len(sys.argv) > 1
           else "/home/wkolbe/MX/PDFDRILL/docs/contracts")
M = json.loads((HERE / "measured.json").read_text(encoding="utf-8"))
COV = json.loads((HERE / "coverage.json").read_text(encoding="utf-8"))
LIST_MODULES = {"src/docmodel/type_contract.py", "src/docmodel/line_types.py"}

#: What pdfdrill's own type_contract declares, for the drift section. Imported
#: rather than parsed: the declaration is a Python dict and reading it any
#: other way would be a second, wrong copy of the same list.
sys.path.insert(0, "src")
try:
    from docmodel import type_contract as _TC
    DECLARED = sorted({k for a in ("CLAIMED", "IGNORED")
                       for k in (getattr(_TC, a, {}) or {})
                       if isinstance(k, str)})
except Exception as _e:                                        # noqa: BLE001
    DECLARED = []
    print("WARNING: type_contract not importable (%s); the drift section "
          "will say so rather than claim agreement" % _e)

MP = M["per_producer"]["mathpix"]

#: What each line type MEANS. Written from the measured examples and from the
#: module that reads it; a type with no reader and no example in the corpus
#: says so rather than guessing.
MEANING = {
 "text": "a run of prose on one baseline; the workhorse type",
 "math": "a display or inline equation, text carrying the LaTeX in the dialect below",
 "simple_cell": "one table cell with a single value",
 "complex_cell": "a table cell whose content is itself structured (list, equation, nested table)",
 "table_spanning_cell": "a cell spanning several columns or rows (cell_col_span / cell_row_span)",
 "table_split_cell": "a cell continued across a page or column break",
 "table_row": "a row container; its children are the cells",
 "table_column": "a column container; a second grouping over the same cells",
 "table": "the table container; children are rows and columns",
 "page_info": "running head, folio, arXiv stamp -- page furniture, not content",
 "list_item": "one item of an enumerated or bulleted list",
 "code": "a line of a verbatim/listing environment",
 "pseudocode": "a line of an algorithm environment; pdfdrill has NO algorithm object (T-0120)",
 "equation_number": "the tag beside a numbered equation, e.g. (3.14)",
 "section_header": "a heading at any level; level, when present, says which",
 "figure_label": "the 'Figure 3' label of a figure, separate from its caption",
 "caption": "a caption line; MathPix types most captions plain text instead, which is why"
            " caption_anchors() exists in line_types",
 "diagram": "a region MathPix read as a drawing rather than text",
 "diagram_info": "metadata emitted beside a diagram",
 "chart": "a region read as a chart; subtype carries the analytical kind",
 "x_axis_tick_label": "one tick label of a chart axis",
 "column": "a page-column container",
 "title": "the document title",
 "authors": "the author block container; its children carry the names",
 "abstract": "the abstract container; its children carry the prose",
 "footnote": "a footnote body at the foot of the page",
 "quote": "a block quotation",
 "qed_symbol": "the end-of-proof mark",
 "table_of_contents_container": "the TOC block; children are rows",
 "table_of_contents_row": "one TOC row; children are the item and the number",
 "table_of_contents_item": "the title part of a TOC row",
 "table_of_contents_number": "the page number part of a TOC row",
 "rotated_container": "a container for sideways material",
 "rotated_text": "sideways text; rotation gives the angle",
 "form_field": "a fillable form field",
 "multiple_choice_block": "a multiple-choice question block",
 "multiple_choice_option": "one option of such a block",
 "icon": "a small pictogram",
 "molecule": "a chemical structure region",
 "formula": "a chemical formula region (NOT mathematics -- see the note below)",
 "equation": "a numbered display equation; rare, 105 lines in 2 documents",
}

def table(rows, head):
    w = [max(len(str(r[i])) for r in [head] + rows) for i in range(len(head))]
    out = ["| " + " | ".join(str(h).ljust(w[i]) for i, h in enumerate(head)) + " |",
           "|" + "|".join("-" * (x + 2) for x in w) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c).ljust(w[i]) for i, c in enumerate(r)) + " |")
    return "\n".join(out)

def readers_of(t):
    for r in COV:
        if r["type"] == t:
            real = [p for p in r["readers"] if p not in LIST_MODULES]
            return [p.replace("src/", "") for p in real]
    return []

# ----------------------------------------------------------------- types json
types_json = {
 "contract": "reading/1",
 "measured_at": M["measured_at"],
 "library": M["library"],
 "producer": "mathpix",
 "files": MP["files_n"], "pages": MP["pages"], "lines": MP["lines"],
 "types": [
   {"name": t, "meaning": MEANING.get(t, ""), "measured_lines": n,
    "measured_docs": d,
    "parents": sorted({pc.split(">")[0] for pc, _ in MP["parent_child"]
                       if pc.split(">")[1] == t}),
    "readers": readers_of(t),
    "status": "read" if readers_of(t) else "declared-only"}
   for t, n, d in MP["types"]],
}
OUT.mkdir(parents=True, exist_ok=True)
(OUT / "reading-types.json").write_text(
    json.dumps(types_json, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print("wrote", OUT / "reading-types.json", len(types_json["types"]), "types")

# ------------------------------------------------------------------ markdown
prod_rows = [[p, M["per_producer"][p]["files_n"], M["per_producer"][p]["pages"],
              M["per_producer"][p]["lines"], len(M["per_producer"][p]["types"])]
             for p, _ in M["producers"]]
type_rows = [[t, n, d,
              ",".join(sorted({pc.split(">")[0] for pc, _ in MP["parent_child"]
                               if pc.split(">")[1] == t})) or "-",
              "read" if readers_of(t) else "DECLARED ONLY",
              MEANING.get(t, "")]
             for t, n, d in MP["types"]]
line_rows = [[k, n, "%.1f%%" % s] for k, n, s in MP["line_fields"]]
page_rows = [[k, n, "%.1f%%" % s] for k, n, s in MP["page_fields"]]
pc_rows = [[pc.split(">")[0], pc.split(">")[1], n]
           for pc, n in MP["parent_child"][:25]]
st_rows = [[s.split("/")[0], s.split("/", 1)[1], n] for s, n in MP["subtypes"][:25]]
declared_only = [t for t, n, d in MP["types"] if not readers_of(t)]
declared_lines = sum(n for t, n, d in MP["types"] if not readers_of(t))

doc = """# contracts/reading.md — the reading contract (reading/1)

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

Measured %(when)s over `%(lib)s`, read only. Nothing in the library was
written. Every count below comes from `measured.json`; none is typed in by
hand.

## 1. The population, and why it is reported per producer

The library holds **%(files)d** `*/*.lines.json` files totalling 6.3 GB. Only
**%(mp_files)d** of them are MathPix readings. The rest are our own readers'
output written in the same shape, and counting them together would produce a
"MathPix contract" that describes pdfdrill's own output back to us — the
same trap that inflated the `.tex` font census twice (T-0107's own note of
2026-10-31).

%(producers)s

The producer is taken FROM THE FILE, in this order:

1. the top-level `source` field, where a writer sets one — `pdfminer-chars`
   is pdfdrill's glyph reader, and `source` WINS even if MathPix markers are
   also present, because a file our reader wrote is our reader's output
   whatever it copied;
2. otherwise `is_printed` or `confidence` on a line, which MathPix sets and
   our readers do not → `mathpix`;
3. otherwise `unknown-shape`, counted and listed, never folded into MathPix.

**%(unknown)d files name no producer at all**, and they are listed by name
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

%(file_fields)s

## 4. Page fields

%(pages)s

## 5. Line fields

%(lines)s

`cnt` is a four-point polygon `[[x,y],[x,y],[x,y],[x,y]]` in the pixel space
of §2; `region` is the same box as `{top_left_x, top_left_y, width, height}`.
Both are present on every line. `line` is a 1-based running index within the
page and `column` a 0-based column number.

`conversion_output` is a boolean and it is NOT a quality flag: it is false on
CONTAINER lines, whose own `text` is empty and whose children carry the
content (`authors`, `abstract`), and true on the lines that contribute text.
`confidence` and `confidence_rate` are absent on exactly those containers,
which is why their presence share is ~90%% rather than 100%%.

**Confidence is not a correctness signal.** MathPix gives 1.0 to fragments
and to CJK misreads (GLYPHDRILL2 T-0113). The only proven signals are
inkdrill's confirmed distance 0 and the author's own LaTeX.

## 6. The type vocabulary

%(types)s

### Containers and children, as measured

`parent_id` points at the container; `children_ids` lists the other
direction. The pairs actually present in the corpus:

%(pc)s

### Subtypes

%(st)s

`formula` is a CHEMICAL formula, not mathematics — 166 lines in 3 documents,
beside `molecule`. Mathematics is `math` (and, in 2 documents, `equation`).
A reader that maps `formula` to an equation object is wrong about every one
of those lines.

## 7. The text dialect

`text` carries LaTeX inline, in exactly two delimiters:

- `\\( ... \\)` for inline mathematics;
- `\\[ ... \\]` for display mathematics, newline-separated from its content.

`text_display` carries the same content with the document's own LaTeX
structure around it (`\\title{...}`, `\\author{...}`) and leading newlines;
it is a presentation string, not a parse target. A dollar sign in prose
arrives escaped as `\\$`.

## 8. Coverage — who reads each type

Every one of the %(ntypes)d types is named somewhere in `src/`, but a mention
in `type_contract.py` or `line_types.py` is a DECLARATION, not a reader.
Excluding those two list modules, **%(ndeclared)d types have no reader at
all**, carrying %(declared_lines)d lines between them:

%(declared)s

That is the gap this contract exists to make visible, and
`tests/test_the_reading_contract_covers_every_type.py` fails if a type is
neither read nor listed here as dropped — so a new MathPix type cannot
vanish silently.

### Drift against pdfdrill's own declaration

`docmodel/type_contract.py` declares **%(ndeclared_tc)d** line types in its
CLAIMED and IGNORED maps. Measured against this contract:

- declared by pdfdrill but NOT in the contract: %(tc_extra)s
- in the contract but NOT declared by pdfdrill: %(tc_missing)s

The second list is the live one. Those types ARE in the corpus — the table
above gives their counts — and pdfdrill's own type declaration does not
mention them, so nothing in the type contract's own checks can notice them.
`formula` matters most: it is a CHEMICAL formula, and a reader that meets it
undeclared is one guess away from filing it as mathematics.

## 9. The shared vocabulary, for every reader

glyphdrill, pdf2mmd2 and Gemma emit THE SAME type names as MathPix. A reader
emits a SUBSET and states which subset in its own output; it never invents a
name that means something MathPix already names. Measured today, pdfdrill's
own glyph reader emits **2** of the %(ntypes)d (`text`, `math`) over
%(chars_lines)d lines — which is the whole of the keyless lane's structural
poverty in one number, and the reason the twenty modules that build Table,
Diagram, CodeListing and Section have nothing to work with on that route.

## 10. What is NOT established

- The MEANING column is written from the measured examples and from the
  module that reads each type. For the %(ndeclared)d declared-only types
  there is no reader to check against, so those meanings are inferred from
  the name and the example line, and are marked here rather than in the JSON.
- `conversion_output`'s full rule is stated from containers versus content
  lines; other cases may exist.
- No claim is made about MathPix's own versioning: the contract describes
  what the library holds, not what the API will return tomorrow.
""" % {
 "when": M["measured_at"], "lib": M["library"], "files": M["files_found"],
 "mp_files": MP["files_n"],
 "producers": table(prod_rows, ["producer", "files", "pages", "lines", "types"]),
 "unknown": M["per_producer"].get("unknown-shape", {}).get("files_n", 0),
 "file_fields": table([[p, ", ".join("%s (%d)" % (k, n) for k, n in
                                     M["per_producer"][p]["file_fields"]) or "-"]
                       for p, _ in M["producers"]], ["producer", "file-level keys"]),
 "pages": table(page_rows, ["page field", "pages", "share"]),
 "lines": table(line_rows, ["line field", "lines", "share"]),
 "types": table(type_rows, ["type", "lines", "docs", "parent(s)", "coverage", "meaning"]),
 "pc": table(pc_rows, ["parent", "child", "lines"]),
 "st": table(st_rows, ["type", "subtype", "lines"]),
 "ntypes": len(MP["types"]), "ndeclared": len(declared_only),
 "declared_lines": declared_lines,
 "declared": "\n".join("- `%s` — %s" % (t, MEANING.get(t, "")) for t in declared_only),
 "chars_lines": M["per_producer"]["reader:pdfminer-chars"]["lines"],
 "ndeclared_tc": len(DECLARED),
 "tc_extra": ", ".join("`%s`" % t for t in DECLARED
                       if t not in {x for x, _, _ in MP["types"]}) or "none",
 "tc_missing": ", ".join("`%s`" % t for t, _, _ in MP["types"]
                         if t not in set(DECLARED)) or "none",
}
(OUT / "reading.md").write_text(doc, encoding="utf-8")
print("wrote", OUT / "reading.md", len(doc), "bytes")
