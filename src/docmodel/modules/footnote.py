r"""
FootnoteProcessor (procOrder 2).

Extracts footnote lines (type='footnote') and parses the actual content from
their `\footnotetext{...}` LaTeX wrapper, then creates Footnote DocObjects.

MathPix puts EVERY footnote of a page into ONE `\footnotetext{...}` group, so
until 636 one Footnote object took the whole group: 14 of the 28 penev_A
bodies this module makes ended with the NEXT footnote's printed number and its
first words. Each label now closes the body before it and opens a body of its
own — see `docmodel.footnote_split` for the rule and why it is exact.

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
from ..footnote_split import LABEL, split_bodies


_FOOTNOTETEXT = re.compile(r"\\footnotetext\{")
_ANCHOR_PATTERN = re.compile(r"\{ \}\^\{(\d+)\}")


class FootnoteProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        anchor_by_id: dict[str, Any] = {}
        for a in stream.anchors:
            lid = stream.payload[a].get("id")
            if lid and lid not in anchor_by_id:
                anchor_by_id[lid] = a
        items: list[dict[str, Any]] = []
        orphan = 0

        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            if payload.get("type") != "footnote":
                continue
            pieces = self._block_pieces(anchor, payload, anchor_by_id, stream)
            full_text = "".join(t for _a, t in pieces)
            refnum = self._refnum(full_text)
            if not refnum:
                continue
            span = self._footnotetext_span(full_text)
            base = {
                "anchor": anchor,
                "page": payload.get("_page"),
                "line_id": payload.get("id"),
                "original_text": full_text,
            }
            if span is None:                       # no wrapper -> no body, as before
                items.append({**base, "refnum": refnum, "content": ""})
                continue
            segs = split_bodies(full_text[span[0]:span[1]])
            if not segs:
                items.append({**base, "refnum": refnum,
                              "content": full_text[span[0]:span[1]].strip()})
                continue
            for i, seg in enumerate(segs):
                orphan += 1 if seg.tail_unassigned else 0
                item = {**base, "refnum": seg.refnum, "content": seg.body}
                if seg.tail_unassigned:
                    item["tail_unassigned"] = True
                if i:                              # a body cut OUT of the block
                    item["split_index"] = i
                    sub = self._sub_anchor(pieces, span[0] + seg.start,
                                           span[0] + seg.end)
                    if sub is not None:
                        item["anchor"], item["offset"], item["length"] = sub
                items.append(item)
        if orphan:
            doc.meta["footnote_orphan_tail"] = \
                int(doc.meta.get("footnote_orphan_tail") or 0) + orphan
            self.bump("footnote_orphan_tail", orphan)
        return items

    # ----- the block -----

    def _block_pieces(self, anchor, line_payload: dict, anchor_by_id: dict,
                      stream) -> list[tuple[Any, str]]:
        """The block as (anchor, text) pieces, in reading order.

        MathPix hangs the footnote text off the `footnote` line as CHILD lines
        (three of them for penev_A's page-4 block, one per printed footnote and
        its continuation). The pieces keep each child's own anchor so a body cut
        out of the block can point at the line it actually starts on."""
        pieces: list[tuple[Any, str]] = []
        for cid in (line_payload.get("children_ids") or []):
            a = anchor_by_id.get(cid)
            if a is None:
                continue
            p = stream.payload[a]
            pieces.append((a, p.get("text_display") or p.get("text") or ""))
        if not any(t for _a, t in pieces):
            pieces = [(anchor, line_payload.get("text_display")
                       or line_payload.get("text") or "")]
        return pieces

    @staticmethod
    def _refnum(text: str) -> Optional[str]:
        """The block's own number: the first LABEL, falling back to the first
        bare `{ }^{n}` so a block whose number is spelled some other way still
        produces the Footnote it always produced."""
        labels = LABEL.search(text or "")
        if labels:
            return labels.group(1)
        m = _ANCHOR_PATTERN.search(text or "")
        return m.group(1) if m else None

    @staticmethod
    def _footnotetext_span(text: str) -> Optional[tuple[int, int]]:
        """[start, end) of the body inside `\\footnotetext{...}` (balanced)."""
        m = _FOOTNOTETEXT.search(text)
        if not m:
            return None
        start = m.end()
        depth = 1
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    return (start, i)
        return None                                # unbalanced -> no body, as before

    @staticmethod
    def _sub_anchor(pieces: list[tuple[Any, str]], start: int,
                    end: int) -> Optional[tuple[Any, int, int]]:
        """(anchor, offset, length) for the piece the cut falls on.

        The length is the part of the body that lies on THAT line — the rest
        runs onto the following lines, which the block's own realization
        already covers. An offset that cannot be placed exactly is not
        invented: the caller then keeps the block anchor."""
        pos = 0
        for a, t in pieces:
            if pos <= start < pos + len(t):
                off = start - pos
                return (a, off, min(end, pos + len(t)) - start)
            pos += len(t)
        return None

    # ----- objects -----

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        props = {
            "refnum": item["refnum"],
            "anchor_marker": "{ }^{" + str(item["refnum"]) + "}",
            "content": item["content"],
            "page": item["page"],
            "bibkey": self.bibkey,
        }
        if item.get("split_index"):
            props["split_index"] = item["split_index"]
        if item.get("tail_unassigned"):
            props["tail_unassigned"] = True
        obj = DocObject(type="Footnote", props=props)
        # Surface realization: the footnote line in mathpix_lines. A body cut
        # out of the block carries a sub-anchor (offset/length) so it claims
        # its share of the line INLINE and not the whole of it (646).
        sub = {}
        if isinstance(item.get("offset"), int) and isinstance(item.get("length"), int):
            sub = {"offset": item["offset"], "length": item["length"]}
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface", props=sub,
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
        if item.get("split_index"):
            self.bump("footnote_bodies_split")
        return obj
