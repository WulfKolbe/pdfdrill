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
        "table", "table_row", "table_column",
        "simple_cell", "complex_cell", "table_spanning_cell",
        "table_split_cell",
    }),
    # 676 (review B7): `column` was here and is NOT a table --- it is a
    # page-layout column, which `paragraph.py:41` annotates "sidenotes".
    # Zero measured impact (16,016 `column` lines corpus-wide carry no
    # inline math at all), so this is about the set's claim to be
    # checkable against the sentence that asked for it.
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


def caption_anchors(doc, stream_name: str = "mathpix_lines") -> set:
    r"""Every line anchor covered by a figure/table CAPTION.

    676 (review B1). MathPix types most captions plain `text`, not
    `figure_label` --- `paragraph.py:54-61` says so in its own comment
    ("its figure_label lines are often EMPTY") and defines `_CAPTION_START`
    to find them. Measured: 11,758 caption-start lines carrying 2,810
    inline-math occurrences, against 2,382 on `figure_label` --- the half
    that a type-based rule misses is larger than the half it catches.

    A caption cannot be recognised line by line. Its FIRST line matches
    `_CAPTION_START`; its continuations match nothing, and end at a
    vertical gap `ParagraphProcessor` measures against the caption's own
    line pitch. A line-level approximation of that (everything prose after
    a caption start, until a non-prose line) over-reaches by an order of
    magnitude: 110,526 lines where the real spans hold far fewer.

    So the span is taken from the model, where it already exists:
    `ParagraphProcessor` stamps `kind: "caption"` on the Paragraph and that
    Paragraph's realization IS the caption's line range. One authority, no
    second detector.
    """
    out = set()
    stream = doc.streams.get(stream_name) if getattr(doc, "streams", None) else None
    if stream is None:
        return out
    for p in doc.objects_of_type("Paragraph"):
        if (getattr(p, "props", None) or {}).get("kind") != "caption":
            continue
        for r in p.realizations:
            if (r.stream != stream_name or r.role != "surface"
                    or r.start is None):
                continue
            out.update(stream.slice_anchors(r.start, r.end))
    return out


def no_transclusion_site(obj, doc, stream_name: str = "mathpix_lines",
                         captions: "set | None" = None) -> bool:
    """True when no surface occurrence of `obj` may host a transclusion.

    An occurrence is disqualified two ways: its line TYPE is forbidden
    (`NO_TRANSCLUDE`), or it lies inside a caption's span
    (`caption_anchors`) --- a caption is a figure/image label whatever
    MathPix typed its lines.

    False for an object with no surface realization at all (a synthetic
    formula built from paragraph text has none, and paragraph text is prose
    by construction) --- absence of evidence is not a refusal.

    676 (review B4) --- ON THE QUESTION THIS ASKS. The review observed that
    "no occurrence the rule permits" is not the same as "no occurrence that
    can actually host a transclusion": a `diagram`, `chart` or `qed_symbol`
    occurrence rescues an object here, and none of those types is in
    `ParagraphProcessor._PROSE_TYPES`, so none can ever carry one (38 rows
    of the published 36,158, 0.11%). That is correct, and asking the
    stricter question was DELIBERATELY not done: `list_item` is not a prose
    type either, and it carries 22,604 inline-math occurrences that are
    real inline formulas in a list. The stricter question drops those too.
    So this asks what the requirement named, and the gap is recorded rather
    than closed by widening a set nobody asked to widen.
    """
    surfaces = [r for r in getattr(obj, "realizations", ()) or ()
                if r.stream == stream_name and r.role == "surface"
                and r.start is not None]
    if not surfaces:
        return False
    if captions is None:
        captions = caption_anchors(doc, stream_name)
    for r in surfaces:
        if r.start in captions:
            continue
        if hosts_transclusion(line_type_at(doc, r.start, stream_name)):
            return False
    return True
