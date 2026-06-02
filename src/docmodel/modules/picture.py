"""
PictureProcessor (procOrder 9).

Picks up figures and inline image URLs.

**Image links — Markdown only.** MathPix encodes the same image two ways:

  - Markdown form: `![](<cdn>)` where `<cdn>` is the *page* image
    (`cropped/<process-id>-<page>.jpg`) plus a rectangle in the query string
    (`height/width/top_left_y/top_left_x`). This is identical to what
    `mathpix.crop_url(image_id, region)` reconstructs from the line's own
    `image_id` + `region`.
  - LaTeX form: `\\begin{figure}\\includegraphics[...]{...}\\end{figure}`. In the
    `tex.zip` export the `\\includegraphics` target is a *per-picture* numbered
    local file (process-id, page, then a picture index) — a different
    addressing scheme that would need image matching to relate back to a full
    page. We therefore do NOT use `\\includegraphics` URLs at all; we take the
    Markdown link (the embedded `![]()` / bare CDN URL, or `crop_url`).

What this processor captures:

- Lines of type='figure': image URL from `crop_url(image_id, region)`, caption
  from a child of type='caption' or the line's own `\\caption{}`.
- Inline Markdown images (`![]()`) / bare CDN URLs embedded in text lines.

`type='diagram'` lines are intentionally NOT handled here — they are owned by
`DiagramProcessor` (procOrder 7), which also uses the Markdown `crop_url` link.
The TS reference removed diagram lines from the document before PictureProcessor
ran; our source streams are immutable, so we skip the type instead to avoid one
image becoming both a Diagram and a Picture.

Each becomes a Picture DocObject with a CDN realization plus a surface
realization into the source line, carrying caption / kind / refnum.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ._captions import extract_figure_caption, parse_caption
from ..base_module import BaseModule
from ..core import Document, DocObject, Realization
from ..mathpix import crop_url, region_from_url


# Markdown image link (the only image-URL form we trust).
_MD_IMG = re.compile(r"!\[[^\]]*\]\((https?://[^\s)]+)\)")
# Bare MathPix CDN crop URL (page image + rectangle params) embedded in text —
# also a Markdown-style link.
_CDN_URL = re.compile(r"(https?://cdn\.mathpix\.com/cropped/[^\s\}>\])\"]+)")

# Line types whose images are owned by another processor.
_SKIP_TYPES = {"diagram"}


class PictureProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        by_id = self.build_line_index(doc)
        items: list[dict[str, Any]] = []

        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            ltype = payload.get("type")
            if ltype in _SKIP_TYPES:
                continue
            if ltype == "figure":
                items.extend(self._from_figure_line(anchor, payload, by_id))
            else:
                items.extend(self._from_inline(anchor, payload))
        return items

    @staticmethod
    def _from_figure_line(anchor, payload, by_id) -> list[dict[str, Any]]:
        text = payload.get("text_display") or payload.get("text") or ""
        # Caption from a child of type='caption', else from a \caption{} in the
        # line's own figure-env text.
        caption = ""
        for cid in payload.get("children_ids", []) or []:
            child = by_id.get(cid)
            if child and child.get("type") == "caption":
                caption = child.get("text_display") or child.get("text") or ""
                break
        if not caption:
            caption = extract_figure_caption(text)
        # Markdown link only: the page image + rectangle from this line's own
        # region (NOT the \includegraphics target).
        region = payload.get("region") or {}
        url = crop_url(payload.get("_image_id"), region)
        if not url:
            return []
        return [{
            "anchor": anchor,
            "url": url,
            "caption": caption,
            "page": payload.get("_page"),
            "region": region,
            "from_line_type": "figure",
        }]

    @staticmethod
    def _from_inline(anchor, payload) -> list[dict[str, Any]]:
        text = payload.get("text_display") or payload.get("text") or ""
        if not text:
            return []
        # Caption from a figure-env in the line text (Markdown `![]()` form has
        # no caption). One caption per line is the realistic case.
        caption = extract_figure_caption(text) if "\\begin{figure}" in text else ""
        urls: list[str] = []
        # Markdown image links, then bare CDN crop URLs — both page+rectangle.
        # MathPix LaTeX-escapes query `&` as `\&` inside table-cell `![]()`;
        # unescape so the stored URL is directly fetchable (no 400 downstream).
        for m in _MD_IMG.finditer(text):
            urls.append(m.group(1).strip().replace("\\&", "&"))
        for m in _CDN_URL.finditer(text):
            urls.append(m.group(1).strip().replace("\\&", "&"))
        # De-duplicate within this line while preserving order.
        seen = set()
        unique = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        out = []
        for i, url in enumerate(unique):
            out.append({
                "anchor": anchor,
                "url": url,
                # Attach the caption to the first image only.
                "caption": caption if i == 0 else "",
                "page": payload.get("_page"),
                "region": region_from_url(url),
                "from_line_type": payload.get("type"),
            })
        return out

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        kind, refnum, cap_body = parse_caption(item["caption"])
        obj = DocObject(
            type="Picture",
            props={
                "url": item["url"],
                "caption": cap_body,
                "kind": kind,           # 'Figure' / 'Picture' / 'Sketch' / ... / None
                "refnum": refnum,
                "page": item["page"],
                "region": item["region"],
                "from_line_type": item["from_line_type"],
                "bibkey": self.bibkey,
            },
        )
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface",
        ))
        obj.add_realization(Realization(
            stream="cdn",
            role="image",
            props={"url": item["url"]},
        ))
        self.bump("pictures_created")
        return obj
