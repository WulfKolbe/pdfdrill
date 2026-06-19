"""
PageProcessor (procOrder 1).

This is the foundational module: it ingests the raw MathPix lines.json and
builds the primary `mathpix_lines` stream, where each anchor corresponds to
one OCR line and carries that line's full payload (text, region, font_size,
type, page, column, image_id, ...).

It also creates a `Page` DocObject per page, with a realization spanning all
of that page's line anchors. Subsequent modules consume the stream and add
their own DocObjects on top.

Unlike the TypeScript version, this module is also responsible for the
initial *ingestion* step (reading the raw JSON into the Document): see
`ingest_lines_json`, which populates the `mathpix_lines` stream and the
page-level metadata on `doc.meta`.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization


def _extract_title(lines_json: dict) -> str:
    """Best-effort document title from the leading `type:"title"` line(s) on the
    first page(s). MathPix often nests the title text in child lines (the parent
    title line's own `text` is empty), so resolve `children_ids`. Returns "" when
    there is no title line (e.g. the keyless tesseract path emits only `text`)."""
    for page in lines_json.get("pages", [])[:2]:
        lines = page.get("lines", [])
        by_id = {l.get("id"): l for l in lines if l.get("id")}
        parts: list[str] = []
        for l in lines:
            if l.get("type") != "title":
                continue
            txt = (l.get("text") or "").strip()
            if not txt and l.get("children_ids"):
                txt = " ".join((by_id.get(cid, {}).get("text") or "")
                               for cid in l["children_ids"])
            txt = " ".join(txt.split())
            if txt and not re.fullmatch(r"abstract", txt, re.I):
                parts.append(txt)
        if parts:
            return " ".join(parts).strip()
    return ""


def ingest_lines_json(doc: Document, lines_json: dict) -> None:
    """
    Populate the `mathpix_lines` stream and store page-level metadata on
    `doc.meta`. Called by main.py before any processor runs.

    The payload of each anchor includes ALL fields of the original line
    (so no information is lost), plus a synthetic `_page` and `_line_index`
    for convenience (the OCR `line` field is sometimes ambiguous).
    """
    stream = doc.ensure_stream(BaseModule.LINES_STREAM)
    pages_meta: list[dict] = []
    for page in lines_json.get("pages", []):
        page_no = page.get("page")
        pages_meta.append({
            "page": page_no,
            "image_id": page.get("image_id"),
            "page_height": page.get("page_height"),
            "page_width": page.get("page_width"),
            "languages_detected": page.get("languages_detected", []),
        })
        for line_index, line in enumerate(page.get("lines", [])):
            payload = dict(line)  # shallow copy of MathPix line
            payload["_page"] = page_no
            payload["_line_index"] = line_index
            payload["_image_id"] = page.get("image_id")
            stream.append(**payload)
    doc.meta["pages"] = pages_meta
    doc.meta["num_pages"] = len(pages_meta)
    # Capture the document title (for the tiddler `caption`, scikgtex, the
    # llm_compact YAML header, …) — the PDF path never stored it before.
    if not doc.meta.get("title"):
        t = _extract_title(lines_json)
        if t:
            doc.meta["title"] = t


class PageProcessor(BaseModule):
    """Create one Page DocObject per page, spanning that page's lines."""

    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)

        # First pass: group existing line anchors by page number.
        anchors_by_page: dict[int, list] = {}
        for anchor in stream.anchors:
            pg = stream.payload[anchor].get("_page")
            anchors_by_page.setdefault(pg, []).append(anchor)

        # Drive the Page list from doc.meta['pages'] (set during ingest), so
        # that pages with zero OCR lines (blank pages) still get a Page object.
        items: list[dict[str, Any]] = []
        for page_meta in doc.meta.get("pages", []):
            pg = page_meta["page"]
            page_anchors = anchors_by_page.get(pg, [])
            items.append({
                "page": pg,
                "image_id": page_meta.get("image_id"),
                "page_height": page_meta.get("page_height"),
                "page_width": page_meta.get("page_width"),
                "languages_detected": page_meta.get("languages_detected", []),
                "start_anchor": page_anchors[0] if page_anchors else None,
                "end_anchor": page_anchors[-1] if page_anchors else None,
                "is_blank": len(page_anchors) == 0,
            })
        return items

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        obj = DocObject(
            type="Page",
            props={
                "page_number": item["page"],
                "image_id": item["image_id"],
                "page_height": item["page_height"],
                "page_width": item["page_width"],
                "languages_detected": item["languages_detected"],
                "is_blank": item["is_blank"],
                "bibkey": self.bibkey,
            },
        )
        if not item["is_blank"]:
            obj.add_realization(Realization(
                stream=self.LINES_STREAM,
                start=item["start_anchor"],
                end=item["end_anchor"],
                role="surface",
            ))
        self.bump("pages_created")
        if item["is_blank"]:
            self.bump("pages_blank")
        return obj
