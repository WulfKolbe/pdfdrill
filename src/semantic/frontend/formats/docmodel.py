"""FORMAT module: the L5 Document IR itself as an input surface for object
detection. The Document is just another format the frontmatter object can be
read from — `surface(doc)` exposes its meta + objects. One module per format."""
from __future__ import annotations

from ..contract import FormatModule, Surface, register_format


class DocmodelFormat(FormatModule):
    format = "docmodel"

    def surface(self, doc) -> Surface:
        meta = getattr(doc, "meta", {}) or {}
        objs = getattr(doc, "objects", {})
        objs = list(objs.values()) if isinstance(objs, dict) else list(objs)
        return Surface(format=self.format, raw="", lines=[],
                       meta={"doc_meta": meta, "objects": objs})


register_format(DocmodelFormat())
