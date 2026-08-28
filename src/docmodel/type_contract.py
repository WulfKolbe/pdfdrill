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
