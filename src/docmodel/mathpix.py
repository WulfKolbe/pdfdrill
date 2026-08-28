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


# ---------------------------------------------------------------------------
# 259 — `cnt`, the line's true quadrilateral.
#
# `region` is an axis-aligned box; `cnt` is the four corners MathPix actually
# found. On 3,459,944 corpus lines the two agree (the box IS the polygon's
# bounding box, to within the 0-2px inclusive-bound padding seen on 2% of
# them), so nothing changes there. On 4,886 lines the polygon is NOT
# axis-aligned — rotated table headers, diagonal annotations — and there
# `region` and the polygon's bbox genuinely disagree on 4,618. A rectangle
# drawn round rotated text is wider than the text: measured over those lines
# the box covers 1.06x the polygon's area at the median, 1.28x at p90 and
# 147x at worst.
#
# A CDN crop is a rectangle, so the polygon cannot make the crop non-rectangular
# — but it can make it TIGHT, and it can be carried so a consumer that wants to
# mask or deskew has the corners instead of having to re-derive them.
# ---------------------------------------------------------------------------

def quad(payload: Optional[dict]) -> list:
    """The line's four corners (`cnt`), or [] when absent or malformed."""
    c = (payload or {}).get("cnt")
    if not isinstance(c, list) or len(c) != 4:
        return []
    if not all(isinstance(pt, (list, tuple)) and len(pt) == 2 for pt in c):
        return []
    return [[pt[0], pt[1]] for pt in c]


def is_axis_aligned(cnt: list) -> bool:
    """True when the quadrilateral is an upright rectangle (<=2 distinct x and
    <=2 distinct y). False means the line is rotated or skewed."""
    if not cnt:
        return True
    return len({pt[0] for pt in cnt}) <= 2 and len({pt[1] for pt in cnt}) <= 2


def quad_bbox(cnt: list) -> dict:
    """The axis-aligned box of a quadrilateral, in `region`'s key shape."""
    if not cnt:
        return {}
    xs = [pt[0] for pt in cnt]
    ys = [pt[1] for pt in cnt]
    return {"top_left_x": min(xs), "top_left_y": min(ys),
            "width": max(xs) - min(xs), "height": max(ys) - min(ys)}


def crop_region(payload: Optional[dict]) -> dict:
    """The rectangle a crop should use.

    `region` normally, EXCEPT where `cnt` says the line is rotated/skewed and
    its own bbox is tighter — then the polygon wins, because it is MathPix's
    statement of where the content is and `region` is only a box around it.
    Lines without `cnt` (534,474 of the corpus) fall back to `region`
    unchanged, which is the whole of the pre-259 behaviour.
    """
    payload = payload or {}
    region = payload.get("region") or {}
    c = quad(payload)
    if not c or is_axis_aligned(c):
        return region
    box = quad_bbox(c)
    try:
        tighter = (box["width"] * box["height"]
                   < int(region["width"]) * int(region["height"]))
    except (KeyError, TypeError, ValueError):
        return box or region
    return box if tighter else region
