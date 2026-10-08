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
                   ext: str = "png", units: Optional[str] = "pt") -> str:
    """Build OUR pyramid crop URL for a region, or '' if id/region is missing.

    `units="pt"` says the region is in PDF POINTS — our glyph reader's frame —
    and the crop server then scales by exactly `pyramid_dpi/72`. `units=None`
    omits the key, which is how the server is told the region is in the
    lines.json's OWN PAGE-PIXEL frame: it scales by `pyramid_W/page_width`
    read from that same lines.json. Both are explicit, and that is the point —
    the unit is a property of the reading, not of whether MathPix produced it.
    """
    if not image_id or not region:
        return ""
    return (
        f"{_LOCAL_CROP_PREFIX}{image_id}.{ext}"
        f"?height={region.get('height')}&width={region.get('width')}"
        f"&top_left_y={region.get('top_left_y')}&top_left_x={region.get('top_left_x')}"
        + (f"&units={units}" if units else "")
    )


#: Readers whose `region` is in the lines.json's OWN page-pixel frame, not in
#: PDF points. MathPix is the origin of that convention; pdf2mmd2 writes the
#: same frame — measured on 1306.1660 page 3, where its `page_width`/
#: `page_height` are 2125x2750, byte-identical to MathPix's own twin of that
#: page (8.5in x 250dpi, 11in x 250dpi) and its regions share those axes.
#:
#: 897 — THIS IS WHY A `source` KEY IS NOT A FREE LABEL. `image_ref` had two
#: cases, "mathpix" and everything-else-is-points, so the moment a reading
#: declared a producer its crops were requested in the wrong unit: a region at
#: y=1400 page pixels asked for as y=1400 points, which is off the page. The
#: frame has to be carried per reader, or declared per reading.
_PAGE_PIXEL_SOURCES = ("mathpix", "pdf2mmd2")


def _is_page_pixel_source(source: str) -> bool:
    src = (source or "mathpix").lower()
    return any(src == s or src.startswith(s + "-") for s in _PAGE_PIXEL_SOURCES)


def image_ref(image_id: Optional[str], region: Optional[dict],
              source: str = "mathpix") -> str:
    """Source-aware crop reference, in THREE cases, because there are three:

      * `mathpix` — the CDN pixel URL. MathPix hosts the page image.
      * another reader in MathPix's page-pixel frame (`pdf2mmd2`) — OUR local
        pyramid, with NO `units`, so the server scales by the lines.json's own
        page dimensions. There is no CDN image to ask for; the coordinates are
        nonetheless pixels.
      * everything else (pdfminer / DRILLPDFse) — OUR local pyramid in PDF
        points, `units=pt`.

    The two coordinate systems still never mix. What changed in 897 is that
    "is it MathPix?" and "is it in pixels?" stopped being the same question.
    """
    if (source or "mathpix").lower() == "mathpix":
        return crop_url(image_id, region)
    if _is_page_pixel_source(source):
        return local_crop_url(image_id, region, units=None)
    return local_crop_url(image_id, region)


def is_local_crop(url: Optional[str]) -> bool:
    """True for one of OUR local pyramid crop URLs (`/cropped/…`), in either
    unit. It tested for `units=pt`, which was the same conflation: a
    page-pixel local crop is just as local."""
    return bool(url) and url.startswith(_LOCAL_CROP_PREFIX)


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
