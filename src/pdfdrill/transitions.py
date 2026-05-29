"""Declarative transition table for the pdfdrill state machine.

State graph:
  START
    ├─ has uploaded text → INSPECT_UPLOAD
    └─ has local_path   → PDFINFO
  INSPECT_UPLOAD
    ├─ abstract answers question → ANSWER
    └─ has local_path            → PDFINFO
  PDFINFO
    └─ always → PDFFONTS
  PDFFONTS
    └─ always → PDFTEXT_FIRST
  PDFTEXT_FIRST
    ├─ abstract answers question (no math needed) → ANSWER
    └─ always → PAGE_RANGE
  PAGE_RANGE
    └─ always → PLUMBER_CHARS
  PLUMBER_CHARS
    └─ always → PLUMBER_EXTRACT (ingest chars to layers)
  PLUMBER_EXTRACT
    └─ always → LAYER_BUILD
  LAYER_BUILD
    └─ always → PROJECT
  PROJECT
    └─ always → ANSWER
"""

from __future__ import annotations

from pathlib import Path

from .context import (
    STATE_ANSWER, STATE_CHECK_SIZE, STATE_DOWNLOAD, STATE_INSPECT_UPLOAD,
    STATE_PDFINFO, STATE_PDFTEXT_FIRST, STATE_PLUMBER_EXTRACT,
    STATE_LAYER_BUILD, STATE_PROJECT, STATE_START,
    DocumentContext,
)
from .engine import Transition, always

from .nodes.poppler import (
    CheckSizeNode, InspectUploadNode, PageRangeNode,
    PdfinfoNode, PdffontsNode, PdftextFirstNode, PlumberCharsNode,
)


# ---------------------------------------------------------------------------
# Guard functions
# ---------------------------------------------------------------------------

def _has_upload(ctx: DocumentContext) -> bool:
    return ctx.uploaded_text is not None and len(ctx.uploaded_text or "") > 50

def _has_local_path(ctx: DocumentContext) -> bool:
    return ctx.local_path is not None and Path(ctx.local_path).exists()

def _has_chars_json(ctx: DocumentContext) -> bool:
    if ctx.local_path:
        chars = Path(ctx.local_path).with_suffix(".chars.json")
        return chars.exists()
    return False

def _has_graphemes(ctx: DocumentContext) -> bool:
    return len(ctx.graphemes) > 0


# ---------------------------------------------------------------------------
# Layer building: a composite node that runs the inner pipeline
# ---------------------------------------------------------------------------

class LayerBuildNode:
    """Runs the inner analysis pipeline (tokenizer, emphasis, refs, math, etc.)."""
    name = "layer_build"

    def should_run(self, ctx: DocumentContext) -> bool:
        return len(ctx.graphemes) > 0

    def run(self, ctx: DocumentContext) -> DocumentContext:
        from .nodes.lines_paragraphs import LinesParagraphsNode
        from .nodes.tokenizer import TokenizerNode
        from .nodes.emphasis_detector import EmphasisDetectorNode
        from .nodes.reference_detector import ReferenceDetectorNode
        from .nodes.math_detector import MathDetectorNode
        from .nodes.math_assembler import MathAssemblerNode
        from .nodes.flagger import FlaggerNode
        from .nodes.stub_nlp import StubNlpNode

        inner_nodes = [
            LinesParagraphsNode(),
            TokenizerNode(),
            EmphasisDetectorNode(),
            ReferenceDetectorNode(),
            MathDetectorNode(),
            MathAssemblerNode(),
            FlaggerNode(),
            StubNlpNode(),
        ]

        for node in inner_nodes:
            if node.should_run(ctx):
                ctx = node.run(ctx)
                ctx.log(node.name, cost_ms=0)

        return ctx


class IngestCharsNode:
    """Ingest .chars.json into the grapheme string and L1."""
    name = "plumber_extract"

    def should_run(self, ctx: DocumentContext) -> bool:
        return _has_chars_json(ctx) or _has_local_path(ctx)

    def run(self, ctx: DocumentContext) -> DocumentContext:
        chars_path = None
        if ctx.local_path:
            chars_path = Path(ctx.local_path).with_suffix(".chars.json")
        if not chars_path or not chars_path.exists():
            ctx.log("plumber_extract", "no .chars.json found")
            return ctx

        from .nodes.ingest_pdfplumber import IngestPdfplumberNode
        node = IngestPdfplumberNode(chars_path)
        ctx = node.run(ctx)
        return ctx


class ProjectNode:
    """Project the document model to Markdown."""
    name = "project"

    def should_run(self, ctx: DocumentContext) -> bool:
        return len(ctx.graphemes) > 0

    def run(self, ctx: DocumentContext) -> DocumentContext:
        from .projectors.markdown import MarkdownProjector
        ctx.projected_md = MarkdownProjector().project(ctx)
        ctx.log("project", f"md_chars={len(ctx.projected_md)}")
        return ctx


class AnswerNode:
    """Terminal node — marks drill-down as complete."""
    name = "answer"

    def should_run(self, ctx: DocumentContext) -> bool:
        return True

    def run(self, ctx: DocumentContext) -> DocumentContext:
        ctx.log("answer", "drill-down complete")
        return ctx


# ---------------------------------------------------------------------------
# The transition table
# ---------------------------------------------------------------------------

_pdfinfo = PdfinfoNode()
_pdffonts = PdffontsNode()
_pdftext = PdftextFirstNode()
_inspect = InspectUploadNode()
_check_size = CheckSizeNode()
_page_range = PageRangeNode()
_plumber_chars = PlumberCharsNode()
_ingest = IngestCharsNode()
_layer_build = LayerBuildNode()
_project = ProjectNode()
_answer = AnswerNode()


TRANSITIONS: list[Transition] = [
    # START
    Transition("START", "INSPECT_UPLOAD", _inspect,
               guard=_has_upload, label="check uploaded text"),
    Transition("START", "PDFINFO", _pdfinfo,
               guard=_has_local_path, label="local PDF → pdfinfo"),

    # INSPECT_UPLOAD → either answer or continue with PDF
    Transition("INSPECT_UPLOAD", "PDFINFO", _pdfinfo,
               guard=_has_local_path, label="uploaded text insufficient, use PDF"),
    Transition("INSPECT_UPLOAD", "ANSWER", _answer,
               guard=always, label="no PDF available, use uploaded text"),

    # PDFINFO → PDFFONTS
    Transition("PDFINFO", "PDFFONTS", _pdffonts,
               guard=always, label="inspect fonts"),

    # PDFFONTS → PDFTEXT_FIRST
    Transition("PDFFONTS", "PDFTEXT_FIRST", _pdftext,
               guard=always, label="extract first page text"),

    # PDFTEXT_FIRST → PAGE_RANGE
    Transition("PDFTEXT_FIRST", "PAGE_RANGE", _page_range,
               guard=always, label="determine page range"),

    # PAGE_RANGE → PLUMBER_CHARS (extract pdfplumber data)
    Transition("PAGE_RANGE", "PLUMBER_CHARS", _plumber_chars,
               guard=always, label="extract char data via pdfplumber"),

    # PLUMBER_CHARS → PLUMBER_EXTRACT (ingest to graphemes + L1)
    Transition("PLUMBER_CHARS", "PLUMBER_EXTRACT", _ingest,
               guard=always, label="ingest chars to layers"),

    # PLUMBER_EXTRACT → LAYER_BUILD (run analysis pipeline)
    Transition("PLUMBER_EXTRACT", "LAYER_BUILD", _layer_build,
               guard=_has_graphemes, label="build analysis layers"),

    # LAYER_BUILD → PROJECT
    Transition("LAYER_BUILD", "PROJECT", _project,
               guard=_has_graphemes, label="project to markdown"),

    # PROJECT → ANSWER
    Transition("PROJECT", "ANSWER", _answer,
               guard=always, label="done"),
]
