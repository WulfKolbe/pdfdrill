"""
Tests for wiring pdfimages/pdfplumber image rects into the model
(pdfdrill.image_model).

No PDF / no subprocess: a synthetic Document (MathPix page dims + Picture/Diagram
crops with a surface realization) is fused against a synthetic image layer.
Covers: EmbeddedImage node creation + metadata, containment fusion (a crop
inside the page image links; a crop outside does NOT), string-coordinate
regions (parsed from URL query params), and idempotent re-runs.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from docmodel.core import Document, DocObject, Realization
from pdfdrill import image_model


def _contains():
    assert image_model._contains((0, 0, 1, 1), (0.2, 0.2, 0.4, 0.4))
    assert not image_model._contains((0, 0, 0.5, 0.5), (0.6, 0.6, 0.9, 0.9))


def test_contains_and_float_coercion():
    _contains()
    assert image_model._f("17") == 17.0
    assert image_model._f(None) is None
    assert image_model._f("x") is None


def _doc_with_crop(region, page=1, ptype="Diagram"):
    """Document with one page (MathPix px dims) + a crop carrying a surface
    realization into mathpix_lines (so it is addressable for an alignment)."""
    doc = Document()
    doc.meta["pages"] = [{"page": page, "page_width": 1000, "page_height": 2000}]
    s = doc.ensure_stream("mathpix_lines")
    a = s.append(type="figure", _page=page)
    o = DocObject(type=ptype, props={"page": page, "region": region})
    o.add_realization(Realization(stream="mathpix_lines", start=a, end=a, role="surface"))
    doc.add(o)
    return doc, o


# Page image covers the whole page (scanned-doc case): 612x792 pt.
_FULL_PAGE_IMG = {"page": 1, "x0": 0.0, "y0": 0.0, "x1": 612.0, "y1": 792.0,
                  "w_pt": 612.0, "h_pt": 792.0, "width_px": 2480, "height_px": 3508,
                  "encoding": "image", "color": "rgb", "object_id": "10 0"}
_PAGE_DIMS = {1: (612.0, 792.0)}


def test_embedded_image_node_and_metadata():
    # Crop in the middle of the page (MathPix px: page is 1000x2000).
    doc, crop = _doc_with_crop({"top_left_x": 200, "top_left_y": 400, "width": 300, "height": 300})
    stats = image_model.attach_embedded_images(doc, [_FULL_PAGE_IMG], _PAGE_DIMS, bibkey="T")
    assert stats["created"] == 1 and stats["fused"] == 1
    ei = doc.objects_of_type("EmbeddedImage")[0]
    assert ei.props["width_px"] == 2480 and ei.props["encoding"] == "image"
    assert ei.props["region"]["space"] == "pdf_points"
    # PDF-native bottom-left Y recorded alongside the top-left region.
    # Page is 792pt tall; image y_top spans 0..792 -> y_bottom spans 0..792.
    assert ei.props["page_height_pt"] == 792.0
    assert ei.props["y0_pdf"] == round(792.0 - _FULL_PAGE_IMG["y1"], 3)
    assert ei.props["y1_pdf"] == round(792.0 - _FULL_PAGE_IMG["y0"], 3)
    assert ei.props["y_origin"] == "top_left"
    # The crop is linked both ways.
    assert crop.props.get("embedded_image_id") == ei.id
    aligns = [a for a in doc.alignments if a.kind == "image_region"]
    assert len(aligns) == 1 and aligns[0].props["crop"] == crop.id


def test_crop_outside_image_is_not_fused():
    # Born-digital case: a small figure image in the TOP half only; a crop in
    # the BOTTOM half must NOT link to it.
    doc, crop = _doc_with_crop({"top_left_x": 100, "top_left_y": 1600, "width": 200, "height": 200})
    top_img = {**_FULL_PAGE_IMG, "y0": 0.0, "y1": 200.0, "h_pt": 200.0}  # top ~25%
    stats = image_model.attach_embedded_images(doc, [top_img], _PAGE_DIMS, bibkey="T")
    assert stats["created"] == 1 and stats["fused"] == 0
    assert crop.props.get("embedded_image_id") is None


def test_string_coordinate_region_fuses():
    # Region parsed from a CDN URL has string coords — must not crash and fuse.
    doc, crop = _doc_with_crop({"top_left_x": "200", "top_left_y": "400",
                                "width": "300", "height": "300"})
    stats = image_model.attach_embedded_images(doc, [_FULL_PAGE_IMG], _PAGE_DIMS, bibkey="T")
    assert stats["fused"] == 1


def test_idempotent_rerun():
    doc, _ = _doc_with_crop({"top_left_x": 200, "top_left_y": 400, "width": 300, "height": 300})
    image_model.attach_embedded_images(doc, [_FULL_PAGE_IMG], _PAGE_DIMS, bibkey="T")
    image_model.attach_embedded_images(doc, [_FULL_PAGE_IMG], _PAGE_DIMS, bibkey="T")
    assert len(doc.objects_of_type("EmbeddedImage")) == 1
    assert len([a for a in doc.alignments if a.kind == "image_region"]) == 1


if __name__ == "__main__":
    fns = [test_contains_and_float_coercion, test_embedded_image_node_and_metadata,
           test_crop_outside_image_is_not_fused, test_string_coordinate_region_fuses,
           test_idempotent_rerun]
    for fn in fns:
        fn(); print(f"PASS {fn.__name__}")
    print(f"\nAll {len(fns)} tests passed.")
