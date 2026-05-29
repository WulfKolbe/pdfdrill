"""DocumentContext — the carrier object for the pdfdrill state machine.

Holds all document state across the full drill-down lifecycle:
  - Input: question, URL/path, uploaded text
  - Discovery: pdfinfo, pdffonts, file size, page count
  - Extraction: pdftotext first page, pdfplumber chars
  - Analysis: the layer stack (L0..L4), templates, audit log
  - Output: projected markdown, answer

Serializable to JSON so it survives across tool calls.

State machine states:
  START → INSPECT_UPLOAD → FETCH_METADATA → CHECK_SIZE → DOWNLOAD →
  PDFINFO → PDFTEXT_FIRST → PLUMBER_EXTRACT → LAYER_BUILD → PROJECT → ANSWER
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# CharMeta — per-position metadata (runtime only, not serialized)
# ---------------------------------------------------------------------------

@dataclass
class CharMeta:
    font_name: str = ""
    font_class: str = "text"
    size: float = 0.0
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0
    page: int = 0
    line_idx: int = 0
    baseline: float = 0.0


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class PageMeta(BaseModel):
    width: float
    height: float


class DefaultStyle(BaseModel):
    font: Optional[str] = None
    size: Optional[float] = None
    color: Optional[str] = None


class DocMeta(BaseModel):
    source: str
    schema_version: str = "0.3.0"
    pages: list[PageMeta] = Field(default_factory=list)
    language: Optional[str] = None
    default_style: Optional[DefaultStyle] = None


class TemplateProperties(BaseModel):
    font: Optional[str] = None
    size: Optional[float] = None
    color: Optional[str] = None
    model_config = {"extra": "allow"}


class Template(BaseModel):
    id: str
    properties: TemplateProperties


class Span(BaseModel):
    start: int
    end: int
    kind: str = ""
    template: Optional[str] = None
    props: Optional[dict[str, Any]] = None


class AuditEntry(BaseModel):
    ts: float
    node: str
    detail: str = ""
    cost_ms: float = 0.0


# ---------------------------------------------------------------------------
# DocumentContext
# ---------------------------------------------------------------------------

class DocumentContext(BaseModel):
    """The carrier object. Holds everything about one document drill-down."""

    # -- Input --
    question: str = ""
    url: Optional[str] = None
    local_path: Optional[str] = None
    uploaded_text: Optional[str] = None

    # -- State machine --
    state: str = "START"
    next_state: Optional[str] = None

    # -- Discovery (filled by Poppler tools) --
    file_size: Optional[int] = None
    page_count: Optional[int] = None
    pdfinfo: Optional[dict[str, str]] = None
    pdffonts: Optional[list[dict[str, str]]] = None
    has_text_layer: Optional[bool] = None
    has_math_fonts: Optional[bool] = None
    first_page_text: Optional[str] = None
    abstract: Optional[str] = None
    toc: Optional[list[str]] = None
    page_range: Optional[list[int]] = None

    # -- Core document model --
    meta: DocMeta = Field(default_factory=lambda: DocMeta(source=""))
    graphemes: str = ""
    templates: list[Template] = Field(default_factory=list)

    # Layer stack
    L1: list[Span] = Field(default_factory=list)
    L2: list[Span] = Field(default_factory=list)
    L3: list[Span] = Field(default_factory=list)
    L4: list[Span] = Field(default_factory=list)

    # -- Output --
    answer: Optional[str] = None
    projected_md: Optional[str] = None

    # -- Audit --
    audit: list[AuditEntry] = Field(default_factory=list)

    model_config = {"extra": "allow"}

    # -- Runtime-only (not serialized) --
    _char_meta: list[CharMeta] = []

    @property
    def char_meta(self) -> list[CharMeta]:
        return self._char_meta

    @char_meta.setter
    def char_meta(self, value: list[CharMeta]):
        self._char_meta = value

    def log(self, node: str, detail: str = "", cost_ms: float = 0.0):
        self.audit.append(AuditEntry(
            ts=time.time(), node=node, detail=detail, cost_ms=cost_ms,
        ))

    def spans_by_kind(self, layer: str, kind: str) -> list[Span]:
        return [s for s in getattr(self, layer, []) if s.kind == kind]

    def to_json(self) -> str:
        return self.model_dump_json(exclude_none=True, indent=2)

    @classmethod
    def from_json(cls, data: str) -> DocumentContext:
        return cls.model_validate_json(data)


# ---------------------------------------------------------------------------
# State constants
# ---------------------------------------------------------------------------

STATE_START = "START"
STATE_INSPECT_UPLOAD = "INSPECT_UPLOAD"
STATE_FETCH_METADATA = "FETCH_METADATA"
STATE_CHECK_SIZE = "CHECK_SIZE"
STATE_DOWNLOAD = "DOWNLOAD"
STATE_PDFINFO = "PDFINFO"
STATE_PDFTEXT_FIRST = "PDFTEXT_FIRST"
STATE_PLUMBER_EXTRACT = "PLUMBER_EXTRACT"
STATE_LAYER_BUILD = "LAYER_BUILD"
STATE_PROJECT = "PROJECT"
STATE_ANSWER = "ANSWER"

# ---------------------------------------------------------------------------
# Span kind constants
# ---------------------------------------------------------------------------

# L1
STYLE_RUN = "style_run"

# L2
PARAGRAPH = "paragraph"
HEADING = "heading"

# L3
TOKEN = "token"
HYPHEN = "hyphen"
CITATION = "citation"
EQUATION_NUMBER = "eq_number"
EQUATION_REF = "eq_ref"
STRUCTURAL_REF = "struct_ref"

# L4
MATH_INLINE = "math_inline"
MATH_DISPLAY = "math_display"
EMPHASIS_BOLD = "bold"
EMPHASIS_ITALIC = "italic"
SENTENCE = "sentence"
FLAG = "flag"
