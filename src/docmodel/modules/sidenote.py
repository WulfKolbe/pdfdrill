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


#: A `column` is a sidenote only if some column on its page is at least this
#: much wider. Two equal body columns differ by a few points; a margin note is
#: a fraction of the measure. 1.5 separates those two cases and nothing in
#: between has been measured, so it is stated rather than tuned.
_SIDENOTE_WIDTH_RATIO = 1.5


class SidenoteProcessor(BaseModule):
    @staticmethod
    def _is_narrow_for_its_page(stream, payload) -> bool:
        """True when a WIDER `column` shares this one's page."""
        w = ((payload.get("region") or {}).get("width") or 0)
        if not w:
            return False
        page = payload.get("_page")
        widest = 0.0
        for a in stream.anchors:
            other = stream.payload[a]
            if other.get("type") != "column" or other.get("_page") != page:
                continue
            widest = max(widest, float((other.get("region") or {}).get("width") or 0))
        return widest >= _SIDENOTE_WIDTH_RATIO * float(w)

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
            # A TEXT COLUMN IS NOT A SIDENOTE. This module was written for a
            # corpus where a `column` with text children WAS a marginal note,
            # and on a two-column paper it makes the body prose one: 18 of
            # them on 1909.00741, the first reading "advances in
            # deep-learning-based object detection have lifted this approach
            # to a higher level", and 8 more on
            # 1-s2.0-S2590118425000565-main whose text is the bibliography.
            #
            # The discriminator is WIDTH, and it is measurable on the page
            # itself: a margin note is materially narrower than the column it
            # sits beside, while the columns of a two-column body are equals.
            # So a `column` qualifies only when a WIDER one shares its page.
            if not self._is_narrow_for_its_page(stream, payload):
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
