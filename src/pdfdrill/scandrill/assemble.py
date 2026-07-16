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
from .ocr import graft_text_layer, tesseract_lang


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
    """Write the lossless PDF for all kept pages, stamp metadata, optionally OCR.

    The three stages are deliberately separate and only the first touches pixels
    (and even that one doesn't re-encode them):

    1. ``img2pdf`` — wraps the original streams. JPEG → ``/DCTDecode`` verbatim,
       PNG → ``/FlateDecode`` with identical pixels. Never re-encodes.
    2. ``meta.stamp`` — /Lang, XMP + DocInfo, page labels. Metadata only.
    3. ``ocr.graft_text_layer`` (opt-in) — overlays an invisible text-only layer;
       the image streams stay byte-identical.

    Returns the output path. Raises ValueError if there are no kept pages.
    """
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

    if ocr:
        lang = ocr_lang or tesseract_lang(meta.lang)
        n = graft_text_layer(out_pdf, srcs, lang=lang)
        # Record it: a text layer makes pdfdrill's `route` read a SCAN as
        # born-digital and pick pdfminer over the vision lane (verified). The
        # provenance is what keeps that decision correctable downstream.
        manifest.ocr = {"applied": True, "engine": "tesseract",
                        "lang": lang, "pages": n}

    manifest.pdf = out_pdf.name
    return out_pdf
