"""
DiagramProcessor (procOrder 7).

Lines of type='diagram' become Diagram DocObjects. The MathPix `image_id` and
the line's `region` are combined into a CDN crop URL via `crop_url` — the
**Markdown-style link** (page image + rectangle params), which is the only
image link we trust. We deliberately ignore the `\\includegraphics` target in
the LaTeX form (in the `tex.zip` export it points at a per-picture numbered
local file, a different addressing scheme). This URL is added as a `cdn`
realization (no anchor range — opaque pointer). If the diagram has LaTeX
children, their text is concatenated into a `latex_code` prop.

When the line carries a `\\caption{...}` (the LaTeX figure form), its caption is
extracted (balanced braces) and parsed into kind/refnum (`Picture 1`, `Sketch
2`, …); the Markdown `![]()` form carries no caption.

Future: if a TikZ reconstruction step succeeds, it would add another
realization with role='tikz_reconstruction' pointing into a new per-diagram
character stream — exactly the cross-stream pattern we want.
"""
from __future__ import annotations

from typing import Any, Optional

import re

from ._captions import extract_figure_caption, parse_caption
from ..base_module import BaseModule
from ..core import Document, DocObject, Realization
from ..mathpix import crop_url


_FENCE = ("```", "~~~")


def _extract_code(text: str):
    """If `text` is a markdown-fenced code block, return (code, language); else
    None. MathPix wraps source-code listings (e.g. Julia) as a `diagram` line
    whose body is ```` ```julia … ``` ```` — that is CODE, not a TikZ graphic,
    and must never be fed to latex→dvisvgm."""
    s = (text or "").strip()
    if not (s.startswith(_FENCE)):
        return None
    lines = s.splitlines()
    # First fence line may carry an info string (```julia title=x); take the
    # leading token as the language.
    info = lines[0].strip().lstrip("`~").split()
    language = info[0] if info and info[0].isalnum() else ""
    # Drop ANY fence line (bare or with a language), not just exact bare fences,
    # so interior fences from concatenated blocks don't leak into the code.
    body = [ln for ln in lines[1:] if not ln.strip().startswith(_FENCE)]
    return "\n".join(body).strip(), language


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
            # MathPix often emits a diagram line as a `\begin{figure}…\caption{…}
            # …\end{figure}` block; pull the caption (balanced braces, since it
            # can contain inline math) and parse its `Picture N:` / `Sketch N:`
            # label. The Markdown `![]()` form carries no caption.
            text = payload.get("text_display") or payload.get("text") or ""
            caption = extract_figure_caption(text)
            latex_code = "\n".join(latex_parts).strip()
            # A diagram whose body is a fenced code block is a source-code
            # listing, not a TikZ/table graphic: keep the code, drop latex_code
            # so it's never compiled by `svg`.
            code = _extract_code(latex_code) or _extract_code(text)
            items.append({
                "anchor": anchor,
                "page": payload.get("_page"),
                "image_id": payload.get("_image_id"),
                "region": payload.get("region"),
                "subtype": "code" if code else payload.get("subtype", ""),
                "latex_code": "" if code else latex_code,
                "code": code[0] if code else "",
                "language": code[1] if code else "",
                "caption": caption,
            })
        return items

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        kind, refnum, cap_body = parse_caption(item.get("caption", ""))
        is_code = item["subtype"] == "code"
        obj = DocObject(
            type="Diagram",
            props={
                "page": item["page"],
                "image_id": item["image_id"],
                "region": item["region"],
                "subtype": item["subtype"],
                "latex_code": item["latex_code"],
                "code": item.get("code", ""),
                "language": item.get("language", ""),
                "caption": cap_body,
                "kind": kind,           # 'Picture' / 'Sketch' / 'Figure' / ... / None
                "refnum": refnum,
                # A code listing is not an image: no CDN crop.
                "cdn_url": "" if is_code else crop_url(item["image_id"], item["region"]),
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
