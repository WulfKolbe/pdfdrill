"""
ParagraphProcessor (procOrder 13).

Walks the mathpix_lines stream within each page and groups consecutive lines
of type 'text' or 'title' into Paragraph DocObjects. A paragraph is broken
when:
  - A non-text line is encountered (equation, math, table, figure, header,
    page_info, footnote, TOC, etc.).
  - The page changes.
  - We enter or exit a LaTeX `abstract` environment (those lines belong to
    the Abstract DocObject, not to running prose).
  - The line's tesseract layout group (block_num, par_num) changes — the
    enriched keyless OCR path preserves the TSV hierarchy per line, which is
    the paragraph signal MathPix lines don't need (they carry no par_num, so
    their grouping is unaffected).

The Paragraph DocObject's surface realization spans the line anchors of the
first to the last contributing line, so all of the original OCR per-line
metadata (font, region, page, column) remains accessible via the stream.
"""
from __future__ import annotations

import re
import statistics
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization
from ..text_utils import STATED_JOIN, join_stated


# Lines that always break a paragraph but never contribute to it.
_BREAK_TYPES = {
    "page_info", "section_header", "footnote",
    # An arXiv stamp down the left margin is not a sentence in section 1.
    "rotated_text",
    "table_of_contents_container", "table_of_contents_item",
    "table_of_contents_number", "table_of_contents_row",
    "table", "table_row", "table_column", "simple_cell", "complex_cell",
    "figure", "diagram", "chart",
    "equation", "math", "equation_number",
    "pseudocode", "qed_symbol", "figure_label", "caption",
    # 259 — a code listing interrupts prose exactly as a list does (248).
    "code",
    "column",  # sidenotes
    "abstract",
    # 248: a typed list item must END the paragraph it interrupts. It was in
    # neither _PROSE_TYPES nor here, so 80,035 lines across 882 documents were
    # invisible in both directions — they contributed nothing AND did not
    # break the prose run they sat inside, silently welding the text before a
    # list to the text after it.
    "list_item",
}

# Lines that may contribute to a paragraph.
_PROSE_TYPES = {"text", "title", "quote"}

# A figure/table caption that MathPix types as plain `text` (its figure_label
# lines are often EMPTY): same column, same font, CONTINUOUS line numbering —
# the only separators are this lexical pattern and the vertical gap after the
# caption (1206.0238 p3: caption + next paragraph merged into one unit).
_CAPTION_START = re.compile(
    r"^(?:Figure|Fig\.?|Table|Tab\.?|Abbildung|Abb\.?|Tafel|Bild)"
    r"\s*\.?\s*\d+(?:\.\d+)*\s*[.:]", re.I)

_ABSTRACT_BEGIN = re.compile(r"\\begin\{abstract\}|\\section\*\{[Aa][Bb][Ss][Tt][Rr][Aa][Cc][Tt]\}")
_ABSTRACT_END = re.compile(r"\\end\{abstract\}")


def _body_edges(stream, prose_types) -> dict:
    """Per page: the body text's LEFT EDGES -- one per column -- and the
    distance a line has to clear to read as a paragraph's FIRST line.

    A paragraph break is a typographic fact, and the reading may not state it.
    MathPix states it with a leading blank in `text_display`; the enriched
    keyless OCR path states it with `par_num`. THE PDF'S OWN TEXT LAYER STATES
    NEITHER, so every prose line on a page joined one paragraph: 11 pages of a
    two-column paper came out as 12 Paragraph objects, and the markdown was 13
    lines at a median of 1,688 characters (arxiv.2602.06992, 2026-11-10).

    What the page itself states is the INDENT. A first line starts an em or two
    right of its column's body edge; a continuation starts at the edge. An edge
    is an x the page RETURNS TO, so it is found by frequency -- a first-line
    indent is used once per paragraph and never dominates.

    The threshold is the median line HEIGHT, which is one em in whatever units
    the reading uses: points for the text layer (~11pt), pixels for MathPix
    (~42px). So no page width is needed and both readings are measured alike.
    """
    per_page: dict = {}
    for anchor in stream.anchors:
        payload = stream.payload[anchor]
        if payload.get("type") not in prose_types:
            continue
        region = payload.get("region") or {}
        x, h = region.get("top_left_x"), region.get("height")
        if x is None:
            continue
        per_page.setdefault(payload.get("_page"), []).append(
            (float(x), float(h or 0)))

    out: dict = {}
    for page, rows in per_page.items():
        xs = [x for x, _ in rows]
        hs = [h for _, h in rows if h > 0]
        if not hs or len(xs) < 4:
            continue
        em = statistics.median(hs)
        if em <= 0:
            continue
        step = max(em * 0.5, 0.5)

        buckets: dict = {}
        for x in xs:
            k = int(round(x / step))
            buckets[k] = buckets.get(k, 0) + 1
        floor = max(3, int(0.10 * len(xs)))
        edges = sorted(k * step for k, n in buckets.items() if n >= floor)
        if edges:
            out[page] = (edges, em)
    return out


def _is_first_line(x, page, edges: dict) -> bool:
    """True when the page itself says a paragraph starts at this line: its left
    edge sits an em or more right of its OWN column's body edge.

    Per column. The right column's edge is far right of the left column's, so
    measured against one page-wide edge every right-column line reads as
    indented.

    A SECOND SIGNAL WAS TRIED AND REJECTED BY MEASUREMENT. The idea was to
    require the PREVIOUS line to stop short of its column's right margin, on
    the reasoning that a paragraph's last line is short while a mid-paragraph
    line runs to the margin -- so a hanging indent or a wide inline equation
    would stop fooling the indent test. Scored against the genuine MathPix
    markdown of arxiv.2602.06992, whose paragraph boundaries are ground truth
    (2026-11-10, default text-layer route):

        variant                    paragraphs  truth starts  welds
        no indent rule                     12         6/238     10
        indent + short predecessor         69        33/238     15
        indent alone                       95        48/238      6

    The extra signal removed 23 breaks of which only 3 were wrong, so it cost
    20 correct paragraph starts to buy 3 -- and it WELDED more, not fewer. It
    is not in the code; this note is here so it is not re-invented.
    """
    if x is None or page not in edges:
        return False
    cols, em = edges[page]
    at_or_left = [e for e in cols if e <= x + em * 0.5]
    if not at_or_left:
        return False
    if (float(x) - at_or_left[-1]) <= em:
        return False
    return True

class ParagraphProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        items: list[dict[str, Any]] = []
        edges = _body_edges(stream, _PROSE_TYPES)

        current: Optional[dict[str, Any]] = None
        current_page: Optional[int] = None
        in_abstract = False
        # DOES THIS READING TYPE ITS ABSTRACT? It decides which fence closes
        # the abstract below, and it is a property of the READER, not of the
        # document, so it is answered once.
        typed_abstract = any(
            (stream.payload.get(a) or {}).get("type") == "abstract"
            for a in stream.anchors)

        def flush() -> None:
            nonlocal current
            if current is not None and current["lines"]:
                items.append(current)
            current = None

        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            page = payload.get("_page")
            ltype = payload.get("type")

            if page != current_page:
                flush()
                current_page = page

            # Track abstract environment via the abstract line type itself
            # (most reliable signal in this corpus).
            if ltype == "abstract":
                in_abstract = True
                flush()
                self.bump("lines_typed_abstract")
                continue

            # WHERE A READING TYPES ITS ABSTRACT, THE TYPE IS THE FENCE AT BOTH
            # ENDS. `in_abstract` was latched on above and cleared only by
            # `_ABSTRACT_END` — the literal `\end{abstract}`, which only a
            # reading carrying LaTeX markup contains. MathPix types its
            # abstract as plain `text`, so the regex released the latch and in
            # the corpus this was written against the bug could not appear. The
            # glyph reader DOES type it, and the first such line then shut the
            # paragraph builder for the rest of the document: measured on the
            # owner's sensors-15-23763, `lines_skipped_inside_an_abstract` 874,
            # 4 Paragraph objects holding 460 of the reading's 69,566 prose
            # characters, a 66 KB markdown file down to 9 KB. Exactly the three
            # documents of the 15 with typed abstracts lost their text.
            if typed_abstract and in_abstract:
                in_abstract = False

            # 811 — a line the ListProcessor already folded into a ListItem is
            # not prose. 248 broke the paragraph on the `list_item` CONTAINER,
            # but a container's children are typed `text` — a prose type — so
            # they kept contributing, and the list text ended up in the model
            # twice: once as a ListItem, once inside a Paragraph. The stamp is
            # set (procOrder 10, before this one at 13) only for containers
            # whose content already holds the child's words, so nothing is lost.
            if payload.get("_in_list_item"):
                flush()
                self.bump("lines_owned_by_a_list_item")
                continue

            # 811 — a `text` line HeaderProcessor promoted to a Section (a
            # back-matter label, or a number-series gap its own document
            # witnesses). Its type is still `text`, so without this it would be
            # a heading AND a paragraph, and the heading would read as the first
            # sentence of the prose beneath it.
            if payload.get("_promoted_heading"):
                flush()
                self.bump("lines_promoted_to_a_heading")
                continue

            text = payload.get("text_display") or payload.get("text") or ""

            # Defensive: text-typed lines may also delimit the abstract.
            if ltype in _PROSE_TYPES:
                if _ABSTRACT_BEGIN.search(text):
                    in_abstract = True
                    flush()
                    continue
                if _ABSTRACT_END.search(text):
                    in_abstract = False
                    flush()
                    continue

            if in_abstract:
                # Skip while inside an abstract block.
                flush()
                self.bump("lines_skipped_inside_an_abstract")
                continue

            if ltype in _BREAK_TYPES:
                flush()
                self.bump("lines_of_a_breaking_type")
                continue
            if ltype not in _PROSE_TYPES:
                flush()
                self.bump("lines_of_a_non_prose_type")
                continue

            # Skip a "title" line whose only content is the literal word
            # 'Abstract' or 'ABSTRACT' (heading-like markers).
            stripped = text.strip()
            if ltype == "title" and re.match(r"^A[Bb][Ss][Tt][Rr][Aa][Cc][Tt]$", stripped):
                flush()
                continue

            group = (payload.get("block_num"), payload.get("par_num"))
            region = payload.get("region") or {}
            y, h = region.get("top_left_y"), region.get("height")
            x0 = region.get("top_left_x")
            if current is not None:
                if _is_first_line(x0, page, edges):
                    # the page's own indent says a new paragraph starts here
                    flush()
                    self.bump("paragraphs_started_by_an_indent")
                elif group != (None, None) and group != current.get("group"):
                    flush()
                elif (_CAPTION_START.match(stripped)
                        and current.get("kind") != "caption"):
                    # a caption starts its OWN paragraph, never rides the tail
                    # of the previous one
                    flush()
                elif (current.get("kind") == "caption" and y is not None
                        and current.get("_last_y") is not None):
                    # the caption ends at the first oversized vertical gap —
                    # applied ONLY inside captions so general paragraphing
                    # keeps its existing behavior
                    gap = y - current["_last_y"]
                    pitches = current.get("_pitches") or []
                    ref = sum(pitches) / len(pitches) if pitches else None
                    if ((ref and gap > 1.6 * ref)
                            or (ref is None and h and gap > 1.8 * h)):
                        flush()

            if current is None:
                current = {
                    "page": page,
                    "start_anchor": anchor,
                    "end_anchor": anchor,
                    "lines": [(anchor, text, payload)],
                    "text": text,
                    "from_line_index": payload.get("_line_index"),
                    "to_line_index": payload.get("_line_index"),
                    "group": group,
                    "kind": ("caption" if _CAPTION_START.match(stripped)
                             else "prose"),
                    "_last_y": y,
                    "_pitches": [],
                }
            else:
                if y is not None and current.get("_last_y") is not None:
                    current["_pitches"].append(y - current["_last_y"])
                if y is not None:
                    current["_last_y"] = y
                current["end_anchor"] = anchor
                current["lines"].append((anchor, text, payload))
                # 256/T-0010 — the line's own subtype states how it attaches to
                # the one before it. This used to be an unconditional space,
                # which put one into the middle of every hyphenation-broken
                # word: 31 of 143 stated no-space joins on Killing, Math. Ann.
                # 33 (1889) read "Transformations gruppen". The rule was already
                # written down in STATED_JOIN and already tested — against the
                # Dehyphenate MUTATOR, which no build command runs. props.text
                # is composed here, so the join has to be honoured here.
                # A line that states nothing keeps the join this composer
                # always did, verbatim: `text_display`'s own leading "\n\n"
                # is MathPix saying the line begins a block, and all 34
                # numbered rules of texbook Appendix G start one that way.
                action = STATED_JOIN.get(payload.get("subtype") or "")
                if action is None:
                    current["text"] += " " + text
                else:
                    head, chunk, dropped = join_stated(
                        current["text"], text, action)
                    current["text"] = head + chunk
                    if dropped:
                        current["soft_breaks_joined"] = (
                            current.get("soft_breaks_joined", 0) + 1)
                current["to_line_index"] = payload.get("_line_index")

        flush()
        return items

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        paragraph_no = self.bump("paragraphs_created")
        obj = DocObject(
            type="Paragraph",
            props={
                "paragraph_index": paragraph_no,
                "kind": item.get("kind", "prose"),
                "page": item["page"],
                "from_line_index": item["from_line_index"],
                "to_line_index": item["to_line_index"],
                "text": item["text"].strip(),
                "num_lines": len(item["lines"]),
                "bibkey": self.bibkey,
            },
        )
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["start_anchor"],
            end=item["end_anchor"],
            role="surface",
        ))
        return obj
