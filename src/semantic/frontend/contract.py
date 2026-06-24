"""The semantic-compiler contract — two orthogonal axes and the cell between.

This is deliberately granular: ONE module per OBJECT and ONE module per input
FORMAT, with the detector for an (object, format) pair living in its own CELL
module. That granularity is the point — each cell is the slot where a LEAN
grammar will later GENERATE the parser (LEAN expresses the recursive grammar via
a fixed-point/Y-combinator, so the parser is synthesised on the fly), and the
same grammar generates + validates the cell's test corpus. Until then each cell
carries a small bootstrap parser implementing the identical contract, so the
generated parser supersedes it without changing any caller.

Three registries:
  OBJECTS[kind]            -> ObjectModule   (schema + conclusion; format-agnostic)
  FORMATS[fmt]             -> FormatModule   (raw -> normalised Surface)
  CELLS[(kind, fmt)]       -> CellModule     (Surface -> [DetectedObject])

The driver: detect(raw, fmt, kind) = CELLS[(kind,fmt)].detect(FORMATS[fmt].surface(raw)).
A conclusion (e.g. to_bibtex) is OBJECTS[kind].conclude(detected_object).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


# --------------------------------------------------------------------------- #
# The uniform detection result — every cell, for every object, returns this.
# --------------------------------------------------------------------------- #
@dataclass
class DetectedObject:
    kind: str                              # "frontmatter", "equation", …
    format: str                            # "latex", "text", "mathpix", …
    fields: dict[str, Any]                 # an instance of the object's schema
    evidence: list[dict[str, Any]] = field(default_factory=list)  # spans backing fields
    confidence: float = 1.0


# --------------------------------------------------------------------------- #
# Surface — a format module's normalised view of raw input. Kept minimal and
# format-neutral so cells consume a common shape (lines + the raw text + a free
# meta bag a format can enrich, e.g. latex preamble vs body).
# --------------------------------------------------------------------------- #
@dataclass
class Surface:
    format: str
    raw: str
    lines: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# The three module kinds.
# --------------------------------------------------------------------------- #
class FormatModule(ABC):
    format: str = ""

    @abstractmethod
    def surface(self, raw: str) -> Surface: ...


class ObjectModule(ABC):
    kind: str = ""

    @abstractmethod
    def schema(self) -> dict[str, Any]:
        """The canonical field schema this object carries (documentation + the
        contract a cell must fill and a LEAN grammar must target)."""

    def conclude(self, obj: DetectedObject) -> Any:
        """The higher-layer inference this object licenses. Default: identity."""
        return obj.fields


class CellModule(ABC):
    kind: str = ""
    format: str = ""

    @abstractmethod
    def detect(self, surface: Surface) -> list[DetectedObject]: ...


# --------------------------------------------------------------------------- #
# Registries + registration decorators.
# --------------------------------------------------------------------------- #
FORMATS: dict[str, FormatModule] = {}
OBJECTS: dict[str, ObjectModule] = {}
CELLS: dict[tuple[str, str], CellModule] = {}


def register_format(m: FormatModule) -> FormatModule:
    FORMATS[m.format] = m
    return m


def register_object(m: ObjectModule) -> ObjectModule:
    OBJECTS[m.kind] = m
    return m


def register_cell(m: CellModule) -> CellModule:
    CELLS[(m.kind, m.format)] = m
    return m


def get_format(fmt: str) -> Optional[FormatModule]:
    return FORMATS.get(fmt)


def get_object(kind: str) -> Optional[ObjectModule]:
    return OBJECTS.get(kind)


def get_cell(kind: str, fmt: str) -> Optional[CellModule]:
    return CELLS.get((kind, fmt))
