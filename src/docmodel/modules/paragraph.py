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

The Paragraph DocObject's surface realization spans the line anchors of the
first to the last contributing line, so all of the original OCR per-line
metadata (font, region, page, column) remains accessible via the stream.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization


# Lines that always break a paragraph but never contribute to it.
_BREAK_TYPES = {
    "page_info", "section_header", "footnote",
    "table_of_contents_container", "table_of_contents_item",
    "table_of_contents_number", "table_of_contents_row",
    "table", "table_row", "table_column", "simple_cell", "complex_cell",
    "figure", "diagram", "chart",
    "equation", "math", "equation_number",
    "pseudocode", "qed_symbol", "figure_label", "caption",
    "column",  # sidenotes
    "abstract",
}

# Lines that may contribute to a paragraph.
_PROSE_TYPES = {"text", "title", "quote"}

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
                continue

            if ltype in _BREAK_TYPES:
                flush()
                continue
            if ltype not in _PROSE_TYPES:
                flush()
                continue

            # Skip a "title" line whose only content is the literal word
            # 'Abstract' or 'ABSTRACT' (heading-like markers).
            stripped = text.strip()
            if ltype == "title" and re.match(r"^A[Bb][Ss][Tt][Rr][Aa][Cc][Tt]$", stripped):
                flush()
                continue

            if current is None:
                current = {
                    "page": page,
                    "start_anchor": anchor,
                    "end_anchor": anchor,
                    "lines": [(anchor, text, payload)],
                    "text": text,
                    "from_line_index": payload.get("_line_index"),
                    "to_line_index": payload.get("_line_index"),
                }
            else:
                current["end_anchor"] = anchor
                current["lines"].append((anchor, text, payload))
                current["text"] += " " + text
                current["to_line_index"] = payload.get("_line_index")

        flush()
        return items

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        paragraph_no = self.bump("paragraphs_created")
        obj = DocObject(
            type="Paragraph",
            props={
                "paragraph_index": paragraph_no,
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
