"""The canonical ingestion artifact: ``ingest.json``.

Deliberately NOT named ``manifest.json`` — that name is already taken by
pdfdrill's deep-zoom pyramid viewer (``<doc>.drill/viewer/manifest.json``).

Every ingestion producer appends :class:`Page` entries; every processing stage
is a pure transform over ``pages``. Removed pages are never deleted — they keep
a ``removed_*`` status so the downstream pdfdrill sidecar can still account for
them (the stage-III "pdfdrill must know removed pages" requirement).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

# Page.status values.
PENDING = "pending"
KEPT = "kept"
REMOVED_BLANK = "removed_blank"
REMOVED_USER = "removed_user"
_KEEP_STATES = {PENDING, KEPT}


@dataclass
class Page:
    """One physical page image and everything ingestion/processing learned about it."""

    seq: int
    src: str  # path relative to the job dir (or absolute for path-reference mode)
    origin: dict[str, Any] = field(default_factory=dict)  # {"kind": "adf"|"find"|"upload"|"camera", ...}
    sha256: str | None = None
    mtime: float | None = None
    width: int | None = None
    height: int | None = None
    dpi: tuple[int, int] | None = None
    skew_deg: float | None = None
    skew_conf: float | None = None
    skew_applied: bool = False
    blank_mean: float | None = None  # grayscale mean of the shaved page, 0..1
    status: str = PENDING
    extra: dict[str, Any] = field(default_factory=dict)  # room for later tools (qr, cropmarks, ...)

    @property
    def kept(self) -> bool:
        return self.status in _KEEP_STATES


@dataclass
class Manifest:
    job: str
    created: str  # ISO-8601; passed in by the caller (no wall-clock reads in this module)
    lang: str = "de-DE"
    pdf: str | None = None
    source_root: str | None = None
    schema: int = SCHEMA_VERSION
    # Set when an OCR text layer was grafted, e.g.
    # {"applied": True, "engine": "tesseract", "lang": "deu"}.
    # This is load-bearing downstream, not decoration: a text layer makes
    # pdfdrill's `route` classify a SCAN as born-digital (verified), so the
    # provenance must travel with the PDF to keep that decision honest.
    ocr: dict[str, Any] | None = None
    pages: list[Page] = field(default_factory=list)

    # ---- construction / ordering -------------------------------------------------
    def add(self, page: Page) -> Page:
        page.seq = len(self.pages) + 1
        self.pages.append(page)
        return page

    def kept_pages(self) -> list[Page]:
        return [p for p in self.pages if p.kept]

    # ---- persistence -------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # tuples -> lists for stable JSON; dataclass asdict already handles nesting
        for pg in d["pages"]:
            if pg.get("dpi") is not None:
                pg["dpi"] = list(pg["dpi"])
        return d

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
        return path

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Manifest":
        pages = []
        for pg in d.get("pages", []):
            pg = dict(pg)
            if pg.get("dpi") is not None:
                pg["dpi"] = tuple(pg["dpi"])
            pages.append(Page(**pg))
        known = {f for f in cls.__dataclass_fields__ if f != "pages"}
        head = {k: v for k, v in d.items() if k in known}
        return cls(pages=pages, **head)

    @classmethod
    def load(cls, path: str | Path) -> "Manifest":
        return cls.from_dict(json.loads(Path(path).read_text()))


def merge_into_sidecar(manifest: Manifest, sidecar: dict[str, Any]) -> dict[str, Any]:
    """Merge ingestion page-provenance INTO a pdfdrill ``.drill.json`` dict.

    Additive by construction: writes under a single ``scandrill`` key and never
    touches existing pdfdrill keys (facts/evidence/pdfinfo/layers/...). This is
    the stage-III contract — provenance *merges in*, a later ``model``/``ocr``
    run must not clobber it.
    """
    block = {
        "job": manifest.job,
        "created": manifest.created,
        "lang": manifest.lang,
        # Tells a downstream reader that a text layer, if present, is OCR — not
        # evidence of a born-digital document.
        "ocr": manifest.ocr,
        "pages": [
            {
                "seq": p.seq,
                "src": p.src,
                "origin": p.origin,
                "sha256": p.sha256,
                "skew_deg": p.skew_deg,
                "blank_mean": p.blank_mean,
                "status": p.status,
            }
            for p in manifest.pages
        ],
    }
    out = dict(sidecar)
    out["scandrill"] = block  # single namespaced key; no existing key is overwritten
    return out
