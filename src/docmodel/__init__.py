"""DocObject converter for MathPix lines.json.

A modular pipeline that turns MathPix OCR `lines.json` into a Document of
typed DocObjects, with realizations into anchor-based Streams.
"""
from .core import (
    Anchor, Stream, Range, Realization, DocObject, Alignment, Document,
)
from .base_module import BaseModule, ModuleConfig

__all__ = [
    "Anchor", "Stream", "Range", "Realization", "DocObject",
    "Alignment", "Document", "BaseModule", "ModuleConfig",
]
