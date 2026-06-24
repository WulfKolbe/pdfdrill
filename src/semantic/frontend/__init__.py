"""semantic.frontend — a granular object×format detection layer feeding the
semantic graph.

Axes (each its own module, by design — the granularity is what lets a LEAN
grammar later generate the per-cell parser and its test corpus):
  * objects/  — one OBJECT module per data object (schema + conclusion)
  * formats/  — one FORMAT module per input surface
  * cells/    — one CELL per (object, format): the detector / LEAN-grammar slot

Driver:
  detect(raw, fmt, kind) -> [DetectedObject]
  to_bibtex(detected)    -> a BibTeX-like record (frontmatter's conclusion)
"""
from __future__ import annotations

from . import contract
from .contract import DetectedObject, Surface

# import side-effects register the modules into the registries
from .formats import latex as _latex          # noqa: F401
from .formats import text as _text            # noqa: F401
from .objects import frontmatter as _fm       # noqa: F401
from .cells import frontmatter_latex as _fml  # noqa: F401
from .cells import frontmatter_letter as _fmt  # noqa: F401


def detect(raw: str, fmt: str, kind: str) -> list[DetectedObject]:
    """Run the (kind, fmt) cell over the format's normalised surface."""
    fmod = contract.get_format(fmt)
    if fmod is None:
        raise ValueError(f"unknown format {fmt!r}; have {sorted(contract.FORMATS)}")
    cell = contract.get_cell(kind, fmt)
    if cell is None:
        raise ValueError(f"no cell for object {kind!r} in format {fmt!r}; "
                         f"have {sorted(contract.CELLS)}")
    return cell.detect(fmod.surface(raw))


def to_bibtex(obj: DetectedObject) -> dict:
    """The object's conclusion — for frontmatter, a BibTeX-like record."""
    omod = contract.get_object(obj.kind)
    if omod is None:
        raise ValueError(f"no object module for {obj.kind!r}")
    return omod.conclude(obj)


__all__ = ["detect", "to_bibtex", "DetectedObject", "Surface", "contract"]
