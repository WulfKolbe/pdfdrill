"""250 — every type the corpus contains must be accounted for.

ONE DIRECTION ONLY. The reverse — every literal in the code must occur in the
corpus — was dropped: out/249 established that "equation", "figure" and
"caption" occur zero times in 4.0M MathPix line objects and are all live,
emitted by the visionocr route or asserted by tests. A literal absent from
today's corpus is not a defect, and a check that flagged those three would have
been answered by allowlisting them, which is decoration.

The direction that has teeth is the other one: a type MathPix emits and no
module names produces nothing, breaks nothing and logs nothing. That is how
`list_item` went unread in 882 documents (out/245, fixed in out/248) and it is
invisible to every test that does not enumerate the input.

CLAIMED names the module that reads each type. IGNORED names a reason, and the
reasons are not interchangeable — three of them mark real gaps, and saying so
in the contract is the point. A type moved into IGNORED to silence the check,
without a reason that survives being read aloud, defeats it.
"""
from __future__ import annotations

import json
from pathlib import Path

INVENTORY = Path(__file__).with_name("corpus_types.json")

#: type -> the module that reads it
CLAIMED: dict[str, str] = {
    "text": "paragraph, list_items, citation",
    "title": "page, paragraph, citation",
    "authors": "page",
    "abstract": "abstract, paragraph",
    "quote": "paragraph",
    "section_header": "header, paragraph",
    "footnote": "footnote, paragraph",
    "page_info": "paragraph (break)",
    "column": "sidenote, paragraph (break)",
    "math": "equation, formula, paragraph (break)",
    "equation_number": "equation, paragraph (break)",
    "table": "table, paragraph (break)",
    "table_row": "table, paragraph (break)",
    "table_column": "table (child), paragraph (break)",
    "simple_cell": "table, paragraph (break)",
    "complex_cell": "table, paragraph (break)",
    "table_spanning_cell": "table",
    "table_of_contents_container": "toc, paragraph (break)",
    "table_of_contents_row": "toc, paragraph (break)",
    "table_of_contents_item": "toc, paragraph (break)",
    "table_of_contents_number": "toc, paragraph (break)",
    "diagram": "diagram, picture (skip), paragraph (break)",
    "chart": "paragraph (break)",
    "figure_label": "paragraph (break)",
    "pseudocode": "paragraph (break)",
    "qed_symbol": "paragraph (break)",
    "list_item": "list_items, paragraph (break)",       # out/248
    "code": "code_listing (CodeListing), diagram (its `code` prop), "
            "paragraph (break)",                        # 259
    "table_split_cell": "table (_CELL_TYPES)",          # 259
    "molecule": "picture (the inline Markdown-CDN path)",
}

#: type -> why nothing reads it. GAP: means content is being dropped.
#:
#: 259 emptied this dict of its GAP entries, and two of the three were wrong
#: when written. `code` was called "dropped entirely" when 43,553 of its 44,689
#: lines already survived as a Diagram's `code` prop; `molecule` was called
#: uncollected when PictureProcessor's inline path had always matched its
#: Markdown CDN link. Both reasons were written from a type's absence in the
#: module that "should" have owned it, without running the module that did.
#: Only `table_split_cell` was the plain omission it claimed to be.
IGNORED: dict[str, str] = {
    "multiple_choice_block": "container only: 453 lines, 23 docs. Its children "
                             "are separately typed and are read on their own, "
                             "so the words survive and only the grouping is "
                             "lost.",
    "multiple_choice_option": "container only: 125 lines, 12 docs. As above.",
    "rotated_container": "container only: 133 lines, 18 docs. As above.",
    "diagram_info": "sub-element: 7 lines, 2 docs. Numeric fragments INSIDE a "
                    "diagram ('110', '- 011'); the diagram itself is a Diagram "
                    "object and these are its internals.",
    "x_axis_tick_label": "sub-element: 1 line, 1 doc. A chart axis label, "
                         "internal to a chart.",
    "form_field": "non-content: 683 lines, 51 docs. Checkbox glyphs (\\n□) "
                  "from questionnaires — UI furniture, no prose.",
    "icon": "non-content: 96 lines, 23 docs. Empty text; a visual mark only.",
}


def corpus_types() -> dict:
    """{type: line count} as last measured. Committed, not scanned at runtime:
    the corpus is 3.8 GB and a startup check must not read it."""
    return json.loads(INVENTORY.read_text(encoding="utf-8"))["counts"]


def violations() -> list[str]:
    """Corpus types named by neither CLAIMED nor IGNORED, worst first."""
    counts = corpus_types()
    known = set(CLAIMED) | set(IGNORED)
    return sorted((t for t in counts if t not in known),
                  key=lambda t: -counts[t])


def gaps() -> dict[str, int]:
    """IGNORED entries whose reason says GAP, with their line counts."""
    counts = corpus_types()
    return {t: counts.get(t, 0) for t, why in IGNORED.items()
            if why.startswith("GAP:")}


# ===========================================================================
# 255 — the same contract, one level down: every FIELD the corpus contains.
#
# A type nobody names drops a whole line. A field nobody reads drops a
# dimension of every line that has it, and it is quieter still: `conversion_
# output` sits on 3,465,341 lines, is carried faithfully through docpack, and
# is consulted by nothing (out/252). `subtype` sat on 1,239,021 and was unread
# until 256.
#
# Same single direction as the type contract, for the same reason. And the same
# rule about reasons: "ignored" earns its place by naming what the values are.
# 253 was the lesson — a reason written from a field's NAME asserted that
# `figure_label` carried figure captions, when reading its values showed axis
# labels and chord names. Every reason below was written after looking at the
# values.
# ===========================================================================

FIELD_INVENTORY = Path(__file__).with_name("corpus_fields.json")

#: field -> what reads it
CLAIMED_FIELDS: dict[str, str] = {
    "id": "base_module.build_line_index; every children_ids lookup",
    "type": "every module — see CLAIMED above",
    "text": "every module (the fallback when text_display is absent)",
    "text_display": "every module (preferred over text)",
    "region": "mathpix.crop_url/image_ref, equation.py's region-nearest number "
              "pairing, semantic.geometry_columns, table rule measurement",
    "children_ids": "footnote, sidenote, diagram, list_items, picture, table",
    "confidence": "equation.py — MathPix's own doubt, surfaced in the formula "
                  "report (out/063)",
    "confidence_rate": "equation.py, tiddlywiki",
    "subtype": "dehyphenation (256, the continues_line_* family), diagram.py "
               "(its own 'code'), formula_report, distill_reader",
    "column": "sidenote.py (a sidenote IS a column line), rectoverso's column "
              "signal",
    "cell_column": "pdfdrill.table_structure",
    "cell_col_span": "pdfdrill.table_structure",
    "cnt": "mathpix.crop_region/quad — 259. Tightens the crop on the 4,618 "
           "lines whose polygon is not axis-aligned and whose `region` "
           "disagrees with its bbox; carried onto Diagram/Picture as `quad` "
           "so a consumer can mask or deskew. Lines without `cnt` keep "
           "`region` unchanged.",
    "font_size": "header.py — 259. Ranks a document's OWN header sizes to set "
                 "Section.level for the 34,128 headers (79%) that carry no "
                 "\\section-family command and were all level 1.",
    "cell_row": "pdfdrill.table_structure",
    "cell_row_span": "pdfdrill.table_structure",
}

#: field -> why nothing reads it. GAP: means information is being lost.
IGNORED_FIELDS: dict[str, str] = {
    "conversion_output": "carried, not read: 3,465,341 lines, a boolean "
                         "(958,464 false / 413,259 true in the 500-doc sample). "
                         "out/252 audited it and found no case where reading it "
                         "would remove content that is wrongly included, so it "
                         "stays unread deliberately rather than by omission.",
    "parent_id": "redundant, VERIFIED: 2,031,812 lines name a parent. Checked "
                 "over 500 documents — 1,122,695 of 1,122,695 parents list the "
                 "child back in `children_ids`. The two are exact inverses, so "
                 "walking children_ids downward loses nothing. This entry "
                 "exists because 'redundant' was an assumption until it was "
                 "counted.",
    "line": "redundant: 3,465,341 lines carry their 1-based index within the "
            "page (1, 2, 3…), which is the order the array already has.",
    "is_printed": "non-content: 3,465,341 lines, effectively constant — 8 "
                  "`false` in 1,371,715 in the 500-doc sample. Echoed into "
                  "snippet requests by mathpix_snip; carries no decision.",
    "is_handwritten": "non-content: as above, 6 `true` in 1,371,717.",
    "selected_labels": "opaque: 61,603 lines in 1,006 documents, each a list of "
                       "32-hex MathPix label ids "
                       "(['f883f3e2b61b46259fe0510affe81c0d']). They resolve "
                       "against nothing we hold, so there is no content behind "
                       "them to lose.",
    "out_of_column": "NOT A MATHPIX FIELD — pdfdrill writes it. "
                     "semantic.geometry_columns.tag_out_of_column stamps it on "
                     "page lines in place and commands.py reads it back in the "
                     "same pass. It reaches 52,668 lines of 90 documents only "
                     "because those files were re-saved after tagging.",
    "margin_role": "NOT A MATHPIX FIELD — as above, same writer, and on exactly "
                   "the same 52,668 lines. Its values come from pdfdrill's own "
                   "classify_margin_item enum, which is what makes the pair "
                   "provably ours: MathPix has no such vocabulary.",
}


def corpus_fields() -> dict:
    """{field: line count} as last measured. Committed, not scanned at runtime."""
    return json.loads(FIELD_INVENTORY.read_text(encoding="utf-8"))["counts"]


def field_violations() -> list[str]:
    """Corpus fields named by neither CLAIMED_FIELDS nor IGNORED_FIELDS."""
    counts = corpus_fields()
    known = set(CLAIMED_FIELDS) | set(IGNORED_FIELDS)
    return sorted((f for f in counts if f not in known), key=lambda f: -counts[f])


def field_gaps() -> dict[str, int]:
    """IGNORED_FIELDS entries whose reason says GAP, with their line counts."""
    counts = corpus_fields()
    return {f: counts.get(f, 0) for f, why in IGNORED_FIELDS.items()
            if why.startswith("GAP:")}


# ===========================================================================
# 260 — the third dimension: VALUES.
#
# 250 asked whether every type is named. 255 asked whether every field is read.
# Both were green while 1,239,021 `subtype` values sat unread: the field was in
# the schema, the type carrying it was claimed, the field was later claimed too
# — and no check could see that the VALUES under it were doing nothing. That is
# the hole this closes. A contract that stops at the field level certifies the
# container, not the contents.
#
# Scope, stated rather than assumed: a value contract only means anything for a
# field with a CLOSED vocabulary. "Every value of `text` is handled" is not a
# claim anyone can make. So the enumerable fields are enumerated and the rest
# are listed in UNBOUNDED_FIELDS with the reason enumeration does not apply —
# because silently skipping them would be the same omission one level down.
# ===========================================================================

VALUE_INVENTORY = Path(__file__).with_name("corpus_values.json")

#: A read field whose values cannot be enumerated -> why not. Listing these is
#: not a formality: the alternative is a check that quietly covers 2 of the 16
#: fields pdfdrill reads and reports itself as complete.
UNBOUNDED_FIELDS: dict[str, str] = {
    "type": "delegated: covered value-by-value by CLAIMED / IGNORED above.",
    "id": "unbounded: an opaque per-line identifier.",
    "text": "unbounded: the content itself.",
    "text_display": "unbounded: the content itself.",
    "region": "structured: four numbers, not a vocabulary.",
    "cnt": "structured: four coordinate pairs.",
    "children_ids": "structured: a list of ids.",
    "confidence": "continuous: a probability in [0,1], consumed by comparison.",
    "confidence_rate": "continuous: as above.",
    "font_size": "ordinal: 207 distinct pixel heights, consumed by RANK within "
                 "a document (header.levels_by_font_size), never by value. "
                 "Enumerating them would invite exactly the absolute threshold "
                 "that ranking exists to avoid.",
    "cell_column": "ordinal: a grid index.",
    "cell_row": "ordinal: a grid index.",
    "cell_col_span": "ordinal: a span count.",
    "cell_row_span": "ordinal: a span count.",
}

#: field -> value -> what reads it.
HANDLED_VALUES: dict[str, dict[str, str]] = {
    "subtype": {
        "continues_line_space": "dehyphenation (256): join with a space",
        "continues_line_newline": "dehyphenation (256): join with a space",
        "continues_line_no_hyphen": "dehyphenation (256): join, drop the hyphen",
        "continues_line_no_space": "dehyphenation (256): join, keep the hyphen",
        "algorithm": "diagram.mathpix_subtype (260)",
        "pseudocode": "diagram.mathpix_subtype (260)",
        "chemistry": "diagram.mathpix_subtype (260)",
        "chemistry_reaction": "diagram.mathpix_subtype (260)",
        "triangle": "diagram.mathpix_subtype (260)",
        "logo": "diagram.mathpix_subtype (260)",
        "line": "picture.mathpix_subtype (260) — chart kind",
        "analytical": "picture.mathpix_subtype (260) — chart kind",
        "column": "picture.mathpix_subtype (260) — chart kind",
        "scatter": "picture.mathpix_subtype (260) — chart kind",
        "bar": "picture.mathpix_subtype (260) — chart kind",
        "area": "picture.mathpix_subtype (260) — chart kind",
        "pie": "picture.mathpix_subtype (260) — chart kind",
    },
    "column": {
        "0": "sidenote.py — a column-0 `column` line IS the sidenote "
             "(15,819 lines)",
    },
}

#: field -> value -> why nothing reads it.
IGNORED_VALUES: dict[str, dict[str, str]] = {
    "subtype": {
        "margin_note": "sub-element: 1,866 lines on `page_info`, 21 docs. "
                       "page_info is a paragraph break and produces no object, "
                       "so there is nothing to hang the value on. The words "
                       "themselves are reached through geometry_columns' own "
                       "margin_role, which is a separate and read path.",
        "qr_code": "non-content: 15 lines on `page_info`. A scannable mark.",
        "checkbox": "non-content: 53 lines on `form_field`, which the type "
                    "contract already lists as UI furniture with no prose.",
        "box": "non-content: 32 lines on `form_field`. As above.",
        "dotted": "non-content: 17 lines on `form_field`. As above.",
        "parentheses": "non-content: 6 lines on `form_field`. As above.",
        "dashed": "non-content: 4 lines on `form_field`. As above.",
        "circle": "non-content: 1 line on `form_field`. As above.",
        "big_capital_letter": "typographic: 23 lines, 13 docs. A drop cap. The "
                              "letter is in `text` and reaches the paragraph "
                              "either way; only the fact that it was set large "
                              "is dropped, and nothing renders drop caps.",
        "vertical": "typographic: 5 lines on `simple_cell`, 3 docs. A cell "
                    "whose text is set sideways. The text is collected by "
                    "table.py; the rotation is not, and no projector can "
                    "express it.",
    },
    "column": {
        "1": "container only: 56 `column` lines. sidenote.py treats only "
             "column 0 as a sidenote; the children of the others are "
             "separately typed and read on their own (809 text, 74 page_info, "
             "72 list_item, 37 math, …), so the words survive and only the "
             "grouping is lost — the same disposal the type contract gives "
             "multiple_choice_block.",
        "2": "container only: 16 lines. Children separately typed and read on "
             "their own; only the column grouping is lost.",
        "3": "container only: 7 lines. Children separately typed and read on "
             "their own; only the column grouping is lost.",
        "6": "container only: 1 line. Its children are separately typed and "
             "read on their own; only the column grouping is lost.",
    },
}


def corpus_values() -> dict:
    """{field: {value: count}} as last measured, for the enumerable fields."""
    data = json.loads(VALUE_INVENTORY.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")
            and not k.endswith("_docs")}


def value_violations() -> list[tuple]:
    """(field, value, count) for corpus values that are neither handled nor
    ignored, worst first. This is the check `subtype` would have failed."""
    out = []
    for field, counts in corpus_values().items():
        known = set(HANDLED_VALUES.get(field, {})) | set(IGNORED_VALUES.get(field, {}))
        for value, n in counts.items():
            if str(value) not in known:
                out.append((field, str(value), n))
    return sorted(out, key=lambda r: -r[2])


def unenumerated_read_fields() -> list[str]:
    """Read fields that are neither enumerated nor excused. Must be empty:
    a value contract covering 2 of 16 fields and calling itself complete is
    the omission it was built to prevent."""
    covered = set(HANDLED_VALUES) | set(IGNORED_VALUES) | set(UNBOUNDED_FIELDS)
    return sorted(f for f in CLAIMED_FIELDS if f not in covered)
