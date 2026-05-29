"""
EquationProcessor (procOrder 11).

Display equations (lines of type='equation' or type='math') get particularly
rich treatment, since equations are the canonical case for multi-stream
realizations:

  1. Surface realization in `mathpix_lines` — where the equation sits in OCR
     output (one anchor, the whole line).
  2. LaTeX-source realization in a per-equation character-level stream
     `latex_eq_<n>` — character anchors for each codepoint of the normalized
     LaTeX. This is the stream you'd address from a structural LaTeX parser
     (Fraction-of-1-over-2, etc.).
  3. CDN realization — opaque pointer to the MathPix-rendered image URL.

A nearby `equation_number` line (±3 lines around) provides the refnum.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization, Range, Alignment
from ..mathpix import crop_url


_OUT_DOLLAR = re.compile(r"^\$\$([\s\S]*)\$\$$")
_OUT_INLDOL = re.compile(r"^\$([\s\S]*)\$$")
_OUT_PAREN = re.compile(r"^\\\(([\s\S]*)\\\)$")
_OUT_BRACK = re.compile(r"^\\\[([\s\S]*)\\\]$")
_BEGIN_EQ = re.compile(r"\\begin\{equation\}")
_END_EQ = re.compile(r"\\end\{equation\}")


def _normalize_latex(raw: str) -> str:
    if not raw:
        return ""
    s = raw.strip()
    for rx in (_OUT_BRACK, _OUT_PAREN, _OUT_DOLLAR, _OUT_INLDOL):
        m = rx.match(s)
        if m:
            s = m.group(1)
            break
    s = _BEGIN_EQ.sub("", s)
    s = _END_EQ.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


class EquationProcessor(BaseModule):
    EQ_TYPES = {"equation", "math"}

    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        anchors = stream.anchors
        items: list[dict[str, Any]] = []

        for i, anchor in enumerate(anchors):
            payload = stream.payload[anchor]
            if payload.get("type") not in self.EQ_TYPES:
                continue
            refnum = self._refnum_near(anchors, stream, i)
            latex_raw = payload.get("text_display") or payload.get("text") or ""
            items.append({
                "anchor": anchor,
                "page": payload.get("_page"),
                "image_id": payload.get("_image_id"),
                "region": payload.get("region"),
                "refnum": refnum,
                "latex_raw": latex_raw,
                "latex": _normalize_latex(latex_raw),
            })
        return items

    @staticmethod
    def _refnum_near(anchors, stream, i: int) -> str:
        lo, hi = max(0, i - 3), min(len(anchors), i + 4)
        for j in range(lo, hi):
            p = stream.payload[anchors[j]]
            if p.get("type") == "equation_number":
                t = (p.get("text") or p.get("text_display") or "").strip()
                t = re.sub(r"[()]", "", t).strip()
                if t:
                    return t
        return ""

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        # 1) Build a per-equation char-level stream for the normalized LaTeX.
        eq_no = self.bump("equations_created")
        latex_stream_name = f"latex_eq_{eq_no:04d}"
        latex_stream = doc.ensure_stream(latex_stream_name)
        latex_anchors = [latex_stream.append(codepoint=ch) for ch in item["latex"]]

        obj = DocObject(
            type="Equation",
            props={
                "refnum": item["refnum"],
                "latex": item["latex"],          # convenient copy
                "latex_raw": item["latex_raw"],
                "page": item["page"],
                "image_id": item["image_id"],
                "region": item["region"],
                "cdn_url": crop_url(item["image_id"], item["region"]),
                "bibkey": self.bibkey,
            },
        )
        # surface in the OCR line stream
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface",
        ))
        # latex source as a char-level realization
        if latex_anchors:
            obj.add_realization(Realization(
                stream=latex_stream_name,
                start=latex_anchors[0], end=latex_anchors[-1],
                role="latex_source",
            ))
        # rendered image (no anchor range, just a URL pointer)
        if obj.props["cdn_url"]:
            obj.add_realization(Realization(
                stream="cdn",
                role="image",
                props={"url": obj.props["cdn_url"]},
            ))

        # The rendering relationship "this latex source produces this CDN
        # image" is expressed both as the cdn-role Realization above AND as
        # an Alignment of kind 'render'. The cdn side of the Range has no
        # anchors (the URL is the substance), which is now a first-class
        # case the Range type supports.
        if latex_anchors and obj.props["cdn_url"]:
            doc.add_alignment(Alignment(
                kind="render",
                left=Range(latex_stream_name, latex_anchors[0], latex_anchors[-1]),
                right=Range("cdn", None, None),
                props={"target_url": obj.props["cdn_url"]},
            ))

        return obj
