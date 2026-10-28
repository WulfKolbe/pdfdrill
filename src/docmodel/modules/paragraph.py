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


class ParagraphProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        items: list[dict[str, Any]] = []

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
            if current is not None:
                if group != (None, None) and group != current.get("group"):
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
