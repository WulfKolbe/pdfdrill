"""Document metadata for the assembled PDF.

A PDF carries metadata in two places that must AGREE or readers disagree with
each other: the legacy **DocInfo** dictionary (``/Title``, ``/Author``, …) and the
**XMP** packet (``dc:title``, ``dc:creator``, …), which is what modern tooling and
PDF/A validators read. :func:`stamp` writes both from one :class:`DocMeta`.

Language lives in neither: it is the catalog ``/Lang``, read by OCR and
accessibility tooling.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pikepdf

from . import __version__

DEFAULT_PRODUCER = f"SCANDRILL {__version__}"


@dataclass
class DocMeta:
    """What goes on the assembled document. All fields optional except lang."""

    title: str | None = None
    author: str | None = None
    subject: str | None = None
    keywords: str | None = None
    creator: str | None = None          # the producing application
    producer: str = DEFAULT_PRODUCER
    created: str | None = None          # ISO-8601; from the job, not wall clock
    lang: str = "de-DE"

    # page labels: /PageLabels number tree
    label_style: str | None = "D"       # D=decimal, R/r=roman, A/a=letters, None=none
    label_start: int = 1
    label_prefix: str | None = None

    @classmethod
    def from_manifest(cls, manifest, **overrides) -> "DocMeta":
        """Derive metadata from the job — the PDF is a projection of the manifest."""
        base = dict(
            title=manifest.job,
            created=manifest.created,
            lang=manifest.lang,
        )
        base.update({k: v for k, v in overrides.items() if v is not None})
        return cls(**base)


def _pdf_date(iso: str | None) -> str | None:
    """ISO-8601 → PDF date string D:YYYYMMDDHHmmSS±HH'mm'."""
    if not iso:
        return None
    from datetime import datetime

    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    s = dt.strftime("D:%Y%m%d%H%M%S")
    off = dt.utcoffset()
    if off is None:
        return s
    total = int(off.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{s}{sign}{total // 3600:02d}'{(total % 3600) // 60:02d}'"


def _page_labels(meta: DocMeta) -> pikepdf.Dictionary | None:
    if meta.label_style is None and meta.label_prefix is None:
        return None
    d = {}
    if meta.label_style:
        d["S"] = pikepdf.Name(f"/{meta.label_style}")
    if meta.label_prefix:
        d["P"] = pikepdf.String(meta.label_prefix)
    if meta.label_start != 1:
        d["St"] = meta.label_start
    else:
        d["St"] = 1
    return pikepdf.Dictionary(Nums=pikepdf.Array([0, pikepdf.Dictionary(**d)]))


def stamp(pdf: pikepdf.Pdf, meta: DocMeta) -> None:
    """Write /Lang, XMP, DocInfo and page labels onto an open Pdf.

    Touches no page content and no image stream — metadata only.
    """
    # Catalog /Lang: OCR + accessibility read this; it is not part of DocInfo/XMP.
    pdf.Root.Lang = pikepdf.String(meta.lang)

    # XMP. set_pikepdf_as_editor=False: otherwise pikepdf stamps ITSELF as the
    # editing tool and overwrites our producer (a known gotcha).
    with pdf.open_metadata(set_pikepdf_as_editor=False) as xmp:
        if meta.title:
            xmp["dc:title"] = meta.title
        if meta.author:
            xmp["dc:creator"] = [meta.author]      # dc:creator is a LIST (seq)
        if meta.subject:
            xmp["dc:description"] = meta.subject
        if meta.keywords:
            xmp["pdf:Keywords"] = meta.keywords
        if meta.creator:
            xmp["xmp:CreatorTool"] = meta.creator
        xmp["pdf:Producer"] = meta.producer
        if meta.created:
            xmp["xmp:CreateDate"] = meta.created

    # DocInfo — must mirror the XMP above or readers disagree.
    di = pdf.docinfo
    for key, val in (
        ("/Title", meta.title),
        ("/Author", meta.author),
        ("/Subject", meta.subject),
        ("/Keywords", meta.keywords),
        ("/Creator", meta.creator),
        ("/Producer", meta.producer),
        ("/CreationDate", _pdf_date(meta.created)),
    ):
        if val:
            di[key] = pikepdf.String(val)

    labels = _page_labels(meta)
    if labels is not None:
        pdf.Root.PageLabels = labels
