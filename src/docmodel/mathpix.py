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
    """Build the MathPix cropped-image CDN URL, or '' if id/region is missing."""
    if not image_id or not region:
        return ""
    return (
        f"https://cdn.mathpix.com/cropped/{image_id}.jpg"
        f"?height={region.get('height')}&width={region.get('width')}"
        f"&top_left_y={region.get('top_left_y')}&top_left_x={region.get('top_left_x')}"
    )


def region_from_url(url: str) -> dict[str, Optional[str]]:
    """Recover region fields from a CDN URL's query string."""
    try:
        q = parse_qs(urlparse(url).query)
    except Exception:
        return {}
    return {k: q[k][0] for k in _REGION_KEYS if k in q}
