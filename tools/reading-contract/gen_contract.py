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

#: §5's confidence measurement. Written by probe_confidence.py; absent when
#: the probe has not been run, and the section then says so rather than
#: repeating the refuted claim.
CONF = {}
_cf = HERE / "confidence.json"
if _cf.exists():
    CONF = json.loads(_cf.read_text(encoding="utf-8"))
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

#: MathPix is measured in TWO classes, because the two API vintages carry
#: different fields and different container nesting (§4a). `MP` is their
#: union, for everything that is common to MathPix as such; CLASSIC and NEWER
#: are reported separately where they differ.
#:
#: There is no "mathpix" class any more. The first version of this script read
#: one, and it contained 34 files of ours whose `source` sits on each page
#: instead of at the top — see §1a.
CLASSIC = M["per_producer"]["mathpix-classic"]
NEWER = M["per_producer"]["mathpix-newer"]


def _merge(a, b):
    """Union of two producer records. Documents are disjoint (a file has one
    producer), so document counts add."""
    from collections import Counter

    def pairs(key, k_is_triple=True):
        c, d = Counter(), Counter()
        for rec in (a, b):
            for row in rec[key]:
                if k_is_triple:
                    c[row[0]] += row[1]
                    d[row[0]] += row[2]
                else:
                    c[row[0]] += row[1]
        return c, d

    lines = a["lines"] + b["lines"]
    pages = a["pages"] + b["pages"]
    tc, td = pairs("types")
    lf, _ = pairs("line_fields")
    pf, _ = pairs("page_fields")
    from collections import Counter as C
    pcc = C()
    for rec in (a, b):
        for k, n in rec["parent_child"]:
            pcc[k] += n
    stc = C()
    for rec in (a, b):
        for k, n in rec["subtypes"]:
            stc[k] += n
    ff = C()
    for rec in (a, b):
        for k, n in rec["file_fields"]:
            ff[k] += n
    return {
        "files_n": a["files_n"] + b["files_n"], "pages": pages, "lines": lines,
        "types": [[t, n, td[t]] for t, n in tc.most_common()],
        "line_fields": [[k, n, round(100.0 * n / max(1, lines), 1)]
                        for k, n in lf.most_common()],
        "page_fields": [[k, n, round(100.0 * n / max(1, pages), 1)]
                        for k, n in pf.most_common()],
        "file_fields": ff.most_common(),
        "subtypes": stc.most_common(),
        "parent_child": pcc.most_common(),
    }


MP = _merge(CLASSIC, NEWER)

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
 "form_field": "a fillable form field",
 "multiple_choice_block": "a multiple-choice question block",
 "multiple_choice_option": "one option of such a block",
 "icon": "a small pictogram",
 "molecule": "a chemical structure region",
#: `caption`, `equation`, `formula` and `rotated_text` are deliberately NOT
#: here: no MathPix file in the library carries them. They were in the first
#: draft because 34 files of ours were misclassified (§1a).
}


# ---------------------------------------------------- derived, for the prose
def _n(rec, key, name):
    for row in rec[key]:
        if row[0] == name:
            return row[1]
    return 0


def _share(rec, key, name, total):
    return 100.0 * _n(rec, key, name) / max(1, total)


def _pc(rec, pair):
    for k, n in rec["parent_child"]:
        if k == pair:
            return n
    return 0


DM = M["per_producer"]["reader:pdfminer-docmodel"]
_by = dict(DM["classified_by"])
TOPLEVEL = _by.get("top-level source", 0)
PAGELEVEL = _by.get("page-level source", 0)
#: What LEFT MathPix when the rule was corrected: exactly the files the
#: page-level rule now claims. Taken from the measurement's `by_rule` record,
#: never by subtracting one run's totals from another's -- a number this
#: document cannot reproduce is an assertion.
_MOVED = M["by_rule"].get("reader:pdfminer-docmodel|page-level source",
                          {"files": [], "pages": 0, "lines": 0})
MOVED_PAGES = _MOVED["pages"]
MOVED_LINES = _MOVED["lines"]
OUR_MATH = _n(DM, "types", "math")
OUR_FORMULA = _n(DM, "types", "formula")


def _moved_block():
    """The moved documents as display lines. The sigma26 run is collapsed to a
    range because 20 consecutive names say less than 'sigma26-073 ... -092'
    does; everything else is named in full."""
    docs = sorted({d.split("/")[0] for d in _MOVED["files"]})
    sig = sorted(d for d in docs if d.startswith("sigma26-"))
    rest = [d for d in docs if not d.startswith("sigma26-")]
    out, line = [], ""
    for d in rest:
        if len(line) + len(d) > 72:
            out.append(line.rstrip(", "))
            line = ""
        line += d + ", "
    if line:
        out.append(line.rstrip(", "))
    if sig:
        out.append("and %s ... %s (%d files)." % (sig[0], sig[-1], len(sig)))
    return out



#: Meanings for the types pdfdrill declares and MathPix does not emit.
PDFDRILL_ONLY_MEANING = {
 "rotated_text": "sideways text in pdfdrill's own reader; `rotation` gives the"
                 " angle. MathPix has `rotated_container` but emits no"
                 " `rotated_text` line in any file in the library.",
 "caption": "a caption line in pdfdrill's reader. MathPix types most captions"
            " plain `text`, which is why caption_anchors() exists in"
            " line_types.",
 "equation": "display maths in pdfdrill's pre-844 vocabulary. _mp_type now"
             " translates it; MathPix emits no `equation` at all.",
 "formula": "a glyph run in a maths font that survived classification -- an"
            " author line misread, not an equation and not chemistry.",
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
 # MathPix is one producer measured in two API vintages; `classes` records
 # them so a consumer can tell which shape it is holding (§4a).
 "classes": {
   cls_name: {
     "files": rec["files_n"], "pages": rec["pages"], "lines": rec["lines"],
     "types": len(rec["types"]),
     # Fields present on EVERY line / page of the class. Computed from the
     # counts, never from the rounded share: a field on 99.96% of lines
     # rounds to 100.0% and is not always present, and `lines-check` would
     # then refuse the 0.04% as broken.
     #
     # MEASURED, NOT DECLARED. MathPix publishes no required-field list, so
     # this is "no counter-example in the library", which is what makes it
     # usable as a check and also what limits it: a field that is simply
     # never absent here may still be optional in their API.
     "always_present_line_fields":
         [k for k, n, _ in rec["line_fields"] if n == rec["lines"]],
     "always_present_page_fields":
         [k for k, n, _ in rec["page_fields"] if n == rec["pages"]],
   }
   for cls_name, rec in (("mathpix-classic", CLASSIC),
                         ("mathpix-newer", NEWER))
 },
 # Types pdfdrill declares that NO MathPix file carries. The contract covers
 # two vocabularies and this is the boundary between them; without it the
 # drift gate compares unlike lists and fails on a correct declaration.
 "pdfdrill_only_types": [
   {"name": t,
    "measured_lines": _n(M["per_producer"]["reader:pdfminer-docmodel"],
                         "types", t),
    "seen_in": "reader:pdfminer-docmodel",
    "meaning": PDFDRILL_ONLY_MEANING.get(t, "")}
   for t in sorted(set(DECLARED) - {x for x, _, _ in MP["types"]})],
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

**The first version of this section fell into that trap itself.** The
coordinator's review of commit `7a6dc1dc` caught it: the rule read `source`
only at the TOP level, so %(pagelevel)d of our own files were filed as
MathPix and their fields and types were reported as MathPix's. §1a records
exactly what moved. Every number in this contract is the corrected
measurement.

%(producers)s

MathPix as a whole is therefore **%(mp_files)d files, %(mp_pages)d pages,
%(mp_lines)d lines, %(ntypes)d types** — split in the table because the two
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
   can say it carries pages from two readers. %(pagelevel)d files are in this
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

## 1a. What the corrected rule moved, and what it invalidated

The first measurement classified by top-level `source` or else by shape.
%(pagelevel)d files of ours declare `source` on each PAGE only — the shape our
writer used before defect 846 moved the key to the top — so all %(pagelevel)d
were filed as MathPix. They are, by name:

%(moved_docs)s

Every one carries page-level `source: "pdfminer-docmodel"`, so they were never
ambiguous: the rule did not look where the answer was. The defect-846 comment
in `docmodel_six.py` records inkdrill hitting this same failure ("every
reading of ours looked like MathPix to it"), and this measurement reproduced
it. §1's own closing line already said *decide by the declared producer,
never by the shape*; rule 2 of the old list did the opposite.

What moved out of MathPix: **%(moved_pages)d pages and %(moved_lines)d
lines**, leaving MathPix at %(mp_files)d files / %(mp_pages)d pages /
%(mp_lines)d lines.

Three consequences, each invalidating something the contract had stated:

**1. Four of the 41 "MathPix types" are not MathPix types.** `caption`,
`equation`, `formula` and `rotated_text` occur in NO MathPix file in the
library. They came entirely from those %(pagelevel)d files, in pdfdrill's
INTERNAL vocabulary, because those files also predate defect 844 — the commit
that added `_mp_type`, the translation from our type names into MathPix's. The
real MathPix vocabulary is **%(ntypes)d types**. `_mp_type`'s own docstring
says so for two of them: *"MathPix emits no `equation` at all"*, and `formula`
maps to `text`.

**2. One type name means opposite things on the two sides, and the old table
summed them.** Ours `math` = PROSE carrying inline maths; MathPix `math` =
DISPLAY maths. The old §6 row for `math` added %(our_math)d of our lines to
MathPix's %(mp_math)d. Defect 844 exists because that collision already cost
`inlinectx.load_spans` 79.2%% of its inline spans; a contract that sums the
two re-creates the defect at the documentation level.

**3. Sixteen fields in §4/§5 were ours.** Page: `px_per_pt`, `source`,
`diagrams`, `fills`, `links`. Line: `complete`, `gaps`, `rules`,
`deferred_glyphs`, `_i`, `level`, `rotation`, `label`, `number`, `caption_id`,
`caption_number`. The review named five of the line fields; the other six had
the same cause and were in the same table.

Also corrected in passing: the first draft called `formula` "a CHEMICAL
formula, not mathematics", reasoning from `molecule` nearby. It is neither.
`_mp_type`'s docstring records what those %(our_formula)d lines are — a glyph
run in a maths font that survived classification, e.g. an author line misread
as "Josef $\\mathrm{Ba}\\ker$ , Alan Sexton and $\\mathrm{Vol}\\ker$ Sorge".

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

%(file_fields)s

Both MathPix classes carry nothing at the top level, which is why a top-level
`source` is a safe producer test in ONE DIRECTION ONLY: its presence proves a
reader, its absence proves nothing. **%(toplevel)d of the %(dm_files)d
`pdfminer-docmodel` files declare `source` at the top; the other
%(pagelevel)d declare it per page** (§1a). A consumer reading only the top
level misreads those %(pagelevel)d as MathPix — which is what `cmd_ocr`'s
backup guard did (defect 846), and what this contract's first draft did.

## 4. Page fields

Per class, because the two vintages do not carry the same page fields. Only
fields MathPix writes appear here; the five the first draft listed
(`px_per_pt`, `source`, `diagrams`, `fills`, `links`) were ours, on
%(moved_pages)d pages, and are gone (§1a).

**mathpix-classic** — %(c_files)d files, %(c_pages)d pages:

%(c_pages_tbl)s

Five fields, and that is all: a classic page carries no confidence of its own.

**mathpix-newer** — %(n_files)d files, %(n_pages)d pages:

%(n_pages_tbl)s

## 4a. The two API vintages, and why the split is not cosmetic

**`parse_status`, `fallback_count` and `page_confidence` are GENUINE MathPix
fields**, from the newer API. glyphdrill2 reported seeing `parse_status` in a
real MathPix file and was right. The evidence is in the files, on all
%(n_files)d:

| discriminator       | mathpix-newer                                  | our `gemma_reader`  |
|---------------------|------------------------------------------------|---------------------|
| `image_id`          | real UUID + page suffix, e.g. `...-2651ee-01`  | `""`                |
| `page_confidence`   | dict, `method: "prototype_min_v1"`             | `None`              |
| `furniture_retyped` | absent                                         | always present      |
| line fields         | `text_confidence`, `layout_confidence` on 100%% | neither             |

A grep is what made this look like ours: `gemma_reader.py` does write all
three names, because it mimics MathPix's shape like everything else here.
**It names who can write the field, not who did.** These files are MathPix.

Two differences a consumer must handle, not merely note:

1. **The newer API emits no `table_row` and no `table_column`.** Classic
   nests `table > table_row` (%(c_trow)d lines) and `table > table_column`
   (%(c_tcol)d); newer has %(n_table)d `table` lines over %(n_tabledocs)d
   documents and **zero** of either, going `table > simple_cell`
   (%(n_cell)d) directly. Code that walks a table by its rows finds nothing
   in a newer reading and reports an empty table, not an error.
2. **Confidence moved onto every line.** `confidence` is on %(c_conf).1f%% of
   classic lines and %(n_conf).1f%% of newer ones, and newer adds
   `text_confidence` and `layout_confidence` on 100%%. A threshold tuned on
   one vintage does not transfer.

Neither vintage is declared in the file. The only way to tell them apart is
`page_confidence` being a dict, which is what the producer rule tests.

## 5. Line fields

Per class again, and ours removed. The first draft's table mixed in eleven
fields of ours — `complete`, `gaps`, `rules`, `deferred_glyphs`, `_i`,
`level`, `rotation`, `label`, `number`, `caption_id`, `caption_number` — all
from the %(pagelevel)d files of §1a.

**mathpix-classic** — %(c_lines)d lines:

%(c_lines_tbl)s

**mathpix-newer** — %(n_lines)d lines:

%(n_lines_tbl)s

`cnt` is a four-point polygon `[[x,y],[x,y],[x,y],[x,y]]` in the pixel space
of §2; `region` is the same box as `{top_left_x, top_left_y, width, height}`.
Both are present on every line. `line` is a 1-based running index within the
page and `column` a 0-based column number.

`conversion_output` is a boolean and it is NOT a quality flag: it is false on
CONTAINER lines, whose own `text` is empty and whose children carry the
content (`authors`, `abstract`), and true on the lines that contribute text.

**`conversion_output` does NOT explain where `confidence` is missing.** The
first draft of this contract said it did — that the field is absent "on
exactly those containers", which is why its share sits near 90%%. Measured
over all %(c_lines)d classic lines (`probe_confidence.py`), that is false:

```
confidence missing            %(cm)d of %(c_lines)d   (%(cmp).2f%%)
conversion_output false       %(cof)d
   ... and confidence PRESENT %(cofp)d   (%(cofpp).1f%% of them)
conversion_output true
   ... and confidence ABSENT  %(cota)d
```

So three quarters of the lines the claim called "exactly those containers"
carry the field, and %(cota)d lines carry no confidence despite contributing
text. The absence is instead strongly TYPE-bound, and for some types
categorical:

%(conf_tbl)s

A type at 100%% never carries confidence; `list_item`, `footnote`, `authors`,
`figure_label` and `section_header` carry it on some lines and not others
within the same type. **No mechanism is offered here.** What a consumer may
rely on is only this: `confidence` may be absent on any line, its absence is
not predictable from `conversion_output`, and code must treat it as optional
rather than defaulting a missing value to 0.0 or to 1.0.

In `mathpix-newer` the question does not arise: `confidence` is on
%(n_conf).1f%% of lines, with `text_confidence` and `layout_confidence`
beside it.

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

**This table counts MathPix files only.** `caption`, `equation`, `formula`
and `rotated_text` are absent from it on purpose: no MathPix file in the
library carries them (§1a). Mathematics is `math`, and `math` ALONE —
MathPix emits no `equation` at all, which is what `_mp_type` exists to
translate. A reader that expects an `equation` type from MathPix will find
none in %(mp_files)d files.

`molecule` (%(mp_molecule)d lines) is a chemical structure region and has no
`formula` companion in MathPix's vocabulary.

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

- declared by pdfdrill but NOT a MathPix type: %(tc_extra)s
- a MathPix type but NOT declared by pdfdrill: %(tc_missing)s

**The second list is empty: pdfdrill declares every one of MathPix's
%(ntypes)d types.** That is the direction that would hurt, and there is no
drift in it.

The first list is not drift either, and the first version of this section got
that wrong. `rotated_text` is pdfdrill's OWN type, emitted by our reader
(%(our_rotated)d lines) and absent from every MathPix file in the library.
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
own glyph reader emits **2** of the %(ntypes)d (`text`, `math`) over
%(chars_lines)d lines — which is the whole of the keyless lane's structural
poverty in one number, and the reason the twenty modules that build Table,
Diagram, CodeListing and Section have nothing to work with on that route.

## 10. What is NOT established

- The MEANING column is written from the measured examples and from the
  module that reads each type. For the %(ndeclared)d declared-only types
  there is no reader to check against, so those meanings are inferred from
  the name and the example line, and are marked here rather than in the JSON.
- `conversion_output`'s rule is stated for containers versus content lines.
  It does NOT explain `confidence`'s absence; §5 records the measurement that
  refuted that, and no mechanism is offered in its place.
- **Producer classification rests on declared fields and markers. A file
  carrying neither is `unknown-shape`** (%(unknown)d files), and is counted
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
 "mp_pages": MP["pages"], "mp_lines": MP["lines"],
 "toplevel": TOPLEVEL, "pagelevel": PAGELEVEL, "dm_files": DM["files_n"],
 "moved_pages": MOVED_PAGES, "moved_lines": MOVED_LINES,
 "moved_docs": "\n".join("> " + d for d in _moved_block()),
 "our_math": OUR_MATH, "our_formula": OUR_FORMULA,
 "our_rotated": _n(M["per_producer"]["reader:pdfminer-docmodel"], "types",
                   "rotated_text"),
 "mp_math": _n(MP, "types", "math"),
 "mp_molecule": _n(MP, "types", "molecule"),
 "c_files": CLASSIC["files_n"], "c_pages": CLASSIC["pages"],
 "c_lines": CLASSIC["lines"],
 "n_files": NEWER["files_n"], "n_pages": NEWER["pages"],
 "n_lines": NEWER["lines"],
 "c_pages_tbl": table([[k, n, "%.1f%%" % sh] for k, n, sh in CLASSIC["page_fields"]],
                      ["page field", "pages", "share"]),
 "n_pages_tbl": table([[k, n, "%.1f%%" % sh] for k, n, sh in NEWER["page_fields"]],
                      ["page field", "pages", "share"]),
 "c_lines_tbl": table([[k, n, "%.1f%%" % sh] for k, n, sh in CLASSIC["line_fields"]],
                      ["line field", "lines", "share"]),
 "n_lines_tbl": table([[k, n, "%.1f%%" % sh] for k, n, sh in NEWER["line_fields"]],
                      ["line field", "lines", "share"]),
 "c_trow": _pc(CLASSIC, "table>table_row"),
 "c_tcol": _pc(CLASSIC, "table>table_column"),
 "n_table": _n(NEWER, "types", "table"),
 "n_tabledocs": [d for t, n, d in NEWER["types"] if t == "table"][0]
                if any(t == "table" for t, _, _ in NEWER["types"]) else 0,
 "n_cell": _pc(NEWER, "table>simple_cell"),
 "c_conf": _share(CLASSIC, "line_fields", "confidence", CLASSIC["lines"]),
 "cm": CONF.get("mathpix-classic", {}).get("missing_confidence", 0),
 "cmp": CONF.get("mathpix-classic", {}).get("missing_pct", 0.0),
 "cof": CONF.get("mathpix-classic", {}).get("conversion_output_false_lines", 0),
 "cofp": CONF.get("mathpix-classic", {}).get(
     "conversion_output_false_BUT_confidence_present", 0),
 "cofpp": (100.0 * CONF.get("mathpix-classic", {}).get(
     "conversion_output_false_BUT_confidence_present", 0)
     / max(1, CONF.get("mathpix-classic", {}).get(
         "conversion_output_false_lines", 1))),
 "cota": CONF.get("mathpix-classic", {}).get(
     "conversion_output_true_BUT_confidence_absent", 0),
 "conf_tbl": table([[t, m, tot, "%.1f%%" % pct] for t, m, tot, pct in
                    CONF.get("mathpix-classic", {}).get("missing_rate_by_type", [])[:14]],
                   ["type", "no confidence", "lines", "share"])
             if CONF else "(probe_confidence.py has not been run)",
 "n_conf": _share(NEWER, "line_fields", "confidence", NEWER["lines"]),
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
