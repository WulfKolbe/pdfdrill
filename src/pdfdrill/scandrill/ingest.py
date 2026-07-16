"""Ingestion producers → :class:`~scandrill.manifest.Page` entries.

This module is the shared machinery every producer (I-A find, I-B upload,
I-C camera, I-D ADF) funnels through: hash, stat, read dimensions, score
blankness, order. The blank score replicates ``scanp.sh``'s ImageMagick check
(shave a border, grayscale mean) so the ADF path and the folder/upload paths
agree on what "blank" means.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from PIL import Image

from .manifest import Manifest, Page, REMOVED_BLANK

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".ppm", ".pnm", ".bmp"}

# scanp.sh defaults: EMPTY_THRESHOLD=0.999, SHAVE_BORDER=40 (px @ 300 dpi).
DEFAULT_BLANK_THRESHOLD = 0.999
DEFAULT_SHAVE_PX = 40


def sha256_file(path: str | Path, _bufsize: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(_bufsize), b""):
            h.update(chunk)
    return h.hexdigest()


def blank_mean(path: str | Path, shave_px: int = DEFAULT_SHAVE_PX) -> float:
    """Grayscale mean of the page interior, 0..1 (1.0 == pure white).

    Mirrors ``scanp.sh``'s ``convert -shave 40x40 -colorspace Gray -format
    '%[fx:mean]'`` so blank detection is identical across producers. Uses PIL
    (no ImageMagick subprocess) — Rec.601 luma matches ImageMagick's default.
    """
    with Image.open(path) as im:
        im = im.convert("L")
        w, h = im.size
        if w > 2 * shave_px and h > 2 * shave_px:
            im = im.crop((shave_px, shave_px, w - shave_px, h - shave_px))
        # PIL mean over 0..255 → normalise to 0..1
        hist = im.histogram()
        total = sum(hist)
        if total == 0:
            return 1.0
        weighted = sum(i * n for i, n in enumerate(hist))
        return (weighted / total) / 255.0


def _natural_key(p: Path):
    """Version-aware sort key: scan_2 < scan_10 (like `sort -V`)."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def iter_images(root: str | Path, mask: str = "*", order: str = "name") -> list[Path]:
    """Find image files under ``root`` matching glob ``mask``, ordered.

    ``order``: ``"name"`` (version-aware, default) or ``"mtime"`` (oldest first).
    Equivalent to the two NUL-safe ``find | sort`` recipes in PROPOSAL.md, but
    in-process so producers share one ordering implementation.
    """
    root = Path(root)
    files = [
        p for p in root.rglob(mask)
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    if order == "mtime":
        files.sort(key=lambda p: (p.stat().st_mtime, _natural_key(p)))
    elif order == "name":
        files.sort(key=_natural_key)
    else:
        raise ValueError(f"unknown order {order!r} (use 'name' or 'mtime')")
    return files


def add_path(
    manifest: Manifest,
    path: str | Path,
    origin: dict,
    *,
    rel_to: str | Path | None = None,
    blank_threshold: float | None = DEFAULT_BLANK_THRESHOLD,
) -> Page:
    """Hash/stat/measure one image and append it as a :class:`Page`."""
    path = Path(path)
    st = path.stat()
    with Image.open(path) as im:
        width, height = im.size
        dpi = im.info.get("dpi")
        dpi = (int(dpi[0]), int(dpi[1])) if dpi else None

    bmean = blank_mean(path)
    src = str(path.relative_to(rel_to)) if rel_to else str(path)
    page = Page(
        seq=0,  # assigned by Manifest.add
        src=src,
        origin=dict(origin),
        sha256=sha256_file(path),
        mtime=st.st_mtime,
        width=width,
        height=height,
        dpi=dpi,
        blank_mean=round(bmean, 6),
    )
    if blank_threshold is not None and bmean > blank_threshold:
        page.status = REMOVED_BLANK
    manifest.add(page)
    return page


def add_folder(
    manifest: Manifest,
    root: str | Path,
    *,
    mask: str = "*",
    order: str = "name",
    origin_kind: str = "find",
    rel_to: str | Path | None = None,
    blank_threshold: float | None = DEFAULT_BLANK_THRESHOLD,
) -> list[Page]:
    """I-A producer: ingest every image under ``root`` in the chosen order."""
    added = []
    for p in iter_images(root, mask=mask, order=order):
        added.append(
            add_path(
                manifest, p,
                origin={"kind": origin_kind, "path": str(p)},
                rel_to=rel_to,
                blank_threshold=blank_threshold,
            )
        )
    return added
