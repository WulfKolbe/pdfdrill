"""
AbstractProcessor (procOrder 6).

Each line of type='abstract' becomes an Abstract DocObject. Multiple abstract
lines collapse into one DocObject when they appear contiguously.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization


_BEGIN_RE = re.compile(r"\\begin\{abstract\}")
_END_RE = re.compile(r"\\end\{abstract\}")
_SECTION_RE = re.compile(r"\\section\*\{(?:Abstract|ABSTRACT|abstract)\}")


class AbstractProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        by_id = self.build_line_index(doc)
        items: list[dict[str, Any]] = []

        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            if payload.get("type") != "abstract":
                continue
            if payload.get("children_ids"):
                parts = []
                for cid in payload["children_ids"]:
                    child = by_id.get(cid)
                    if not child:
                        continue
                    parts.append(child.get("text_display") or child.get("text") or "")
                text = " ".join(parts)
            else:
                text = payload.get("text_display") or payload.get("text") or ""
            text = _BEGIN_RE.sub("", text)
            text = _END_RE.sub("", text)
            text = _SECTION_RE.sub("", text)
            items.append({
                "anchor": anchor,
                "text": text.strip(),
                "page": payload.get("_page"),
            })
        return items

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        if not item["text"]:
            return None
        obj = DocObject(
            type="Abstract",
            props={
                "text": item["text"],
                "page": item["page"],
                "bibkey": self.bibkey,
            },
        )
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface",
        ))
        self.bump("abstracts_created")
        return obj
