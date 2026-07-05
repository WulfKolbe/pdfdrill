"""
MathPix CDN helpers — the single owner of the cropped-image URL scheme.

A MathPix `region` is a dict with keys `height`, `width`, `top_left_x`,
`top_left_y`. `crop_url` renders such a region (plus an image id) into the
canonical CDN URL; `region_from_url` is its inverse, recovering the region
fields from a CDN URL's query string. Keeping the pair here means the URL
format lives in exactly one place.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse, parse_qs

# Query keys, in the order crop_url emits them.
_REGION_KEYS = ("height", "width", "top_left_y", "top_left_x")


def crop_url(image_id: Optional[str], region: Optional[dict]) -> str:
    """Build the MathPix cropped-image CDN URL, or '' if id/region is missing.
    The region keys are page-image PIXELS at MathPix's render DPI."""
    if not image_id or not region:
        return ""
    return (
        f"https://cdn.mathpix.com/cropped/{image_id}.jpg"
        f"?height={region.get('height')}&width={region.get('width')}"
        f"&top_left_y={region.get('top_left_y')}&top_left_x={region.get('top_left_x')}"
    )


# OUR local pyramid crop route (served by tools/imageserver/mathpix_server.py,
# proxied by the drillui bridge). `units=pt` tells the server the region is in
# PDF POINTS (top-left, y-down) — our coordinate system — so it scales by
# pyramid_dpi/72, NOT by MathPix's pixel DPI. Relative so it resolves against
# whatever local host serves the pyramid.
_LOCAL_CROP_PREFIX = "/cropped/"


def local_crop_url(image_id: Optional[str], region: Optional[dict],
                   ext: str = "png") -> str:
    """Build OUR pyramid crop URL for a region in PDF POINTS, or '' if missing.
    Carries `units=pt` so no coordinate-system mixing can occur downstream."""
    if not image_id or not region:
        return ""
    return (
        f"{_LOCAL_CROP_PREFIX}{image_id}.{ext}"
        f"?height={region.get('height')}&width={region.get('width')}"
        f"&top_left_y={region.get('top_left_y')}&top_left_x={region.get('top_left_x')}"
        f"&units=pt"
    )


def image_ref(image_id: Optional[str], region: Optional[dict],
              source: str = "mathpix") -> str:
    """Source-aware crop reference. `mathpix` → the CDN pixel URL; any other
    source (pdfminer/DRILLPDFse, …) → OUR local pyramid URL in PDF points. The
    two coordinate systems never mix — the source alone selects one."""
    if (source or "mathpix").lower() == "mathpix":
        return crop_url(image_id, region)
    return local_crop_url(image_id, region)


def is_local_crop(url: Optional[str]) -> bool:
    """True for one of OUR local pyramid crop URLs (`/cropped/…?…&units=pt`)."""
    return bool(url) and url.startswith(_LOCAL_CROP_PREFIX) and "units=pt" in url


def page_url(image_id_or_crop_url: Optional[str]) -> str:
    """Return the full-page CDN image URL for a crop.

    A crop URL is the same base image as the full page, so dropping the region
    query yields the complete-page render. Accepts a full crop URL or a bare
    image_id; returns '' if nothing usable is given.
    """
    s = image_id_or_crop_url
    if not s:
        return ""
    if s.startswith("http"):
        return s.split("?", 1)[0]
    return f"https://cdn.mathpix.com/cropped/{s}.jpg"


def region_from_url(url: str) -> dict[str, Optional[str]]:
    """Recover region fields from a CDN URL's query string."""
    try:
        q = parse_qs(urlparse(url).query)
    except Exception:
        return {}
    return {k: q[k][0] for k in _REGION_KEYS if k in q}
