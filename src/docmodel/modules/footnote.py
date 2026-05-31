"""
FootnoteProcessor (procOrder 2).

Extracts footnote lines (type='footnote') and parses the actual content from
their `\\footnotetext{...}` LaTeX wrapper, then creates Footnote DocObjects.

Compared to the TS version, this implementation:
  - Does NOT remove the footnote line from the source stream (immutable).
  - Does NOT do text replacement; the footnote anchor reference in body text
    is left for a follow-up resolver to express as an alignment between the
    body-text occurrence of `{ }^{N}` and the Footnote DocObject.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization


_FOOTNOTETEXT = re.compile(r"\\footnotetext\{")
_ANCHOR_PATTERN = re.compile(r"\{ \}\^\{(\d+)\}")


class FootnoteProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        by_id = self.build_line_index(doc)
        items: list[dict[str, Any]] = []

        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            if payload.get("type") != "footnote":
                continue
            full_text, refnum = self._collect_footnote_text(payload, by_id)
            if not refnum:
                continue
            content = self._parse_footnotetext(full_text, refnum)
            items.append({
                "anchor": anchor,
                "refnum": refnum,
                "content": content,
                "page": payload.get("_page"),
                "line_id": payload.get("id"),
                "original_text": full_text,
            })
        return items

    @staticmethod
    def _collect_footnote_text(line_payload: dict, by_id: dict) -> tuple[str, Optional[str]]:
        """Concatenate child text and detect the first ${ }^{N}$ anchor for refnum.

        Falls back to the line's own text when it has no children (MathPix puts
        the footnote anchor on the line itself for single-line footnotes)."""
        text = ""
        refnum: Optional[str] = None
        children = line_payload.get("children_ids", []) or []
        for cid in children:
            child = by_id.get(cid)
            if not child:
                continue
            child_text = child.get("text_display") or child.get("text") or ""
            if refnum is None:
                m = _ANCHOR_PATTERN.search(child_text)
                if m:
                    refnum = m.group(1)
            text += child_text
        if not text:
            text = line_payload.get("text_display") or line_payload.get("text") or ""
        if refnum is None:
            m = _ANCHOR_PATTERN.search(text)
            if m:
                refnum = m.group(1)
        return text, refnum

    @staticmethod
    def _parse_footnotetext(text: str, refnum: str) -> str:
        """Pull the body out of `\\footnotetext{...}` with balanced braces."""
        m = _FOOTNOTETEXT.search(text)
        if not m:
            return ""
        start = m.end()
        depth = 1
        end = start
        for i in range(start, len(text)):
            c = text[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if depth != 0:
            return ""
        body = text[start:end]
        # Drop the {refnum}^... anchor that often appears at the start.
        anchor_re = re.compile(r"\\\(\{ \}\^\{" + refnum + r"\}\\\)")
        return anchor_re.sub("", body).strip()

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        obj = DocObject(
            type="Footnote",
            props={
                "refnum": item["refnum"],
                "anchor_marker": "{ }^{" + str(item["refnum"]) + "}",
                "content": item["content"],
                "page": item["page"],
                "bibkey": self.bibkey,
            },
        )
        # Surface realization: the footnote line in mathpix_lines.
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface",
        ))
        # Cleaned realization: the parsed body text, no anchor span — it's a
        # derived value, kept on props. We expose it as an extra realization
        # with role='cleaned' so downstream code can find it uniformly.
        obj.add_realization(Realization(
            stream="derived",
            role="cleaned",
            props={"text": item["content"]},
        ))
        self.bump("footnotes_created")
        return obj
