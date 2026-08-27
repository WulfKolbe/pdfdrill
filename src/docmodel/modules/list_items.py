"""
ListProcessor (procOrder 10).

248 — MathPix TYPES list items, and until now this module ignored that and
re-derived them lexically. `"list_item"` appeared nowhere in src/: 80,035 lines
across 882 of 1,350 corpus documents, skipped by `type != "text": continue`.

The container carries the structure, not the words: 75% have EMPTY text and
`children_ids` pointing at the lines that hold them — usually `text`, but also
math, equation_number, nested list_item and diagram. So the old scan was not
missing the items (the children are text lines and do start with markers); it
was missing their BOUNDARIES. A two-line item became one item plus a stray
paragraph, an item whose marker MathPix consumed became nothing, and nesting
was invisible.

Containers are read first. A text line already claimed by a container is not
scanned again, so nothing is counted twice. Lines outside any container still
go through the lexical path, which is the only thing that works on documents
MathPix typed no list_item for at all.

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

# "Strong" bullet glyphs (NOT '-'/'*', too ambiguous mid-line). When one of
# these appears *mid-line*, the line is a run of bullet items the OCR merged
# without a linefeed — split it into separate items.
_STRONG_BULLET = re.compile("[•‣◦⁃∙▪●○∙]")


def _detect_marker(text: str) -> Optional[str]:
    for rx in (_BULLET, _NUMBERED, _LETTERED):
        m = rx.match(text)
        if m:
            return m.group(1)
    return None


def _split_bullets(text: str) -> list[tuple[str, str]]:
    """Return [(marker, content)] for a line.

    If a strong bullet glyph appears mid-line (merged bullets, no linefeed),
    split into one item per segment. Otherwise a single leading-marker item,
    or [] when the line isn't a list item.
    """
    if text and _STRONG_BULLET.search(text[1:]):
        segs = [s.strip() for s in _STRONG_BULLET.split(text) if s.strip()]
        return [("•", s) for s in segs]
    marker = _detect_marker(text)
    if marker:
        content = re.sub(r"^" + re.escape(marker) + r"\s+", "", text).strip()
        return [(marker, content)]
    return []


class ListProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        items: list[dict[str, Any]] = []
        global_index = 0

        # ---- 248: the typed containers first --------------------------------
        by_id: dict[str, dict] = {}
        anchor_by_id: dict[str, Any] = {}
        for a in stream.anchors:
            pl = stream.payload[a]
            lid = pl.get("id")
            if lid:
                by_id[lid] = pl
                anchor_by_id[lid] = a
        claimed: set = set()          # text lines a container already owns
        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            if payload.get("type") != "list_item":
                continue
            marker, content, kids = self._from_container(payload, by_id)
            for cid in kids:
                claimed.add(cid)
            if not content:
                continue
            global_index += 1
            items.append({
                "anchor": anchor,
                "marker": marker,
                "content": content,
                "page": payload.get("_page"),
                "line_index": payload.get("_line_index"),
                "list_index": global_index,
                "source": "typed",
                "child_ids": kids,
            })

        # ---- the lexical path, for lines no container claimed ---------------
        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            if payload.get("type") != "text":
                continue
            if payload.get("id") in claimed:
                continue
            text = (payload.get("text") or "").strip()
            # One line may carry several bullets the OCR merged (no linefeed):
            # _split_bullets returns one (marker, content) per item.
            for marker, content in _split_bullets(text):
                if not content:
                    continue
                global_index += 1
                items.append({
                    "anchor": anchor,
                    "marker": marker,
                    "content": content,
                    "page": payload.get("_page"),
                    "line_index": payload.get("_line_index"),
                    "list_index": global_index,
                    "source": "lexical",
                    "child_ids": [],
                })
        return items

    @staticmethod
    def _from_container(payload: dict, by_id: dict) -> tuple:
        """(marker, content, child ids) for a typed `list_item` line.

        The container's own text is used when it has one (25% of them do);
        otherwise the content is its `text` children joined — which is what
        makes a two-line item ONE item instead of an item plus a stray
        paragraph. Non-text children (math, equation_number, nested items) are
        claimed so nothing scans them twice, but they are not folded into the
        content string: an equation inside a list item is an Equation, and
        flattening it into prose would lose it.
        """
        kids = list(payload.get("children_ids") or [])
        own = (payload.get("text") or "").strip()
        parts: list[str] = []
        text_kids: list[str] = []
        for cid in kids:
            ch = by_id.get(cid)
            if not ch or ch.get("type") != "text":
                continue
            text_kids.append(cid)
            t = (ch.get("text") or "").strip()
            if t:
                parts.append(t)
        raw = own or " ".join(parts)
        if not raw:
            return "", "", text_kids
        marker = _detect_marker(raw) or "\u2022"
        content = re.sub(r"^" + re.escape(marker) + r"\s+", "", raw).strip() \
            if _detect_marker(raw) else raw
        return marker, content, text_kids

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        obj = DocObject(
            type="ListItem",
            props={
                "marker": item["marker"],
                "content": item["content"],
                "page": item["page"],
                "line_index": item["line_index"],
                "list_index": item["list_index"],
                # 248: which path found it — a typed container or the lexical
                # fallback. Without it the two are indistinguishable after the
                # fact, and the whole point of the change is measurable only
                # if they are not.
                "detected_by": item.get("source", "lexical"),
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
