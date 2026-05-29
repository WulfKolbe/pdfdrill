"""
DiagramProcessor (procOrder 7).

Lines of type='diagram' become Diagram DocObjects. The MathPix `image_id` and
the line's `region` are combined into a CDN crop URL, which is added as a
`cdn` realization (no anchor range — opaque pointer). If the diagram has
LaTeX children, their text is concatenated into a `latex_code` prop.

Future: if a TikZ reconstruction step succeeds, it would add another
realization with role='tikz_reconstruction' pointing into a new per-diagram
character stream — exactly the cross-stream pattern we want.
"""
from __future__ import annotations

from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization
from ..mathpix import crop_url


class DiagramProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        by_id = self.build_line_index(doc)
        items: list[dict[str, Any]] = []

        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            if payload.get("type") != "diagram":
                continue
            latex_parts = []
            for cid in payload.get("children_ids", []) or []:
                child = by_id.get(cid)
                if not child:
                    continue
                ct = child.get("text_display") or child.get("text") or ""
                if ct:
                    latex_parts.append(ct)
            items.append({
                "anchor": anchor,
                "page": payload.get("_page"),
                "image_id": payload.get("_image_id"),
                "region": payload.get("region"),
                "subtype": payload.get("subtype", ""),
                "latex_code": "\n".join(latex_parts).strip(),
            })
        return items

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        obj = DocObject(
            type="Diagram",
            props={
                "page": item["page"],
                "image_id": item["image_id"],
                "region": item["region"],
                "subtype": item["subtype"],
                "latex_code": item["latex_code"],
                "cdn_url": crop_url(item["image_id"], item["region"]),
                "bibkey": self.bibkey,
            },
        )
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface",
        ))
        if obj.props["cdn_url"]:
            obj.add_realization(Realization(
                stream="cdn",
                role="image",
                props={"url": obj.props["cdn_url"]},
            ))
        self.bump("diagrams_created")
        return obj
