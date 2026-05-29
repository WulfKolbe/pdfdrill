"""
SidenoteProcessor (procOrder 5).

A sidenote in this corpus is a line of type='column' (typically column 0 with
text children). We create a Sidenote DocObject per such line, concatenating
the children's text with naive de-hyphenation across line breaks.
"""
from __future__ import annotations

from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization


class SidenoteProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        by_id = self.build_line_index(doc)
        anchor_by_id = self.build_anchor_index(doc)
        items: list[dict[str, Any]] = []

        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            if payload.get("type") != "column":
                continue
            if payload.get("children_ids") in (None, []):
                continue
            col = payload.get("column")
            if col not in (0, None):
                continue
            child_anchors, texts = [], []
            for cid in payload["children_ids"]:
                child = by_id.get(cid)
                if not child or child.get("type") != "text":
                    continue
                child_anchor = anchor_by_id.get(cid)
                if child_anchor is not None:
                    child_anchors.append(child_anchor)
                texts.append(child.get("text_display") or child.get("text") or "")
            content = self._concat_with_softhyphens(texts)
            items.append({
                "anchor": anchor,
                "child_anchors": child_anchors,
                "content": content.strip(),
                "page": payload.get("_page"),
            })
        return items

    @staticmethod
    def _concat_with_softhyphens(parts: list[str]) -> str:
        if not parts:
            return ""
        out = parts[0]
        for nxt in parts[1:]:
            if nxt.startswith(" "):
                out += nxt
            elif out.endswith("-"):
                out = out[:-1] + nxt   # remove the soft hyphen
            else:
                out += " " + nxt
        return out

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        obj = DocObject(
            type="Sidenote",
            props={
                "content": item["content"],
                "page": item["page"],
                "bibkey": self.bibkey,
            },
        )
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface",
        ))
        if item["child_anchors"]:
            obj.add_realization(Realization(
                stream=self.LINES_STREAM,
                start=item["child_anchors"][0],
                end=item["child_anchors"][-1],
                role="children",
            ))
        self.bump("sidenotes_created")
        return obj
