"""
TableProcessor (procOrder 4).

Tables are line type='table' with children_ids pointing to rows/cells.
We create a Table DocObject with TableRow and TableCell children, all linked
back to their source line anchors.

The TS version also stripped table lines from the document; we preserve the
source stream and just emit objects on top.
"""
from __future__ import annotations

from typing import Any, Optional

from ..base_module import BaseModule
from ..core import Document, DocObject, Realization


_TABLE_TYPES = {"table"}
_ROW_TYPES = {"table_row"}
# table_spanning_cell carries the layout structure (a header covering N
# columns / a row-group label covering N rows); it was missing here, which
# silently dropped every spanning cell from the model.
_CELL_TYPES = {"simple_cell", "complex_cell", "table_spanning_cell"}
# MathPix per-cell grid coordinates, kept verbatim on the collected child.
_CELL_COORD_KEYS = ("cell_row", "cell_column", "cell_row_span", "cell_col_span",
                    "region")


class TableProcessor(BaseModule):
    def find_items(self, doc: Document) -> list[dict[str, Any]]:
        if self.LINES_STREAM not in doc.streams:
            return []
        stream = doc.stream(self.LINES_STREAM)
        by_id = self.build_line_index(doc)
        anchor_by_id = self.build_anchor_index(doc)
        items: list[dict[str, Any]] = []

        for anchor in stream.anchors:
            payload = stream.payload[anchor]
            if payload.get("type") not in _TABLE_TYPES:
                continue
            children = self._collect_children(payload, by_id, anchor_by_id)
            items.append({
                "anchor": anchor,
                "page": payload.get("_page"),
                "line_id": payload.get("id"),
                "children": children,
                # The table's own MathPix region (top_left_x/y/width/height) — so
                # the Table object is region-addressable like an Equation.
                "region": payload.get("region"),
                "raw_text": "\n".join(c["text"] for c in children if c["text"]),
            })
        return items

    def _collect_children(
        self, table_payload: dict, by_id: dict, anchor_by_id: dict,
    ) -> list[dict[str, Any]]:
        """Resolve children_ids -> child payloads with their stream anchors."""
        out: list[dict[str, Any]] = []
        for cid in table_payload.get("children_ids", []) or []:
            child = by_id.get(cid)
            if not child:
                continue
            ctype = child.get("type")
            if ctype not in (_ROW_TYPES | _CELL_TYPES):
                continue
            anchor = anchor_by_id.get(cid)
            entry: dict[str, Any] = {
                "anchor": anchor,
                "type": ctype,
                "text": child.get("text_display") or child.get("text") or "",
                "line_id": cid,
            }
            for key in _CELL_COORD_KEYS:
                if key in child:
                    entry[key] = child[key]
            out.append(entry)
        return out

    def create_object(self, item: dict[str, Any], doc: Document) -> Optional[DocObject]:
        # The Table itself.
        props: dict[str, Any] = {
            "page": item["page"],
            "raw_text": item["raw_text"],
            "bibkey": self.bibkey,
        }
        if item.get("region"):
            props["region"] = item["region"]          # region-addressable table
        # Span-aware cell structure: a value lives once at its anchor slot and
        # covers a range (cell_row/cell_column/cell_row_span/cell_col_span come
        # straight from MathPix). columns = flattened, linefeed-free header
        # names so a column is findable by name later.
        from pdfdrill.table_structure import cells_from_mathpix, column_headers
        cells, n_rows, n_cols = cells_from_mathpix(item["children"])
        if cells:
            columns, header_rows = column_headers(cells, n_cols)
            props.update(cells=cells, n_rows=n_rows, n_cols=n_cols,
                         columns=columns, header_rows=header_rows)
        obj = DocObject(
            type="Table",
            props=props,
        )
        obj.add_realization(Realization(
            stream=self.LINES_STREAM,
            start=item["anchor"], end=item["anchor"],
            role="surface",
        ))
        doc.add(obj)

        # Children: rows and cells, as separate DocObjects nested under the Table.
        for child in item["children"]:
            sub_type = "TableRow" if child["type"] in _ROW_TYPES else "TableCell"
            sub = DocObject(
                type=sub_type,
                props={"text": child["text"], "bibkey": self.bibkey},
            )
            if child["anchor"] is not None:
                sub.add_realization(Realization(
                    stream=self.LINES_STREAM,
                    start=child["anchor"], end=child["anchor"],
                    role="surface",
                ))
            doc.add_child(obj, sub)

        self.bump("tables_created")
        # Return None because we added the parent ourselves and don't want
        # the BaseModule's default loop to add it again.
        return None

    def process_document(self, doc: Document) -> None:
        # We override directly because create_object adds children itself.
        items = self.find_items(doc)
        for item in items:
            self.create_object(item, doc)
