"""
Wire embedded raster images (pdfplumber rects + `pdfimages -list` metadata)
into the docmodel as first-class `EmbeddedImage` nodes, and fuse them onto the
MathPix `Picture`/`Diagram` crops that fall inside them.

Why: MathPix gives us *cropped* CDN images (sub-rectangles of a page) but tells
us nothing about the actual embedded image objects — their true pixel size,
encoding, colour space, ppi, file size — nor where pdfplumber sees them on the
page. `pdfimages`/`pdfplumber` give exactly that. Bringing both into ONE
structure means every route to an image (MathPix CDN crop, GPT-4o vision read,
pdfimages XObject metadata, pdfplumber rect) hangs off the same graph, so the
state machine can pick whichever route succeeds.

Coordinate fusion: pdfplumber rects are in PDF points; MathPix regions are in
image pixels. Both are normalized to page fractions [0,1] (pdfplumber rect ÷
page-points; MathPix region ÷ MathPix page-pixels) and a crop is linked to an
embedded image when the crop's box is essentially contained in the image's box
— recorded as `Alignment(kind="image_region")`. On a scanned PDF each page is
one full-page image, so every crop on the page links to it (the page scan
contains all its figures); on a born-digital PDF the per-figure XObjects link
to the matching crops.
"""
from __future__ import annotations

from typing import Any, Optional

from docmodel.core import (
    Document, DocObject, Realization, Region, Range, Alignment,
)

PDF_IMAGES_STREAM = "pdf_images"

# pdfimages/pdfplumber per-image fields carried onto the EmbeddedImage props.
_META_FIELDS = ("width_px", "height_px", "encoding", "color", "bpc", "ppi",
                "size", "object_id", "x0", "y0", "x1", "y1", "w_pt", "h_pt")


def fetch_page_dims_pts(pdf) -> dict[int, tuple[float, float]]:
    """Page (width, height) in PDF points, via pdfplumber. {} if unavailable."""
    try:
        import pdfplumber
    except ImportError:
        return {}
    dims: dict[int, tuple[float, float]] = {}
    with pdfplumber.open(str(pdf)) as doc:
        for i, page in enumerate(doc.pages, start=1):
            dims[i] = (float(page.width), float(page.height))
    return dims


def _contains(outer: tuple, inner: tuple, slack: float = 0.04) -> bool:
    """True if `inner` bbox is (almost) inside `outer` bbox (page fractions)."""
    ox0, oy0, ox1, oy1 = outer
    ix0, iy0, ix1, iy1 = inner
    return (ix0 >= ox0 - slack and iy0 >= oy0 - slack
            and ix1 <= ox1 + slack and iy1 <= oy1 + slack)


def _f(v) -> Optional[float]:
    """Coerce a coordinate to float (regions parsed from URL query params or
    JSON may be strings). None when not numeric."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _surface_range(obj: DocObject) -> Optional[Range]:
    r = next((r for r in obj.realizations
              if r.stream == "mathpix_lines" and r.start is not None), None)
    return Range("mathpix_lines", r.start, r.end) if r else None


def _mathpix_crop_boxes(doc: Document) -> list[tuple]:
    """(crop_obj, normalized_bbox) for every Picture/Diagram with a region,
    using the MathPix page-pixel dimensions from doc.meta."""
    mp_dims = {p["page"]: (p.get("page_width"), p.get("page_height"))
               for p in doc.meta.get("pages", [])}
    out: list[tuple] = []
    for o in doc.objects.values():
        if o.type not in ("Picture", "Diagram"):
            continue
        r = o.props.get("region") or {}
        pg = o.props.get("page")
        dims = mp_dims.get(pg)
        W = _f(dims[0]) if dims else None
        H = _f(dims[1]) if dims else None
        tlx, tly = _f(r.get("top_left_x")), _f(r.get("top_left_y"))
        w, h = _f(r.get("width")), _f(r.get("height"))
        if None in (W, H, tlx, tly, w, h) or not W or not H:
            continue
        out.append((o, (tlx / W, tly / H, (tlx + w) / W, (tly + h) / H)))
    return out


def clear_embedded_images(doc: Document) -> None:
    """Remove a prior run (EmbeddedImage objects, the stream, image_region edges)."""
    drop = [oid for oid, o in doc.objects.items() if o.type == "EmbeddedImage"]
    for oid in drop:
        doc.objects.pop(oid, None)
    doc.streams.pop(PDF_IMAGES_STREAM, None)
    doc.alignments = [a for a in doc.alignments if a.kind != "image_region"]


def attach_embedded_images(
    doc: Document,
    image_layer: list[dict[str, Any]],
    page_dims_pts: dict[int, tuple[float, float]],
    bibkey: str = "",
) -> dict[str, int]:
    """Create EmbeddedImage nodes from the image layer and fuse onto crops.

    Returns {"created", "fused", "with_coords"}.
    """
    clear_embedded_images(doc)
    stream = doc.ensure_stream(PDF_IMAGES_STREAM)
    crops = _mathpix_crop_boxes(doc)

    created = fused = with_coords = 0
    for rec in image_layer:
        pg = rec.get("page")
        anchor = stream.append(kind="embedded_image", page=pg,
                               object_id=rec.get("object_id"))
        props: dict[str, Any] = {"page": pg, "bibkey": bibkey,
                                 "source": "pdfimages+pdfplumber"}
        for k in _META_FIELDS:
            if rec.get(k) is not None:
                props[k] = rec.get(k)
        if rec.get("x0") is not None:
            props["region"] = Region(
                page=pg, top_left_x=rec.get("x0"), top_left_y=rec.get("y0"),
                width=rec.get("w_pt"), height=rec.get("h_pt"),
                space="pdf_points",
            ).to_dict()
            # x0/y0 above are TOP-left origin (pdfplumber). Also record the
            # PDF-native BOTTOM-left origin Y + page dims, so the node is
            # self-describing and matches a bottom-origin tool exactly:
            #   y_bottom = page_height - y_top.
            pdims = page_dims_pts.get(pg)
            ph = _f(pdims[1]) if pdims else None
            if ph:
                props["page_width_pt"] = round(_f(pdims[0]), 2)
                props["page_height_pt"] = round(ph, 2)
                props["y0_pdf"] = round(ph - _f(rec["y1"]), 3)   # bottom-left
                props["y1_pdf"] = round(ph - _f(rec["y0"]), 3)
                props["y_origin"] = "top_left"  # the region's own y convention
        obj = DocObject(type="EmbeddedImage", props=props)
        obj.add_realization(Realization(
            stream=PDF_IMAGES_STREAM, start=anchor, end=anchor, role="embedded",
            region=Region.from_dict(props.get("region")),
            props={k: props[k] for k in ("width_px", "height_px", "encoding")
                   if k in props},
        ))
        doc.add(obj)
        created += 1

        dims = page_dims_pts.get(pg)
        if not (dims and rec.get("x0") is not None and dims[0] and dims[1]):
            continue
        with_coords += 1
        W, H = dims
        img_box = (rec["x0"] / W, rec["y0"] / H, rec["x1"] / W, rec["y1"] / H)
        for crop_obj, cbox in crops:
            if crop_obj.props.get("page") != pg:
                continue
            if _contains(img_box, cbox):
                right = _surface_range(crop_obj)
                if right is None:
                    continue
                doc.add_alignment(Alignment(
                    kind="image_region",
                    left=Range(PDF_IMAGES_STREAM, anchor, anchor),
                    right=right,
                    props={"embedded_image": obj.id, "crop": crop_obj.id,
                           "crop_type": crop_obj.type},
                ))
                # Cross-link on the crop for easy querying.
                crop_obj.props.setdefault("embedded_image_id", obj.id)
                fused += 1
    return {"created": created, "fused": fused, "with_coords": with_coords}
