"""
Promote hyperlink annotations into the unified model as first-class `Link`
DocObjects.

The sidecar `urls` layer (from links_layer.fetch_links) holds rich link
records — uri, kind, dest, the rectangle, and the visible anchor text. This
lifts each into a `Link` DocObject so annotations join the document graph
(rather than living only in the sidecar). A Link uses the same "opaque
pointer" pattern as the cdn image: a no-anchor `Realization` whose `props`
carry the URL and whose `Region` is the annotation rectangle (PDF points).
The anchor text / context are kept so the page-1 "code link with no visible
text" is queryable as a node.
"""
from __future__ import annotations


def add_link_objects(doc, records: list[dict], provenance: str = "pdfplumber") -> int:
    """Add a `Link` DocObject per link record. Returns the count added."""
    from docmodel.core import DocObject, Realization, Region

    doc.ensure_stream("links")
    added = 0
    for r in records:
        uri = r.get("uri") or ""
        kind = r.get("kind")
        if kind == "url" and not uri:
            continue
        if kind != "url" and not (r.get("dest_name")):
            continue

        rect = r.get("rect") or []
        region = None
        if len(rect) == 4 and all(v is not None for v in rect):
            x0, y0, x1, y1 = rect
            region = Region(page=r.get("page"), top_left_x=x0, top_left_y=y0,
                            width=x1 - x0, height=y1 - y0, space="pdf_points")

        obj = DocObject(type="Link", props={
            "uri": uri,
            "kind": kind,
            "dest_name": r.get("dest_name") or "",
            "dest_page": r.get("dest_page"),
            "anchor_text": r.get("anchor_text") or "",
            "context": r.get("context") or "",
            "page": r.get("page"),
        })
        obj.add_realization(Realization(
            stream="links", role="annotation", provenance=provenance,
            props={"uri": uri, "anchor_text": r.get("anchor_text") or ""},
            region=region,
        ))
        doc.add(obj)
        added += 1
    return added
