"""
HeaderProcessor (procOrder 8).

Lines of type='section_header' usually have a single child carrying both a
clean caption (`text`) and a LaTeX command (`text_display`, e.g.
`\\section*{...}`). We create one Section DocObject per header with level,
caption, and command kind.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization


_CMD_RE = re.compile(
    r"\\(section|subsection|subsubsection|paragraph|subparagraph)\*?\{([^}]*)\}"
)
_CMD_ONLY_RE = re.compile(
    r"\\(section|subsection|subsubsection|paragraph|subparagraph)\*?"
)

_LEVEL = {
    "section": 1, "subsection": 2, "subsubsection": 3,
    "paragraph": 4, "subparagraph": 5,
}


class HeaderProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        by_id = self.build_line_index(doc)
        items: list[dict[str, Any]] = []

        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            if payload.get("type") != "section_header":
                continue
            kids = payload.get("children_ids") or []
            if not kids:
                continue
            child = by_id.get(kids[0])
            if not child:
                continue

            child_text = child.get("text") or ""
            child_display = child.get("text_display") or ""

            cmd, caption = self._parse_header(child_text, child_display)
            items.append({
                "anchor": anchor,
                "page": payload.get("_page"),
                "line_index": payload.get("_line_index"),
                "cmd": cmd,
                "caption": caption,
                "level": _LEVEL.get(cmd, 1),
            })
        return items

    @staticmethod
    def _parse_header(text: str, display: str) -> tuple[str, str]:
        # Strategy 1: display contains a full \section*{Caption} pattern.
        m = _CMD_RE.search(display)
        if m:
            return m.group(1), m.group(2)
        # Strategy 2: display contains a bare \section* command and text has the caption.
        m2 = _CMD_ONLY_RE.search(display)
        if m2:
            return m2.group(1), text.strip()
        # Strategy 3: fall back to whatever text we have.
        return "section", text.strip() or display.strip()

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        obj = DocObject(
            type="Section",
            props={
                "level": item["level"],
                "caption": item["caption"],
                "cmd": item["cmd"],
                "page": item["page"],
                "line_index": item["line_index"],
                "bibkey": self.bibkey,
            },
        )
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface",
        ))
        self.bump("sections_created")
        return obj
