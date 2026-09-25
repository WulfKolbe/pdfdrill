"""
RotatedTextProcessor.

SIDEWAYS TEXT IS ITS OWN KIND, and it was arriving as prose. An arXiv
identifier stamped down the left margin — `arXiv:1909.00741v1 [cs.MM] 2 Sep
2019`, set at 90 degrees — belongs to the ARCHIVE, not to the paper, and a
reader that finds it inside the running text of section 1 has been told
something false about the document.

It is established by the CTM, not by reading: the glyphs' text matrix is
rotated off the page axis. That makes it one of the few types in the
specification that needs no language, no font ranking and no threshold — the
matrix either is rotated or it is not.

Worse than useless as prose, it is genuinely useful as an object: it carries an
identifier, a date and a classification, in its own rectangle, at a known
angle. `rotation` rides along because a reader cropping the region needs it and
cannot recover it from a rectangle.

MathPix has no type for this; the name is ours, and it matches the property
`pdfdrill profile` already reports (`rotated-text`).
"""
from __future__ import annotations

from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization


class RotatedTextProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        items: list[dict[str, Any]] = []
        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            if payload.get("type") != "rotated_text":
                continue
            text = (payload.get("text_display") or payload.get("text") or "").strip()
            if not text:
                continue                       # a rectangle with no words is
                                               # a graphic, not rotated text
            items.append({
                "anchor": anchor,
                "text": text,
                "page": payload.get("_page"),
                "rotation": payload.get("rotation"),
                "region": payload.get("region"),
            })
        return items

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        props: dict[str, Any] = {
            "text": item["text"],
            "page": item["page"],
            "bibkey": self.bibkey,
        }
        # Only what was measured. A rotation the reader did not establish is
        # absent rather than 0, because 0 is a claim that the text is upright.
        if item.get("rotation") is not None:
            props["rotation"] = item["rotation"]
        if item.get("region"):
            props["region"] = item["region"]
        obj = DocObject(type="RotatedText", props=props)
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface",
        ))
        self.bump("rotated_text_created")
        return obj
