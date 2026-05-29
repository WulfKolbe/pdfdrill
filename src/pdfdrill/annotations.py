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


def add_link_objects(doc, records: list[dict], provenance: str = "pdfplumber") -> list:
    """Add a `Link` DocObject per link record.

    Each link also gets an anchor in the `links` stream (so it is addressable
    by Alignments). Returns a list of (link_obj, anchor) pairs.
    """
    from docmodel.core import DocObject, Realization, Region

    s = doc.ensure_stream("links")
    created = []
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

        anchor = s.append(uri=uri, kind=kind, page=r.get("page"),
                          dest_name=r.get("dest_name") or "",
                          anchor_text=r.get("anchor_text") or "")
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
            stream="links", start=anchor, end=anchor,
            role="annotation", provenance=provenance,
            props={"uri": uri, "anchor_text": r.get("anchor_text") or ""},
            region=region,
        ))
        doc.add(obj)
        created.append((obj, anchor))
    return created


def link_xref_alignments(doc, created: list) -> dict:
    """Add cross-reference Alignments for internal links.

    A small dest-name micro-grammar splits `prefix.key` (e.g. cite.foo2023,
    theorem.1.1). For `cite.*` we align the Link to the matching Citation
    object's surface range (citation-graph seed); for any internal link with a
    `dest_page` we align it to that Page object (page-level xref). Returns
    {cites, xrefs}.
    """
    from docmodel.core import Range, Alignment

    cite_by_key = {}
    for c in doc.objects.values():
        if c.type == "Citation":
            k = (c.props.get("citekey") or "").strip()
            if k:
                cite_by_key.setdefault(k, c)
    page_by_num = {p.props.get("page_number"): p
                   for p in doc.objects.values() if p.type == "Page"}

    def surface_range(obj):
        r = next((r for r in obj.realizations
                  if r.stream == "mathpix_lines" and r.start is not None), None)
        return Range("mathpix_lines", r.start, r.end) if r else None

    cites = xrefs = 0
    for obj, anchor in created:
        if obj.props.get("kind") == "url":
            continue
        left = Range("links", anchor, anchor)
        dest = obj.props.get("dest_name") or ""
        prefix, _, key = dest.partition(".")
        if prefix == "cite" and key in cite_by_key:
            tgt = surface_range(cite_by_key[key])
            if tgt:
                doc.add_alignment(Alignment(kind="cites", left=left, right=tgt,
                                            props={"citekey": key}))
                cites += 1
                continue
        dp = obj.props.get("dest_page")
        if dp in page_by_num:
            tgt = surface_range(page_by_num[dp])
            if tgt:
                doc.add_alignment(Alignment(kind="xref", left=left, right=tgt,
                                            props={"dest_name": dest, "dest_page": dp}))
                xrefs += 1
    return {"cites": cites, "xrefs": xrefs}
