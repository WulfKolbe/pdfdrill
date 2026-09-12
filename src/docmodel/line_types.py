"""MathPix line types that must never host a transcluded formula.

WHY THIS EXISTS
---------------
A `{{Bibkey_FO0191||FO}}` transclusion is a claim about PROSE: "at this
point in a sentence there is an inline formula, and here it is." MathPix
types every line it emits, and most of its types are not sentences at all
--- a table cell, a section heading, a title, a table-of-contents entry, a
figure label. Math inside those is already carried whole by the object that
OWNS the line (a Table keeps the entire `\\begin{tabular}` in `mathpix_text`
/ `latex_code`; a Section keeps its heading in `caption`), so mining the
same characters a second time into a Formula produces a duplicate that no
sentence names.

Measured 2026-09-12 over the 1,367-document library, counting inline-math
occurrences (`formula._MATH_RE`, footnote markers excluded) on lines whose
type is NOT `equation`/`math`:

    text                 879,620      simple_cell        138,097
    table                188,035      complex_cell        46,685
    list_item             22,604      diagram             10,307
    qed_symbol             8,277      pseudocode           6,529
    table_spanning_cell    3,595      figure_label         2,382
    chart                  1,827      page_info            1,650
    table_of_contents_item 1,391      section_header       1,384
    code                   1,108      form_field             591
    equation_number          476      footnote               389
    authors                   69      title                   19
    table_split_cell           6      quote                    6
    table_of_contents_number   3

The five families below --- the ones named as forbidden --- are 17 line
types and account for 381,597 of those 1,315,050 occurrences (29.0%):
table 376,418, figure_label 2,382, toc 1,394, section_header 1,384,
title 19.

WHAT THIS IS NOT
----------------
This is not about WHERE LaTeX is stored. Both readings of a line's math
(`latex` and `latex_original`, `latex_code` and `mathpix_text`) stay exactly
where PROPS.md says they live, on the object that owns the line. This set
governs one thing only: whether an occurrence is a transclusion SITE.

NEXT WEEK'S SHAPE
-----------------
This set is an approximation of the subtractive pipeline: a line already
claimed by TableProcessor / HeaderProcessor / TocProcessor / the caption
layer would simply not be offered to FormulaProcessor, and no name-based
exclusion would be needed. Until each pass reads the previous pass's
leftovers, the exclusion is stated by type. When that lands, delete this
module rather than growing it.
"""
from __future__ import annotations

#: The forbidden families, kept SEPARATE and named the way they were named
#: as requirements, so a reader can check the set against the sentence that
#: asked for it instead of against a flat list of 14 strings.
NON_PROSE_HOSTS: dict[str, frozenset[str]] = {
    # "any kind of table" --- every cell/row/column type MathPix emits,
    # including the whole-region `table` line that carries the tabular.
    "table": frozenset({
        "table", "table_row", "table_column", "column",
        "simple_cell", "complex_cell", "table_spanning_cell",
        "table_split_cell",
    }),
    # "section heading"
    "section_header": frozenset({"section_header"}),
    # "titles"
    "title": frozenset({"title"}),
    # "toc entries" --- the container and its three row/item/number parts.
    "toc": frozenset({
        "table_of_contents_container", "table_of_contents_item",
        "table_of_contents_row", "table_of_contents_number",
    }),
    # "figure and image labels" --- the label, NOT the figure itself. A
    # `diagram`/`chart` line is an image REGION whose math is its content;
    # only the text that LABELS an image is excluded here.
    "figure_label": frozenset({
        "figure_label", "diagram_info", "x_axis_tick_label",
    }),
}

#: Flat membership test. 17 types.
NO_TRANSCLUDE: frozenset[str] = frozenset().union(*NON_PROSE_HOSTS.values())


def family(line_type) -> "str | None":
    """Which forbidden family a line type belongs to, or None if it hosts.

    Returns the requirement's own word ("table", "toc", ...) so a refusal
    can say WHICH rule it applied rather than "excluded".
    """
    for name, members in NON_PROSE_HOSTS.items():
        if line_type in members:
            return name
    return None


def hosts_transclusion(line_type) -> bool:
    """True when a formula occurring on this line is a transclusion site."""
    return line_type not in NO_TRANSCLUDE


def line_type_at(doc, anchor, stream_name: str = "mathpix_lines"):
    """The MathPix `type` of one anchor, or None when it cannot be read."""
    stream = doc.streams.get(stream_name) if getattr(doc, "streams", None) else None
    if stream is None:
        return None
    payload = stream.payload.get(anchor)
    return payload.get("type") if payload else None


def prose_realizations(obj, doc, stream_name: str = "mathpix_lines") -> list:
    """The object's surface realizations that sit on a transcludable line.

    An object may occur many times --- `FormulaProcessor` de-duplicates by
    LaTeX, so one Formula can be realized in a table cell AND in a sentence.
    The exclusion is per OCCURRENCE, never per object: the table occurrence
    is not a transclusion site, the sentence occurrence still is.
    """
    out = []
    for r in getattr(obj, "realizations", ()) or ():
        if (r.stream != stream_name or r.role != "surface"
                or r.start is None):
            continue
        if hosts_transclusion(line_type_at(doc, r.start, stream_name)):
            out.append(r)
    return out


def only_non_prose(obj, doc, stream_name: str = "mathpix_lines") -> bool:
    """True when EVERY surface occurrence of `obj` is on a forbidden line.

    False for an object with no surface realization at all (a synthetic
    formula built from paragraph text has none, and paragraph text is prose
    by construction) --- absence of evidence is not a refusal.
    """
    surfaces = [r for r in getattr(obj, "realizations", ()) or ()
                if r.stream == stream_name and r.role == "surface"
                and r.start is not None]
    if not surfaces:
        return False
    return not prose_realizations(obj, doc, stream_name)
