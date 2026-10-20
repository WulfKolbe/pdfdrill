"""Stage II-D: lossless images → one PDF, the genuinely new core.

pdfdrill is PDF-*in* and has no image→PDF assembly (its deps carry ``pypdf`` but
not ``img2pdf``). This module fills that gap:

    kept pages in seq order → img2pdf (no re-encode) → pikepdf metadata pass

img2pdf embeds JPEG streams verbatim (``/DCTDecode``) and PNG pixels via
``/FlateDecode`` — pixels are bit-identical either way. pikepdf then stamps the
document ``/Lang``, Title/Producer, and PDF page labels.
"""

from __future__ import annotations

from pathlib import Path

import img2pdf
import pikepdf

from .manifest import Manifest
from .meta import DocMeta, stamp


def resolve_srcs(manifest: Manifest, job_dir: str | Path | None = None) -> list[Path]:
    """Absolute paths of kept pages, in seq order."""
    base = Path(job_dir) if job_dir else None
    out = []
    for p in sorted(manifest.kept_pages(), key=lambda pg: pg.seq):
        src = Path(p.src)
        if not src.is_absolute() and base is not None:
            src = base / src
        out.append(src)
    return out


def assemble(
    manifest: Manifest,
    out_pdf: str | Path,
    *,
    job_dir: str | Path | None = None,
    meta: DocMeta | None = None,
    title: str | None = None,
    ocr: bool = False,
    ocr_lang: str | None = None,
) -> Path:
    """Write the lossless PDF for all kept pages and stamp its metadata.

    The two stages are deliberately separate and only the first touches pixels
    (and even that one doesn't re-encode them):

    1. ``img2pdf`` — wraps the original streams. JPEG → ``/DCTDecode`` verbatim,
       PNG → ``/FlateDecode`` with identical pixels. Never re-encodes.
    2. ``meta.stamp`` — /Lang, XMP + DocInfo, page labels. Metadata only.

    There was a third stage: an invisible tesseract text layer, grafted on
    request. It is gone, and it should never have been reachable — a text layer
    makes `route` read a SCAN as born-digital and pick the text-layer lane over
    the one that can actually read it, which is the misroute
    `docs/LANES.md` exists to prevent. ``ocr``/``ocr_lang`` are accepted and
    REFUSED, so a caller that still passes them is told why rather than silently
    getting a different PDF.

    Returns the output path. Raises ValueError if there are no kept pages, or if
    ``ocr`` is requested.
    """
    if ocr:
        raise ValueError(
            "scandrill no longer grafts an OCR text layer: it would make "
            "`pdfdrill route` read this scan as born-digital and send it to the "
            "text-layer lane instead of the one that can read it. Acquire the "
            "scan, then read it with `pdfdrill gemmaocr <pdf>` (METERED) or take "
            "its shape for free with `pdfdrill gemmaocr <pdf> --geometry-only`.")
    srcs = resolve_srcs(manifest, job_dir=job_dir)
    if not srcs:
        raise ValueError("no kept pages to assemble")
    missing = [str(s) for s in srcs if not s.exists()]
    if missing:
        raise FileNotFoundError(f"kept page images missing: {missing}")

    out_pdf = Path(out_pdf)
    # Lossless embed. img2pdf never re-encodes; it wraps the original streams.
    with open(out_pdf, "wb") as fh:
        fh.write(img2pdf.convert([str(s) for s in srcs]))

    if meta is None:
        meta = DocMeta.from_manifest(manifest, title=title)
    with pikepdf.open(out_pdf, allow_overwriting_input=True) as pdf:
        stamp(pdf, meta)
        pdf.save()

    manifest.pdf = out_pdf.name
    return out_pdf
