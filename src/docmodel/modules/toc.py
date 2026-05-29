"""
TocProcessor (procOrder 6).

Collects all `table_of_contents_*` lines (container, row, item, number) and
emits a single Toc DocObject containing the concatenated entries, with
realizations into each contributing line.
"""
from __future__ import annotations

from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization


_TOC_TYPES = {
    "table_of_contents_container",
    "table_of_contents_row",
    "table_of_contents_item",
    "table_of_contents_number",
}


class TocProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        by_id = self.build_line_index(doc)

        toc_anchors = []
        entry_strings: list[str] = []
        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            if payload.get("type") not in _TOC_TYPES:
                continue
            toc_anchors.append(anchor)
            if payload.get("children_ids"):
                parts = []
                for cid in payload["children_ids"]:
                    child = by_id.get(cid)
                    if not child:
                        continue
                    parts.append(child.get("text_display") or child.get("text") or "")
                entry_strings.append(" ".join(parts).strip())
            else:
                entry_strings.append(
                    (payload.get("text_display") or payload.get("text") or "").strip()
                )

        entry_strings = [s for s in entry_strings if s]
        if not toc_anchors:
            return []
        return [{
            "anchors": toc_anchors,
            "entries": entry_strings,
        }]

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        obj = DocObject(
            type="Toc",
            props={
                "entries": item["entries"],
                "bibkey": self.bibkey,
            },
        )
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchors"][0], end=item["anchors"][-1],
            role="surface",
        ))
        self.bump("toc_created")
        return obj
