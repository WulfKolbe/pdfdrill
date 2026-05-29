"""
PictureProcessor (procOrder 9).

Picks up figures and inline image URLs:

- Lines of type='figure' with optional child captions and an
  `\\includegraphics` URL.
- Inline Markdown images `![alt](url)` in body text.
- Bare MathPix CDN URLs (cropped) embedded in text.

Each becomes a Picture DocObject with a CDN realization plus a surface
realization into the source line.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization
from ..mathpix import region_from_url


_INCLUDEGRAPHICS = re.compile(r"\\includegraphics[^{]*\{([^}]+)\}")
_MD_IMG = re.compile(r"!\[[^\]]*\]\((https?://[^\s)]+)\)")
_CDN_URL = re.compile(r"(https?://cdn\.mathpix\.com/cropped/[^\s\}>\])\"]+)")
_FIGURE_RE = re.compile(
    r"\\begin\{figure\}.*?\\includegraphics[^{]*\{([^}]+)\}.*?(?:\\caption\{([^}]*)\})?.*?\\end\{figure\}",
    re.DOTALL,
)


def _caption_kind_refnum(caption: str) -> tuple[Optional[str], Optional[str], str]:
    """Parse 'Figure 1.2: caption' style strings."""
    m = re.match(r"^\s*(Abbildung|Figure)\s+([0-9.]+)\s*:\s*(.*)$", caption, re.I)
    if not m:
        return None, None, caption.strip()
    return m.group(1).capitalize(), m.group(2), m.group(3).strip()


class PictureProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        by_id = self.build_line_index(doc)
        items: list[dict[str, Any]] = []

        # Pass 1: figure lines.
        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            if payload.get("type") == "figure":
                items.extend(self._from_figure_line(anchor, payload, by_id))
            else:
                items.extend(self._from_inline(anchor, payload))
        return items

    @staticmethod
    def _from_figure_line(anchor, payload, by_id) -> list[dict[str, Any]]:
        # Caption from a child of type='caption'.
        caption = ""
        for cid in payload.get("children_ids", []) or []:
            child = by_id.get(cid)
            if child and child.get("type") == "caption":
                caption = child.get("text_display") or child.get("text") or ""
                break
        text = payload.get("text_display") or payload.get("text") or ""
        m = _INCLUDEGRAPHICS.search(text)
        url = m.group(1).strip() if m else ""
        if not url:
            return []
        region = payload.get("region") or {}
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
        urls: list[str] = []
        # \begin{figure}…\end{figure} blocks inside text are unusual at line
        # granularity, but possible.
        for m in _FIGURE_RE.finditer(text):
            urls.append(m.group(1).strip())
        for m in _MD_IMG.finditer(text):
            urls.append(m.group(1).strip())
        for m in _CDN_URL.finditer(text):
            urls.append(m.group(1).strip())
        # De-duplicate within this line while preserving order.
        seen = set()
        unique = []
        for u in urls:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        out = []
        for url in unique:
            out.append({
                "anchor": anchor,
                "url": url,
                "caption": "",
                "page": payload.get("_page"),
                "region": region_from_url(url),
                "from_line_type": payload.get("type"),
            })
        return out

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        kind, refnum, cap_body = _caption_kind_refnum(item["caption"])
        obj = DocObject(
            type="Picture",
            props={
                "url": item["url"],
                "caption": cap_body,
                "kind": kind,           # 'Figure' / 'Abbildung' / None
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
