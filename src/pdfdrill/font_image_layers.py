"""pdffonts + pdfimages-derived layers.

Two structured top-level layers in the sidecar:

  fonts_layer  → list[FontRecord]
                 from `pdffonts <pdf>`
                 each record: name, base_name, family, type, encoding,
                 embedded, subset, unicode, object_id, is_math, is_bold,
                 is_italic, is_subscript_size, ...

  images_layer → list[ImageRecord]
                 from `pdfimages -list <pdf>` + pdfplumber page.images
                 each record: page, x0, y0, x1, y1, w_pt, h_pt, w_px,
                 h_px, x_ppi, y_ppi, color, encoding, kind, file_kb,
                 ratio, name, candidate_pix2latex

The images_layer also exposes a fast `chars_in_rect(page, char_meta)`
helper used by the math/text pipeline to prune spurious characters from
EPS streams, and a `pix2latex_candidates()` helper that yields likely
equation regions for further inspection.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# pdffonts parsing
# ---------------------------------------------------------------------------

_MATH_FONT_HINTS = (
    "math", "msbm", "msam", "eufm", "cmsy", "cmmi", "cmex", "symbol",
    "mt2mi", "mt2sy", "newpxmi", "pxsy", "stixmath", "rsfs", "mathpi",
)


def _classify_font_family(name: str) -> tuple[str, bool, bool, bool]:
    """Return (base_name, is_math, is_bold, is_italic) from a font name."""
    base = name.split("+", 1)[-1] if "+" in name else name
    low = base.lower()
    is_math = any(h in low for h in _MATH_FONT_HINTS)
    is_bold = "bold" in low or "-bd" in low or "medi" in low
    is_italic = ("ital" in low or "-it" in low) and not is_math
    return base, is_math, is_bold, is_italic


def fetch_fonts(pdf: Path) -> list[dict[str, Any]]:
    """Parse `pdffonts <pdf>` output into structured records."""
    out = _run(["pdffonts", str(pdf)])
    return _parse_pdffonts(out)


def _parse_pdffonts(out: str) -> list[dict[str, Any]]:
    lines = out.strip().splitlines()
    if len(lines) < 2:
        return []
    # Header line determines column boundaries; the data lines that follow
    # are space-separated but field positions are deterministic.
    fonts: list[dict[str, Any]] = []
    for line in lines[2:]:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) < 7:
            continue
        # Reverse-fill known-shape columns from the right; name may contain
        # spaces in some rare pdffonts outputs.
        try:
            obj_num = parts[-2]
            obj_gen = parts[-1]
            uni = parts[-3]
            sub = parts[-4]
            emb = parts[-5]
            # encoding can also contain whitespace ("Identity-H"), but it's a
            # single token in practice; type is two tokens for "Type 1C", "Type 3", etc.
            # Encoding is at parts[-6]; type is whatever is left between name and encoding.
            encoding = parts[-6]
            # Find where the type starts. Type starts with "Type", "TrueType", "CID", etc.
            type_start = None
            for i in range(len(parts) - 7, -1, -1):
                token = parts[i]
                if token.startswith(("Type", "TrueType", "CID", "PostScript")):
                    type_start = i
                    break
            if type_start is None:
                continue
            name = " ".join(parts[:type_start])
            ftype = " ".join(parts[type_start:-6])
        except (IndexError, ValueError):
            continue

        base, is_math, is_bold, is_italic = _classify_font_family(name)
        fonts.append({
            "name": name,
            "base_name": base,
            "family": base.split("-", 1)[0],
            "type": ftype,
            "encoding": encoding,
            "embedded": emb.lower() in ("yes", "y", "true"),
            "subset": sub.lower() in ("yes", "y", "true"),
            "unicode": uni.lower() in ("yes", "y", "true"),
            "object_id": f"{obj_num} {obj_gen}",
            "is_math": is_math,
            "is_bold": is_bold,
            "is_italic": is_italic,
        })
    return fonts


def summarize_fonts(fonts: list[dict[str, Any]]) -> dict[str, Any]:
    """Compact summary used by the prose formatter."""
    families = sorted({f["family"] for f in fonts})
    math_fonts = [f for f in fonts if f["is_math"]]
    bold_fonts = [f for f in fonts if f["is_bold"]]
    italic_fonts = [f for f in fonts if f["is_italic"]]
    not_embedded = [f for f in fonts if not f["embedded"]]
    return {
        "n_fonts": len(fonts),
        "n_families": len(families),
        "families": families,
        "n_math": len(math_fonts),
        "math_families": sorted({f["family"] for f in math_fonts}),
        "n_bold": len(bold_fonts),
        "n_italic": len(italic_fonts),
        "n_not_embedded": len(not_embedded),
    }


# ---------------------------------------------------------------------------
# pdfimages -list parsing
# ---------------------------------------------------------------------------

_IMG_HEADER = re.compile(r"^page\s+num\s+type", re.I)


def fetch_pdfimages_list(pdf: Path) -> list[dict[str, Any]]:
    """Parse `pdfimages -list <pdf>` into records keyed by (page, obj_id)."""
    out = _run(["pdfimages", "-list", str(pdf)], timeout=60)
    return _parse_pdfimages_list(out)


def _parse_pdfimages_list(out: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in out.splitlines():
        s = line.strip()
        if not s or _IMG_HEADER.match(s) or s.startswith("-"):
            continue
        parts = s.split()
        if len(parts) < 12:
            continue
        try:
            page = int(parts[0])
            num = int(parts[1])
            kind = parts[2]
            width_px = int(parts[3])
            height_px = int(parts[4])
            color = parts[5]
            # comp = int(parts[6]); bpc = int(parts[7])
            encoding = parts[8]
            # interp = parts[9]
            obj_id = parts[10]
            obj_gen = parts[11]
            x_ppi = _as_int_or_none(parts[12]) if len(parts) > 12 else None
            y_ppi = _as_int_or_none(parts[13]) if len(parts) > 13 else None
            size_str = parts[14] if len(parts) > 14 else ""
            ratio_str = parts[15].rstrip("%") if len(parts) > 15 else ""
        except (IndexError, ValueError):
            continue
        records.append({
            "page": page,
            "image_num": num,
            "kind": kind,
            "width_px": width_px,
            "height_px": height_px,
            "color": color,
            "encoding": encoding,
            "object_id": f"{obj_id} {obj_gen}",
            "x_ppi": x_ppi,
            "y_ppi": y_ppi,
            "size_str": size_str,
            "size_bytes": _parse_size(size_str),
            "ratio_pct": _as_float_or_none(ratio_str),
        })
    return records


def _as_int_or_none(s: str) -> int | None:
    try:
        return int(s)
    except ValueError:
        return None


def _as_float_or_none(s: str) -> float | None:
    try:
        return float(s)
    except ValueError:
        return None


def _parse_size(s: str) -> int:
    """Parse "18.8K", "1.2M", "430K" → bytes."""
    if not s:
        return 0
    m = re.match(r"(\d+(?:\.\d+)?)\s*([KMG]?)B?", s)
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2)
    return int(val * {"K": 1024, "M": 1024**2, "G": 1024**3, "": 1}.get(unit, 1))


# ---------------------------------------------------------------------------
# Images layer (positions from pdfplumber, metadata from pdfimages -list)
# ---------------------------------------------------------------------------

def fetch_image_layer(pdf: Path) -> list[dict[str, Any]]:
    """Build the unified images_layer.

    Positions come from pdfplumber's `page.images`; per-image metadata
    (encoding, ppi, file size) is joined in from `pdfimages -list` by
    (page, object_id) where available.
    """
    plumber_imgs = _fetch_pdfplumber_images(pdf)
    metadata_list = fetch_pdfimages_list(pdf)

    # Index pdfimages records by (page, object_id_num)
    by_key: dict[tuple[int, str], dict[str, Any]] = {}
    for rec in metadata_list:
        obj_num = rec["object_id"].split()[0]
        by_key[(rec["page"], obj_num)] = rec

    records: list[dict[str, Any]] = []
    for img in plumber_imgs:
        page = img["page"]
        obj_num = _stream_object_num(img.get("stream_repr", ""))
        meta = by_key.get((page, obj_num)) if obj_num else None

        x0, y0, x1, y1 = img["x0"], img["top"], img["x1"], img["bottom"]
        rec: dict[str, Any] = {
            "page": page,
            "x0": round(x0, 2),
            "y0": round(y0, 2),
            "x1": round(x1, 2),
            "y1": round(y1, 2),
            "w_pt": round(x1 - x0, 2),
            "h_pt": round(y1 - y0, 2),
            "name": img.get("name", ""),
            "imagemask": img.get("imagemask", False),
        }
        if meta:
            rec.update({
                "width_px": meta["width_px"],
                "height_px": meta["height_px"],
                "encoding": meta["encoding"],
                "color": meta["color"],
                "x_ppi": meta["x_ppi"],
                "y_ppi": meta["y_ppi"],
                "size_bytes": meta["size_bytes"],
                "object_id": meta["object_id"],
            })
        rec["candidate_pix2latex"] = _is_pix2latex_candidate(rec)
        records.append(rec)

    # Append images that pdfimages -list saw but pdfplumber didn't surface
    # with a position (unusual but possible for inline / softmask images).
    seen_obj_keys = {
        (r["page"], r.get("object_id", "").split()[0])
        for r in records if r.get("object_id")
    }
    for meta in metadata_list:
        obj_num = meta["object_id"].split()[0]
        if (meta["page"], obj_num) in seen_obj_keys:
            continue
        records.append({
            "page": meta["page"],
            "x0": None, "y0": None, "x1": None, "y1": None,
            "w_pt": None, "h_pt": None,
            "width_px": meta["width_px"],
            "height_px": meta["height_px"],
            "encoding": meta["encoding"],
            "color": meta["color"],
            "x_ppi": meta["x_ppi"],
            "y_ppi": meta["y_ppi"],
            "size_bytes": meta["size_bytes"],
            "object_id": meta["object_id"],
            "name": "",
            "imagemask": False,
            "position_unknown": True,
            "candidate_pix2latex": False,
        })

    records.sort(key=lambda r: (r["page"], r.get("y0") or 0, r.get("x0") or 0))
    return records


def _fetch_pdfplumber_images(pdf: Path) -> list[dict[str, Any]]:
    """Return image positions via pdfplumber, per-page."""
    import pdfplumber
    images: list[dict[str, Any]] = []
    with pdfplumber.open(pdf) as pdf_obj:
        for page in pdf_obj.pages:
            for img in page.images:
                images.append({
                    "page": page.page_number,
                    "x0": float(img.get("x0", 0)),
                    "top": float(img.get("top", img.get("y0", 0))),
                    "x1": float(img.get("x1", 0)),
                    "bottom": float(img.get("bottom", img.get("y1", 0))),
                    "name": img.get("name", ""),
                    "imagemask": bool(img.get("imagemask", False)),
                    "stream_repr": repr(img.get("stream", "")),
                })
    return images


_STREAM_OBJ_RE = re.compile(r"PDFStream\((\d+)\)")


def _stream_object_num(stream_repr: str) -> str:
    m = _STREAM_OBJ_RE.search(stream_repr or "")
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# pix2latex candidate detection
# ---------------------------------------------------------------------------

def _is_pix2latex_candidate(rec: dict[str, Any]) -> bool:
    """A pdfimages-listed image is a pix2latex candidate if it's a small
    inline graphic with relatively low ppi — characteristic of an
    embedded equation rendered as a bitmap.
    """
    w_pt = rec.get("w_pt")
    h_pt = rec.get("h_pt")
    ppi = rec.get("x_ppi") or 0
    if w_pt is None or h_pt is None:
        return False
    # Embedded equation bitmaps are small (< ~3 inches wide) and rasterized
    # at typical screen/print resolutions.
    width_in = w_pt / 72.0
    height_in = h_pt / 72.0
    if width_in > 4.0 or height_in > 2.0:
        return False
    if ppi and ppi < 96:
        return False
    return True


# ---------------------------------------------------------------------------
# Geometry helpers (used downstream by the math/text pipeline)
# ---------------------------------------------------------------------------

def image_rects_per_page(images: list[dict[str, Any]]) -> dict[int, list[tuple[float, float, float, float]]]:
    """Group positioned images by page → [(x0, y0, x1, y1), ...]."""
    out: dict[int, list[tuple[float, float, float, float]]] = {}
    for rec in images:
        if rec.get("position_unknown") or rec.get("x0") is None:
            continue
        out.setdefault(rec["page"], []).append(
            (rec["x0"], rec["y0"], rec["x1"], rec["y1"])
        )
    return out


def char_falls_inside(rects: list[tuple[float, float, float, float]],
                      x0: float, y0: float, x1: float, y1: float) -> bool:
    """True if the char bbox center is inside any image rect on the page."""
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    for rx0, ry0, rx1, ry1 in rects:
        if rx0 <= cx <= rx1 and ry0 <= cy <= ry1:
            return True
    return False


def mark_chars_inside_images(
    char_meta_like: list[dict[str, Any]],
    images_layer: list[dict[str, Any]],
) -> list[bool]:
    """Return a boolean mask, one entry per char, True ↔ char is inside an
    image rectangle on the same page.

    Used by the pdfplumber ingest stage to prune spurious chars that come
    from EPS image streams. Each char dict needs `page`, `x0`, `top`,
    `x1`, `bottom` (pdfplumber's natural keys).
    """
    rects_by_page = image_rects_per_page(images_layer)
    mask: list[bool] = []
    for ch in char_meta_like:
        page = ch.get("page") or ch.get("page_number") or 0
        rects = rects_by_page.get(page, [])
        if not rects:
            mask.append(False)
            continue
        mask.append(char_falls_inside(
            rects,
            ch.get("x0", 0),
            ch.get("top", ch.get("y0", 0)),
            ch.get("x1", 0),
            ch.get("bottom", ch.get("y1", 0)),
        ))
    return mask


def pix2latex_candidate_rects(
    images_layer: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the image records flagged as pix2latex candidates with their
    rectangles, ready to be handed off to MathPix / pix2tex.
    """
    return [
        {
            "page": r["page"],
            "x0": r["x0"], "y0": r["y0"], "x1": r["x1"], "y1": r["y1"],
            "w_pt": r["w_pt"], "h_pt": r["h_pt"],
            "encoding": r.get("encoding"),
            "x_ppi": r.get("x_ppi"),
            "y_ppi": r.get("y_ppi"),
        }
        for r in images_layer
        if r.get("candidate_pix2latex") and r.get("x0") is not None
    ]


# ---------------------------------------------------------------------------
# Subprocess wrapper
# ---------------------------------------------------------------------------

def _run(cmd: list[str], timeout: int = 30) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout
    except (subprocess.SubprocessError, OSError):
        return ""
