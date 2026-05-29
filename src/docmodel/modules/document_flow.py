"""
DocumentFlowProcessor (procOrder 999, post-pass).

Sorts all "content" DocObjects (Paragraph, Equation, Table, Picture, Diagram,
Footnote, Sidenote, Formula display variants, ListItem, Section) by their
first surface position in mathpix_lines and assigns each a sequential
`flow_index`. Also adds `prev_in_flow` / `next_in_flow` props so the flow
is doubly-linked.

This is the equivalent of the TS DocumentFlowProcessor but does NOT create
extra FLOW tiddlers — the flow is just a property on the existing objects,
which is the natural place for it in the DocObject model.
"""
from __future__ import annotations

from typing import Optional

from ..base_module import BaseModule
from ..core import Document, DocObject


# Object types that participate in document flow.
_FLOW_TYPES = {
    "Paragraph", "Equation", "Table", "Picture", "Diagram",
    "Footnote", "Sidenote", "Formula", "ListItem", "Section",
    "Abstract", "Toc",
}

# Tie-breaker when two objects share the same (page, line_index).
_KIND_TIEBREAK = {
    "Section": 0,
    "Paragraph": 1,
    "Equation": 2,
    "Formula": 3,
    "Table": 4,
    "Picture": 5,
    "Diagram": 6,
    "ListItem": 7,
    "Footnote": 8,
    "Sidenote": 9,
    "Abstract": 10,
    "Toc": 11,
}


class DocumentFlowProcessor(BaseModule):
    # A post-pass module: all work happens in process_objects, after every
    # other module's process_document has run. find_items/create_object keep
    # their base no-op defaults.

    def process_objects(self, doc: Document) -> None:
        if self.LINES_STREAM not in doc.streams:
            return
        stream = doc.stream(self.LINES_STREAM)

        # Position key for a DocObject = (page, line_index of first surface
        # realization, kind_tiebreak). Objects without a surface realization
        # in mathpix_lines are excluded from the flow (they're meta).
        keyed: list[tuple[tuple[int, int, int], DocObject]] = []
        for obj in doc.objects.values():
            if obj.type not in _FLOW_TYPES:
                continue
            surface = [
                r for r in obj.realizations
                if r.stream == self.LINES_STREAM and r.start is not None
            ]
            if not surface:
                continue
            first = surface[0]
            payload = stream.payload[first.start]
            page = payload.get("_page") or 0
            line_index = payload.get("_line_index") or 0
            kind_rank = _KIND_TIEBREAK.get(obj.type, 99)
            keyed.append(((page, line_index, kind_rank), obj))

        keyed.sort(key=lambda t: t[0])

        prev: Optional[DocObject] = None
        for idx, (_key, obj) in enumerate(keyed, start=1):
            obj.props["flow_index"] = idx
            if prev is not None:
                obj.props["prev_in_flow"] = prev.id
                prev.props["next_in_flow"] = obj.id
            prev = obj

        self.bump("flow_indexed", len(keyed))
        if self.debug:
            self.log(f"flow-indexed {len(keyed)} objects")
