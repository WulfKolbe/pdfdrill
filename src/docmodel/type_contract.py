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
}

#: type -> why nothing reads it. GAP: means content is being dropped.
IGNORED: dict[str, str] = {
    "code": "GAP: 44,689 lines in 205 documents. Source listings and logic "
            "programs, dropped entirely. docmodel's only 'code' is diagram.py's "
            "TikZ subtype, which is unrelated. This is the largest unread type "
            "in the corpus and it is content, not decoration.",
    "molecule": "GAP: 10 lines in 4 documents. A CDN image link to a rendered "
                "chemical structure — the same shape a Picture carries, so the "
                "content exists and nothing collects it.",
    "table_split_cell": "GAP: 10 lines in 7 documents. A \\backslashbox "
                        "diagonal header cell with one child. It belongs in "
                        "table.py's _CELL_TYPES beside simple/complex/spanning "
                        "and is missing from it.",
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
    "cell_row": "pdfdrill.table_structure",
    "cell_row_span": "pdfdrill.table_structure",
}

#: field -> why nothing reads it. GAP: means information is being lost.
IGNORED_FIELDS: dict[str, str] = {
    "cnt": "GAP: 3,465,341 lines. A four-point polygon — the line's actual "
           "quadrilateral, e.g. [[996,2714],[1078,2714],[1078,2750],[996,2750]] "
           "— where `region` is only its axis-aligned box. For rotated or "
           "skewed lines the two differ, and every crop we build uses the box. "
           "docpack packs it; nothing reads it.",
    "font_size": "GAP: 3,463,072 lines carry a pixel height (31, 29, 28, 22…). "
                 "Header detection is done on text patterns alone, and the "
                 "signal that would settle a heading from a bold run is sitting "
                 "unread on every line.",
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
