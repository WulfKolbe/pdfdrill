"""
ListProcessor (procOrder 10).

Detects list items inside text lines by looking at a leading marker:
  - Bullets: -, *, •, ○, ▪, etc.
  - Numbered: '1.', '2)', ...
  - Lettered: 'a.', 'b)', ...
Each becomes a ListItem DocObject. Adjacent items at the same nesting level
could in principle be grouped into a List object, but the simple TS port did
not do this; we keep parity.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization


_BULLET = re.compile(r"^([•○▪\-*\u2022\u2023\u25E6\u2043\u2219])\s+")
_NUMBERED = re.compile(r"^(\d+[.)])\s+")
_LETTERED = re.compile(r"^([a-zA-Z][.)])\s+")


def _detect_marker(text: str) -> Optional[str]:
    for rx in (_BULLET, _NUMBERED, _LETTERED):
        m = rx.match(text)
        if m:
            return m.group(1)
    return None


class ListProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        items: list[dict[str, Any]] = []
        global_index = 0

        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            if payload.get("type") != "text":
                continue
            text = (payload.get("text") or "").strip()
            marker = _detect_marker(text)
            if not marker:
                continue
            content = re.sub(
                r"^" + re.escape(marker) + r"\s+", "", text
            ).strip()
            global_index += 1
            items.append({
                "anchor": anchor,
                "marker": marker,
                "content": content,
                "page": payload.get("_page"),
                "line_index": payload.get("_line_index"),
                "list_index": global_index,
            })
        return items

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        obj = DocObject(
            type="ListItem",
            props={
                "marker": item["marker"],
                "content": item["content"],
                "page": item["page"],
                "line_index": item["line_index"],
                "list_index": item["list_index"],
                "bibkey": self.bibkey,
            },
        )
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface",
        ))
        self.bump("list_items_created")
        return obj
