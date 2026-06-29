#!/usr/bin/env python3
"""
pdfimg_locate.py  -  Locate embedded raster images on PDF pages.

Goal
----
For each embedded raster image in a PDF, report:
  * its native pixel size and ppi             (from `pdfimages -list`)
  * its placement rectangle on the page       (from pdfplumber content-stream geometry)
  * whether it is a full-page image           (-> "nothing to do")
  * the PDF object number / extracted file     (join keys for pdfdrill)

All page geometry is reported in ONE canonical coordinate system:

    CANONICAL = points (1/72 inch), TOP-LEFT origin, y increasing DOWNWARD.

This is the SAME orientation MathPix uses in lines.json (region.top_left_x /
top_left_y / width / height and the cnt contour, ordered TL,TR,BR,BL).  MathPix
coordinates are pixels of the *rendered page image*; converting canonical points
into that space is a single uniform scale:

    scale_x = mathpix_page_image_width_px  / page_width_pt
    scale_y = mathpix_page_image_height_px / page_height_pt

We therefore also emit normalized [0,1] coordinates (resolution-independent, the
safest join key) and provide helpers to project into MathPix pixel space once the
rendered page-image dimensions (or DPI) are known.

Environment
-----------
Requires the poppler CLI tools `pdfinfo` and `pdfimages` (tested on poppler
24.02.0) and the Python package `pdfplumber`.  Ghostscript and PyMuPDF are NOT
required (neither is available in the target sandbox).

Standalone use
--------------
    python3 pdfimg_locate.py file.pdf
    python3 pdfimg_locate.py file.pdf --extract --outdir imgs --json out.json
    python3 pdfimg_locate.py file.pdf --mathpix-page-px 1654x2339   # demo MathPix px

Integration (pdfdrill)
----------------------
pdfdrill already runs pdfinfo / pdfimages and stores the text.  Pass that text in
to avoid re-running the tools:

    locate_pdf_images(pdf_path,
                      pdfinfo_text=stored_pdfinfo,
                      pdfimages_list_text=stored_pdfimages_list)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional


# --------------------------------------------------------------------------- #
# External-tool wrappers (skippable for integration via *_text arguments)
# --------------------------------------------------------------------------- #
def _which(name: str) -> Optional[str]:
    return shutil.which(name)


def run_pdfinfo(pdf_path: str) -> str:
    """Return per-page `pdfinfo` text (forces per-page Page/rot lines)."""
    n = 1
    try:
        head = subprocess.run(["pdfinfo", pdf_path], capture_output=True,
                              text=True, check=True).stdout
        m = re.search(r"^Pages:\s+(\d+)", head, re.M)
        if m:
            n = int(m.group(1))
    except Exception:
        pass
    out = subprocess.run(["pdfinfo", "-f", "1", "-l", str(n), pdf_path],
                         capture_output=True, text=True, check=True)
    return out.stdout


def run_pdfimages_list(pdf_path: str) -> str:
    out = subprocess.run(["pdfimages", "-list", pdf_path],
                         capture_output=True, text=True, check=True)
    return out.stdout


def run_pdfimages_extract(pdf_path: str, out_prefix: str, fmt: str = "all") -> list[str]:
    """Extract images; returns sorted list of produced file paths.

    fmt: 'all' (native), 'png', 'j' (jpeg), 'tiff'.  We map to pdfimages flags.
    Filenames are <prefix>-NNN.<ext> where NNN == the `num` column in -list.
    """
    flag = {"all": "-all", "png": "-png", "j": "-j", "jpeg": "-j", "tiff": "-tiff"}.get(fmt, "-all")
    d = os.path.dirname(out_prefix)
    if d:
        os.makedirs(d, exist_ok=True)
    subprocess.run(["pdfimages", flag, pdf_path, out_prefix], check=True)
    base = os.path.basename(out_prefix)
    produced = []
    for fn in os.listdir(d or "."):
        if fn.startswith(base + "-"):
            produced.append(os.path.join(d or ".", fn))
    return sorted(produced)


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #
@dataclass
class PageInfo:
    width_pt: float
    height_pt: float
    rotation: int = 0


def parse_pdfinfo(text: str) -> dict[int, PageInfo]:
    """Parse `pdfinfo -f .. -l ..` output into {page_number: PageInfo}.

    Handles both the per-page form ("Page  1 size: W x H pts") and the single
    "Page size: W x H pts" form (applied to all pages)."""
    pages: dict[int, PageInfo] = {}
    n_pages = None
    m = re.search(r"^Pages:\s+(\d+)", text, re.M)
    if m:
        n_pages = int(m.group(1))

    # Per-page size lines
    for m in re.finditer(r"^Page\s+(\d+)\s+size:\s+([\d.]+)\s+x\s+([\d.]+)\s+pts", text, re.M):
        p = int(m.group(1))
        pages.setdefault(p, PageInfo(float(m.group(2)), float(m.group(3))))
    for m in re.finditer(r"^Page\s+(\d+)\s+rot:\s+(-?\d+)", text, re.M):
        p = int(m.group(1))
        if p in pages:
            pages[p].rotation = int(m.group(2))

    if not pages:
        # Single global "Page size:" / "Page rot:"
        gm = re.search(r"^Page size:\s+([\d.]+)\s+x\s+([\d.]+)\s+pts", text, re.M)
        gr = re.search(r"^Page rot:\s+(-?\d+)", text, re.M)
        if gm:
            w, h = float(gm.group(1)), float(gm.group(2))
            rot = int(gr.group(1)) if gr else 0
            for p in range(1, (n_pages or 1) + 1):
                pages[p] = PageInfo(w, h, rot)
    return pages


@dataclass
class PdfImageRow:
    page: int
    num: int          # sequential index == extracted-file suffix
    type: str         # image / smask / stencil / ...
    width_px: int
    height_px: int
    color: str
    comp: Optional[int]
    bpc: Optional[int]
    enc: str          # jpeg / jpx / image (raw) / ccitt / ...
    object_num: Optional[int]   # PDF object number (xref) -> join key
    x_ppi: Optional[float]
    y_ppi: Optional[float]
    size: str
    ratio: str


def parse_pdfimages_list(text: str) -> list[PdfImageRow]:
    """Parse `pdfimages -list` (poppler).  Column layout (poppler 24.x):
       page num type width height color comp bpc enc interp object ID x-ppi y-ppi size ratio
    """
    rows: list[PdfImageRow] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("page ") or set(s) <= set("-"):
            continue
        f = s.split()
        if len(f) < 16 or not f[0].isdigit():
            continue

        def _int(x):
            try:
                return int(x)
            except ValueError:
                return None

        def _float(x):
            try:
                return float(x)
            except ValueError:
                return None

        rows.append(PdfImageRow(
            page=int(f[0]), num=int(f[1]), type=f[2],
            width_px=int(f[3]), height_px=int(f[4]), color=f[5],
            comp=_int(f[6]), bpc=_int(f[7]), enc=f[8],
            object_num=_int(f[10]),            # f[9]=interp, f[10]=object, f[11]=ID
            x_ppi=_float(f[12]), y_ppi=_float(f[13]),
            size=f[14], ratio=f[15],
        ))
    return rows


# --------------------------------------------------------------------------- #
# Placement geometry via pdfplumber  (top-left origin, y-down, points)
# --------------------------------------------------------------------------- #
@dataclass
class RawPlacement:
    page: int
    name: str
    x0: float
    top: float
    x1: float
    bottom: float
    src_w_px: Optional[int]
    src_h_px: Optional[int]


def placements_from_pdfplumber(pdf_path: str) -> tuple[dict[int, PageInfo], list[RawPlacement], dict[int, int]]:
    import pdfplumber
    page_info: dict[int, PageInfo] = {}
    placements: list[RawPlacement] = []
    text_chars: dict[int, int] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for pi, page in enumerate(pdf.pages, start=1):
            page_info[pi] = PageInfo(float(page.width), float(page.height),
                                     int(getattr(page, "rotation", 0) or 0))
            try:
                text_chars[pi] = len((page.extract_text() or "").strip())
            except Exception:
                text_chars[pi] = 0
            for im in page.images:
                src = im.get("srcsize") or (None, None)
                placements.append(RawPlacement(
                    page=pi,
                    name=str(im.get("name")),
                    x0=float(im["x0"]), top=float(im["top"]),
                    x1=float(im["x1"]), bottom=float(im["bottom"]),
                    src_w_px=(int(src[0]) if src[0] else None),
                    src_h_px=(int(src[1]) if src[1] else None),
                ))
    return page_info, placements, text_chars


# --------------------------------------------------------------------------- #
# Result model
# --------------------------------------------------------------------------- #
@dataclass
class ImagePlacement:
    page: int
    index_on_page: int
    # geometry (canonical: points, top-left origin, y-down)
    bbox_pt: list[float]               # [x0, y0, x1, y1]
    bbox_norm: list[float]             # fractions of page [0,1]
    width_pt: float
    height_pt: float
    coverage_w: float
    coverage_h: float
    coverage_area: float
    full_page: bool
    # native raster info
    native_px: Optional[list[int]]     # [w, h]
    ppi: Optional[list[float]]         # [x_ppi, y_ppi] from pdfimages
    # join keys / provenance
    pdfimages_num: Optional[int]       # == extracted-file suffix NNN
    object_num: Optional[int]          # PDF object number (xref)
    img_type: Optional[str]            # image / smask / ...
    img_format: Optional[str]          # enc: jpeg / jpx / raw / ...
    extracted_file: Optional[str]
    plumber_name: str
    match: str                         # unique | by_ppi | ambiguous | unmatched
    has_alpha: bool = False            # a paired soft-mask (smask) exists
    is_template: bool = False          # full-page image reused across pages
    # populated only by match_against_mathpix_lines()
    mathpix: Optional[dict] = None     # {type, text, iou, contained, line_id}


@dataclass
class PageResult:
    page: int
    width_pt: float
    height_pt: float
    rotation: int
    n_images: int
    n_fullpage: int
    nothing_to_do: bool
    rotation_warning: bool
    text_chars: int = 0
    full_page_image: bool = False   # page carried by a full-page raster, no overlay
    scan_like: bool = False         # full_page_image + non-template carrier + ~no text
    images: list[ImagePlacement] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Core
# --------------------------------------------------------------------------- #
def _derived_ppi(width_pt: float, height_pt: float, src_w: Optional[int],
                 src_h: Optional[int]) -> tuple[Optional[float], Optional[float]]:
    px = None
    py = None
    if src_w and width_pt > 0:
        px = src_w / (width_pt / 72.0)
    if src_h and height_pt > 0:
        py = src_h / (height_pt / 72.0)
    return px, py


def _match_row(pl: RawPlacement, rows: list[PdfImageRow], used: set[int]) -> tuple[Optional[PdfImageRow], str]:
    """Match a pdfplumber placement to a pdfimages row by native size, then ppi."""
    same = [r for r in rows if r.page == pl.page
            and r.width_px == pl.src_w_px and r.height_px == pl.src_h_px]
    # A transparent image lists a paired 'smask' row (same object, same size).
    # Match against the real image only; record the alpha channel separately.
    cands = [r for r in same if r.type != "smask"]
    has_alpha = any(r.type == "smask" for r in same)
    if not cands:
        return None, "unmatched", has_alpha
    if len(cands) == 1:
        has_alpha = has_alpha or any(
            r.type == "smask" and r.object_num == cands[0].object_num for r in rows
            if r.page == pl.page)
        return cands[0], "unique", has_alpha
    # disambiguate by ppi computed from the placement display size
    dpx, dpy = _derived_ppi(pl.x1 - pl.x0, pl.bottom - pl.top, pl.src_w_px, pl.src_h_px)
    best, best_err = None, 1e18
    for r in cands:
        if r.x_ppi is None or dpx is None:
            continue
        err = abs(r.x_ppi - dpx) + (abs(r.y_ppi - dpy) if (r.y_ppi and dpy) else 0)
        if r.num in used:
            err += 0.001
        if err < best_err:
            best, best_err = r, err
    if best is not None and best_err <= 3.0:
        return best, "by_ppi", has_alpha
    for r in cands:
        if r.num not in used:
            return r, "ambiguous", has_alpha
    return cands[0], "ambiguous", has_alpha


def locate_pdf_images(
    pdf_path: str,
    *,
    extract: bool = False,
    outdir: Optional[str] = None,
    extract_fmt: str = "all",
    fullpage_side_thresh: float = 0.95,
    fullpage_area_thresh: float = 0.90,
    min_side_pt: float = 0.0,
    scan_text_char_thresh: int = 12,
    pdfinfo_text: Optional[str] = None,
    pdfimages_list_text: Optional[str] = None,
) -> dict:
    """Locate embedded raster images and report them in MathPix-compatible coords.

    Parameters
    ----------
    extract            : if True, run `pdfimages` to extract files and link them.
    outdir             : directory for extracted files (default '<pdf>_images').
    fullpage_side_thresh : image counts as full-page if it covers >= this fraction
                           of BOTH page width and height.
    fullpage_area_thresh : alternative area-coverage gate (OR-ed with side gate).
    min_side_pt        : drop placements whose width or height < this (filters
                           rule/spacer images).  0 = keep all.
    pdfinfo_text / pdfimages_list_text : pre-computed tool output (pdfdrill).
    """
    pdf_path = os.fspath(pdf_path)

    # 1) page sizes + image inventory (prefer caller-supplied text)
    if pdfinfo_text is None:
        pdfinfo_text = run_pdfinfo(pdf_path)
    if pdfimages_list_text is None:
        pdfimages_list_text = run_pdfimages_list(pdf_path)
    info_pages = parse_pdfinfo(pdfinfo_text)
    rows = parse_pdfimages_list(pdfimages_list_text)

    # 2) placements (must read the PDF itself)
    plumber_pages, placements, text_chars = placements_from_pdfplumber(pdf_path)

    # page geometry: trust pdfinfo where available, else pdfplumber
    page_geom: dict[int, PageInfo] = {}
    for p, pi in plumber_pages.items():
        page_geom[p] = info_pages.get(p, pi)

    # 3) optional extraction -> map num -> filepath
    num_to_file: dict[int, str] = {}
    if extract:
        outdir = outdir or (os.path.splitext(os.path.basename(pdf_path))[0] + "_images")
        os.makedirs(outdir, exist_ok=True)
        files = run_pdfimages_extract(pdf_path, os.path.join(outdir, "img"), fmt=extract_fmt)
        for fp in files:
            m = re.search(r"-(\d+)\.[^.]+$", fp)
            if m:
                num_to_file[int(m.group(1))] = fp

    # 4) build per-page results
    used_rows: set[int] = set()
    pages_out: list[PageResult] = []
    by_page: dict[int, list[RawPlacement]] = {}
    for pl in placements:
        by_page.setdefault(pl.page, []).append(pl)

    doc_has_non_fullpage = False

    for p in sorted(page_geom):
        geom = page_geom[p]
        W, H = geom.width_pt, geom.height_pt
        rot_warn = (geom.rotation % 360) != 0
        imgs_out: list[ImagePlacement] = []
        pls = by_page.get(p, [])
        idx = 0
        for pl in pls:
            w_pt = pl.x1 - pl.x0
            h_pt = pl.bottom - pl.top
            if min_side_pt and (w_pt < min_side_pt or h_pt < min_side_pt):
                continue
            row, how, has_alpha = _match_row(pl, rows, used_rows)
            if row is not None:
                used_rows.add(row.num)

            cov_w = (w_pt / W) if W else 0.0
            cov_h = (h_pt / H) if H else 0.0
            cov_a = cov_w * cov_h
            full = (cov_w >= fullpage_side_thresh and cov_h >= fullpage_side_thresh) \
                or (cov_a >= fullpage_area_thresh)

            native = None
            if pl.src_w_px and pl.src_h_px:
                native = [pl.src_w_px, pl.src_h_px]
            elif row:
                native = [row.width_px, row.height_px]

            ppi = None
            if row and row.x_ppi is not None:
                ppi = [row.x_ppi, row.y_ppi]
            else:
                dpx, dpy = _derived_ppi(w_pt, h_pt, native[0] if native else None,
                                        native[1] if native else None)
                if dpx:
                    ppi = [round(dpx, 1), round(dpy, 1) if dpy else None]

            bbox_pt = [round(pl.x0, 3), round(pl.top, 3), round(pl.x1, 3), round(pl.bottom, 3)]
            bbox_norm = [round(pl.x0 / W, 6), round(pl.top / H, 6),
                         round(pl.x1 / W, 6), round(pl.bottom / H, 6)] if (W and H) else [0, 0, 0, 0]

            imgs_out.append(ImagePlacement(
                page=p, index_on_page=idx,
                bbox_pt=bbox_pt, bbox_norm=bbox_norm,
                width_pt=round(w_pt, 3), height_pt=round(h_pt, 3),
                coverage_w=round(cov_w, 4), coverage_h=round(cov_h, 4),
                coverage_area=round(cov_a, 4), full_page=bool(full),
                native_px=native, ppi=ppi,
                pdfimages_num=(row.num if row else None),
                object_num=(row.object_num if row else None),
                img_type=(row.type if row else None),
                img_format=(row.enc if row else None),
                extracted_file=(num_to_file.get(row.num) if row else None),
                plumber_name=pl.name, match=how, has_alpha=has_alpha,
            ))
            idx += 1

        n_full = sum(1 for im in imgs_out if im.full_page)
        n_non_full = len(imgs_out) - n_full
        if n_non_full > 0:
            doc_has_non_fullpage = True
        pages_out.append(PageResult(
            page=p, width_pt=round(W, 3), height_pt=round(H, 3),
            rotation=geom.rotation, n_images=len(imgs_out), n_fullpage=n_full,
            nothing_to_do=(n_non_full == 0), rotation_warning=rot_warn,
            text_chars=text_chars.get(p, 0),
            full_page_image=(n_full >= 1 and n_non_full == 0),
            images=imgs_out,
        ))

    # Template/background detection: an image object used full-page on >1 page
    # (e.g. a slide-master background) is almost never something to annotate.
    fullpage_pages: dict[int, list[int]] = {}
    for pr in pages_out:
        for im in pr.images:
            if im.full_page and im.object_num is not None:
                fullpage_pages.setdefault(im.object_num, []).append(pr.page)
    templates = {obj: pgs for obj, pgs in fullpage_pages.items() if len(pgs) > 1}
    for pr in pages_out:
        for im in pr.images:
            if im.object_num in templates:
                im.is_template = True

    # scan_like: a full-page-image page whose carrier is NOT a reused template and
    # which has (almost) no born-digital text layer -> a scanned/composite page.
    # On such pages, figures live only inside the raster and must come from MathPix.
    for pr in pages_out:
        if pr.full_page_image:
            carrier_is_template = any(im.full_page and im.is_template for im in pr.images)
            pr.scan_like = (not carrier_is_template) and pr.text_chars < scan_text_char_thresh

    return {
        "pdf": pdf_path,
        "n_pages": len(page_geom),
        "coordinate_system": {
            "units": "points (1/72 inch)",
            "origin": "top-left",
            "y_axis": "down",
            "note": "Same orientation as MathPix lines.json. Use bbox_to_mathpix_px() "
                    "with the rendered page-image dimensions, or compare bbox_norm.",
        },
        "tools": {
            "pdfinfo": _which("pdfinfo"),
            "pdfimages": _which("pdfimages"),
            "ghostscript": _which("gs"),
        },
        "templates": {str(o): pgs for o, pgs in templates.items()},
        "scan_like_pages": [pr.page for pr in pages_out if pr.scan_like],
        "nothing_to_do": (not doc_has_non_fullpage),
        "pages": [_page_to_dict(pr) for pr in pages_out],
    }


def _page_to_dict(pr: PageResult) -> dict:
    d = asdict(pr)
    return d


# --------------------------------------------------------------------------- #
# MathPix coordinate helpers (for the pdfdrill integration)
# --------------------------------------------------------------------------- #
def bbox_to_mathpix_px(bbox_pt, page_w_pt, page_h_pt,
                       page_img_w_px, page_img_h_px) -> list[float]:
    """Project a canonical point-bbox into MathPix rendered-page pixel space.

    page_img_w_px / page_img_h_px are the dimensions of the page image MathPix
    rendered (the image referenced by lines.json `image_id`).  Returns
    [top_left_x, top_left_y, bottom_right_x, bottom_right_y] in pixels.
    """
    sx = page_img_w_px / page_w_pt
    sy = page_img_h_px / page_h_pt
    return [bbox_pt[0] * sx, bbox_pt[1] * sy, bbox_pt[2] * sx, bbox_pt[3] * sy]


def bbox_to_px_at_dpi(bbox_pt, dpi: float) -> list[float]:
    """Project a canonical point-bbox into pixels at a known render DPI."""
    s = dpi / 72.0
    return [c * s for c in bbox_pt]


def mathpix_region_to_norm(region: dict, page_img_w_px: float, page_img_h_px: float) -> list[float]:
    """Convert a MathPix lines.json `region` (pixels) to normalized [0,1] bbox."""
    x0 = region["top_left_x"] / page_img_w_px
    y0 = region["top_left_y"] / page_img_h_px
    x1 = (region["top_left_x"] + region["width"]) / page_img_w_px
    y1 = (region["top_left_y"] + region["height"]) / page_img_h_px
    return [x0, y0, x1, y1]


def iou(a, b) -> float:
    """Intersection-over-union of two [x0,y0,x1,y1] boxes (same coord system)."""
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


def fraction_inside(inner, outer) -> float:
    """Fraction of `inner` box area contained within `outer` box."""
    ix0, iy0 = max(inner[0], outer[0]), max(inner[1], outer[1])
    ix1, iy1 = min(inner[2], outer[2]), min(inner[3], outer[3])
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    area = (inner[2] - inner[0]) * (inner[3] - inner[1])
    return (inter / area) if area > 0 else 0.0


def mathpix_page_dims(lines_json: dict) -> dict[int, tuple[int, int]]:
    """Return {page_number: (page_width_px, page_height_px)} from a lines.json.

    These are the dimensions of the page image MathPix rendered; they are the
    authoritative scale for projecting canonical point/normalized boxes into
    MathPix pixel coordinates (page_width_px / page_width_pt)."""
    out = {}
    for p in lines_json.get("pages", []):
        if "page_width" in p and "page_height" in p:
            out[int(p["page"])] = (int(p["page_width"]), int(p["page_height"]))
    return out


def match_against_mathpix_lines(
    result: dict,
    lines_json: dict,
    *,
    contain_thresh: float = 0.5,
    iou_thresh: float = 0.3,
    types: Optional[tuple[str, ...]] = None,
    include_full_page: bool = False,
) -> dict:
    """Associate each located image with the MathPix line(s) drawn over it.

    For every non-template image placement, find overlapping MathPix lines
    (matched in normalized page space, so render DPI is irrelevant) and attach
    the best one to ImagePlacement-equivalent dict as `mathpix`:
        {type, text, iou, contained, line_id}
    plus a full `mathpix_candidates` list.  This is the link pdfdrill uses to
    decide whether an embedded image is really recognized text/LaTeX (replace
    it) or a genuine figure/photo needing vision (e.g. a `diagram`).

    `types` optionally restricts to certain MathPix line types; default = all.
    Mutates and returns `result`.
    """
    per_page: dict[int, list[tuple]] = {}
    for p in lines_json.get("pages", []):
        W, H = p.get("page_width"), p.get("page_height")
        if not (W and H):
            continue
        items = []
        for ln in p["lines"]:
            r = ln.get("region")
            if not r:
                continue
            if types and ln.get("type") not in types:
                continue
            rn = [r["top_left_x"] / W, r["top_left_y"] / H,
                  (r["top_left_x"] + r["width"]) / W, (r["top_left_y"] + r["height"]) / H]
            txt = ln.get("text") or ln.get("text_display") or ""
            items.append((ln.get("type"), txt, ln.get("id"), rn))
        per_page[int(p["page"])] = items

    dims = mathpix_page_dims(lines_json)
    for pg in result["pages"]:
        pg["mathpix_render_px"] = list(dims.get(pg["page"], (None, None)))
        lines = per_page.get(pg["page"], [])
        for im in pg["images"]:
            if im.get("is_template") and not include_full_page:
                continue
            if im.get("full_page") and not include_full_page:
                continue
            cands = []
            for typ, txt, lid, rn in lines:
                c = fraction_inside(im["bbox_norm"], rn)
                i = iou(im["bbox_norm"], rn)
                if c >= contain_thresh or i >= iou_thresh:
                    cands.append({"type": typ, "text": txt, "line_id": lid,
                                  "iou": round(i, 3), "contained": round(c, 3)})
            cands.sort(key=lambda d: (d["contained"], d["iou"]), reverse=True)
            im["mathpix"] = cands[0] if cands else None
            im["mathpix_candidates"] = cands
    return result


# --------------------------------------------------------------------------- #
# MathPix-only figures (figures isolated by OCR inside a full-page raster).
# These do NOT appear as distinct XObjects in `pdfimages -list`, so they can
# only be found via lines.json and cropped from a rendered page.
# --------------------------------------------------------------------------- #
def mathpix_only_figures(
    result: dict,
    lines_json: dict,
    *,
    figure_types: tuple[str, ...] = ("diagram", "image", "figure", "chart"),
    scan_pages_only: bool = True,
    exclude_overlay_iou: float = 0.5,
    min_area_frac: float = 0.004,
    edge_decoration_frac: float = 0.0,
) -> dict:
    """Find figure regions that exist only in MathPix output, not as XObjects.

    The classic case (composite/scanned documents): a page is a single full-page
    raster, so `pdfimages -list` shows one full-page image and the locator marks
    the page `nothing_to_do` for embedded extraction -- yet MathPix's OCR has
    isolated real figures *inside* that raster.  Those figures are returned here
    with bboxes in the canonical system so they can be cropped from a render.

    By default only `scan_like` pages are considered, which avoids resurfacing
    template decorations / vector tables on born-digital pages (set
    scan_pages_only=False to consider every page).  A figure region overlapping
    an already-located embedded overlay (IoU >= exclude_overlay_iou) is skipped
    as a duplicate.  Adds `result["pages"][i]["mathpix_figures"]` (a list) and
    returns result.
    """
    scan_pages = {p["page"] for p in result["pages"] if p.get("scan_like")}
    per_page = {}
    for p in lines_json.get("pages", []):
        per_page[int(p["page"])] = p

    for pg in result["pages"]:
        pg["mathpix_figures"] = []
        if scan_pages_only and pg["page"] not in scan_pages:
            continue
        mp = per_page.get(pg["page"])
        if not mp:
            continue
        W, H = mp.get("page_width"), mp.get("page_height")
        if not (W and H):
            continue
        overlays = [im["bbox_norm"] for im in pg["images"] if not im["full_page"]]
        for ln in mp["lines"]:
            if ln.get("type") not in figure_types:
                continue
            r = ln.get("region")
            if not r:
                continue
            rn = [r["top_left_x"] / W, r["top_left_y"] / H,
                  (r["top_left_x"] + r["width"]) / W, (r["top_left_y"] + r["height"]) / H]
            area = (rn[2] - rn[0]) * (rn[3] - rn[1])
            if area < min_area_frac:
                continue
            if any(iou(rn, ov) >= exclude_overlay_iou for ov in overlays):
                continue  # already an extractable embedded image
            Wp, Hp = pg["width_pt"], pg["height_pt"]
            pg["mathpix_figures"].append({
                "source": "mathpix",
                "type": ln.get("type"),
                "line_id": ln.get("id"),
                "text": ln.get("text") or "",
                "bbox_norm": [round(v, 6) for v in rn],
                "bbox_pt": [round(rn[0] * Wp, 3), round(rn[1] * Hp, 3),
                            round(rn[2] * Wp, 3), round(rn[3] * Hp, 3)],
                "bbox_render_px": [r["top_left_x"], r["top_left_y"],
                                   r["top_left_x"] + r["width"], r["top_left_y"] + r["height"]],
                "render_page_px": [W, H],
                "extracted_file": None,
            })
    return result


def render_page_png(pdf_path: str, page_number: int, dpi: int, out_path_noext: str) -> str:
    """Render one PDF page to PNG via Ghostscript (>= 400 DPI; the only
    rasterizer). Returns the file path."""
    from pathlib import Path as _P
    from . import pdf_reading
    out = out_path_noext + ".png"
    pdf_reading.render_page(_P(pdf_path), page_number, _P(out), dpi=dpi)
    return out


def extract_mathpix_figures(
    result: dict,
    lines_json: dict,
    pdf_path: str,
    outdir: str,
    *,
    dpi: Optional[int] = None,
    **figure_kwargs,
) -> dict:
    """Crop MathPix-only figures out of a rendered page (since they are not
    XObjects).  Renders each affected page once at `dpi` (default: the DPI
    MathPix itself used, derived from page_width_px / page_width_pt), crops by
    normalized bbox, writes PNGs, and sets each figure's `extracted_file`.
    """
    from PIL import Image
    mathpix_only_figures(result, lines_json, **figure_kwargs)
    os.makedirs(outdir, exist_ok=True)
    dims = mathpix_page_dims(lines_json)
    for pg in result["pages"]:
        figs = pg.get("mathpix_figures") or []
        if not figs:
            continue
        page_dpi = dpi
        if page_dpi is None:
            wpx = dims.get(pg["page"], (None, None))[0]
            page_dpi = int(round(wpx / pg["width_pt"] * 72)) if wpx else 200
        png = render_page_png(pdf_path, pg["page"], page_dpi,
                              os.path.join(outdir, f"page{pg['page']:03d}"))
        im = Image.open(png)
        W, H = im.size
        for k, fig in enumerate(figs):
            x0, y0, x1, y1 = fig["bbox_norm"]
            box = (int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H))
            crop = im.crop(box)
            fp = os.path.join(outdir, f"page{pg['page']:03d}_fig{k:02d}.png")
            crop.save(fp)
            fig["extracted_file"] = fp
    return result


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_report(res: dict, mathpix_px: Optional[tuple[int, int]] = None) -> None:
    print(f"PDF: {res['pdf']}   pages={res['n_pages']}   "
          f"nothing_to_do={res['nothing_to_do']}")
    print(f"coords: points, top-left origin, y-down "
          f"(gs={'yes' if res['tools']['ghostscript'] else 'absent'})")
    for pg in res["pages"]:
        tag = "  [NOTHING TO DO]" if pg["nothing_to_do"] else ""
        if pg.get("scan_like"):
            tag += "  [SCAN-LIKE: check MathPix figures]"
        warn = "  [ROTATED - geometry may need check]" if pg["rotation_warning"] else ""
        print(f"\nPage {pg['page']}  {pg['width_pt']}x{pg['height_pt']} pt  "
              f"rot={pg['rotation']}  images={pg['n_images']} "
              f"(full-page={pg['n_fullpage']}){tag}{warn}")
        for im in pg["images"]:
            flags = ""
            if im.get("full_page"):
                flags += "  FULL-PAGE"
            if im.get("is_template"):
                flags += "  TEMPLATE"
            if im.get("has_alpha"):
                flags += "  +alpha"
            line = (f"  #{im['index_on_page']} obj={im['object_num']} "
                    f"num={im['pdfimages_num']} {im['img_type']}/{im['img_format']} "
                    f"native={im['native_px']} ppi={im['ppi']} "
                    f"match={im['match']}" + flags)
            print(line)
            print(f"      bbox_pt   = {im['bbox_pt']}")
            print(f"      bbox_norm = {im['bbox_norm']}  "
                  f"(cov w={im['coverage_w']} h={im['coverage_h']})")
            if im["extracted_file"]:
                print(f"      file      = {im['extracted_file']}")
            if im.get("mathpix"):
                mx = im["mathpix"]
                txt = (mx["text"] or "").replace("\n", " ")[:70]
                print(f"      mathpix   = {mx['type']} (IoU={mx['iou']} "
                      f"contained={mx['contained']}) :: {txt!r}")
            if mathpix_px and not im["full_page"]:
                px = bbox_to_mathpix_px(im["bbox_pt"], pg["width_pt"], pg["height_pt"],
                                        mathpix_px[0], mathpix_px[1])
                px = [round(v, 1) for v in px]
                print(f"      mathpix_px= {px}  (page img {mathpix_px[0]}x{mathpix_px[1]})")
        for fig in pg.get("mathpix_figures", []) or []:
            txt = (fig["text"] or "").replace("\n", " ")[:60]
            print(f"  ~ MathPix-only figure ({fig['type']}) bbox_norm={fig['bbox_norm']} "
                  f"bbox_pt={fig['bbox_pt']} :: {txt!r}")
            if fig.get("extracted_file"):
                print(f"      file      = {fig['extracted_file']}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Locate embedded raster images on PDF pages "
                                             "in MathPix-compatible coordinates.")
    ap.add_argument("pdf")
    ap.add_argument("--extract", action="store_true", help="extract image files via pdfimages")
    ap.add_argument("--outdir", default=None, help="directory for extracted files")
    ap.add_argument("--fmt", default="all", choices=["all", "png", "j", "jpeg", "tiff"],
                    help="pdfimages extraction format (default: all=native)")
    ap.add_argument("--fullpage-side", type=float, default=0.95)
    ap.add_argument("--fullpage-area", type=float, default=0.90)
    ap.add_argument("--min-side-pt", type=float, default=0.0,
                    help="drop placements thinner/shorter than this (filters rules/spacers)")
    ap.add_argument("--mathpix-page-px", default=None,
                    help="WxH of the MathPix rendered page image, e.g. 1654x2339 (demo only)")
    ap.add_argument("--lines-json", default=None,
                    help="MathPix lines.json: associate each image with its recognized line(s)")
    ap.add_argument("--mathpix-figures", action="store_true",
                    help="find figures isolated by MathPix inside full-page rasters (needs --lines-json)")
    ap.add_argument("--extract-mathpix-figures", default=None, metavar="DIR",
                    help="also crop those figures from a pdftoppm render into DIR (needs --lines-json)")
    ap.add_argument("--all-pages-figures", action="store_true",
                    help="consider MathPix figures on every page, not only scan-like pages")
    ap.add_argument("--json", default=None, help="write full result JSON to this path")
    args = ap.parse_args(argv)

    mp = None
    if args.mathpix_page_px:
        m = re.match(r"(\d+)x(\d+)$", args.mathpix_page_px)
        if not m:
            ap.error("--mathpix-page-px must look like 1654x2339")
        mp = (int(m.group(1)), int(m.group(2)))

    res = locate_pdf_images(
        args.pdf, extract=args.extract, outdir=args.outdir, extract_fmt=args.fmt,
        fullpage_side_thresh=args.fullpage_side, fullpage_area_thresh=args.fullpage_area,
        min_side_pt=args.min_side_pt,
    )
    if args.lines_json:
        with open(args.lines_json) as f:
            lines_json = json.load(f)
        res = match_against_mathpix_lines(res, lines_json)
        scan_only = not args.all_pages_figures
        if args.extract_mathpix_figures:
            extract_mathpix_figures(res, lines_json, args.pdf, args.extract_mathpix_figures,
                                    scan_pages_only=scan_only)
        elif args.mathpix_figures:
            mathpix_only_figures(res, lines_json, scan_pages_only=scan_only)
    _print_report(res, mathpix_px=mp)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(res, f, indent=2)
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
