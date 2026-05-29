"""Poppler tool nodes — lightweight PDF inspection without full extraction.

These nodes call Poppler command-line tools (pdfinfo, pdffonts, pdftotext,
pdfimages) via subprocess. They fill discovery fields on DocumentContext
so the state machine can decide what to do next.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from ..context import DocumentContext
from ..engine import Node


class PdfinfoNode(Node):
    """Run pdfinfo on the local PDF file. Fills page_count, pdfinfo, file_size."""
    name = "pdfinfo"

    def should_run(self, ctx: DocumentContext) -> bool:
        return ctx.local_path is not None and Path(ctx.local_path).exists()

    def run(self, ctx: DocumentContext) -> DocumentContext:
        path = Path(ctx.local_path)
        ctx.file_size = path.stat().st_size

        try:
            out = subprocess.run(
                ["pdfinfo", str(path)],
                capture_output=True, text=True, timeout=30,
            )
            info = {}
            for line in out.stdout.splitlines():
                if ":" in line:
                    key, _, val = line.partition(":")
                    info[key.strip()] = val.strip()

            ctx.pdfinfo = info
            ctx.page_count = int(info.get("Pages", "0"))
            ctx.meta.source = path.name

            ctx.log("pdfinfo", f"pages={ctx.page_count} size={ctx.file_size}")
        except Exception as e:
            ctx.log("pdfinfo", f"error: {e}")

        return ctx


class PdffontsNode(Node):
    """Run pdffonts to detect math fonts and text layer presence."""
    name = "pdffonts"

    def should_run(self, ctx: DocumentContext) -> bool:
        return ctx.local_path is not None and Path(ctx.local_path).exists()

    def run(self, ctx: DocumentContext) -> DocumentContext:
        path = Path(ctx.local_path)
        try:
            out = subprocess.run(
                ["pdffonts", str(path)],
                capture_output=True, text=True, timeout=60,
            )
            fonts = []
            lines = out.stdout.strip().splitlines()
            if len(lines) >= 2:
                for line in lines[2:]:  # skip header
                    parts = line.split()
                    if len(parts) >= 3:
                        fonts.append({
                            "name": parts[0],
                            "type": parts[1] if len(parts) > 1 else "",
                            "encoding": parts[2] if len(parts) > 2 else "",
                        })

            ctx.pdffonts = fonts
            ctx.has_text_layer = len(fonts) > 0

            math_keywords = ["math", "symbol", "msbm", "eufm", "cmsy", "cmmi", "cmex", "mt2"]
            ctx.has_math_fonts = any(
                any(kw in f["name"].lower() for kw in math_keywords)
                for f in fonts
            )

            ctx.log("pdffonts", f"fonts={len(fonts)} math={ctx.has_math_fonts}")
        except Exception as e:
            ctx.log("pdffonts", f"error: {e}")

        return ctx


class PdftextFirstNode(Node):
    """Run pdftotext on first page (and optionally last 2 pages) to get abstract/TOC."""
    name = "pdftext_first"

    def should_run(self, ctx: DocumentContext) -> bool:
        return ctx.local_path is not None and Path(ctx.local_path).exists()

    def run(self, ctx: DocumentContext) -> DocumentContext:
        path = Path(ctx.local_path)
        try:
            out = subprocess.run(
                ["pdftotext", "-f", "1", "-l", "1", "-layout", str(path), "-"],
                capture_output=True, text=True, timeout=30,
            )
            ctx.first_page_text = out.stdout

            text = out.stdout
            ctx.abstract = _extract_abstract(text)
            ctx.toc = _extract_toc(text)

            ctx.log("pdftext_first", f"chars={len(text)} abstract={'yes' if ctx.abstract else 'no'}")
        except Exception as e:
            ctx.log("pdftext_first", f"error: {e}")

        return ctx


class InspectUploadNode(Node):
    """Check if the user uploaded text that can answer the question directly."""
    name = "inspect_upload"

    def should_run(self, ctx: DocumentContext) -> bool:
        return ctx.uploaded_text is not None and len(ctx.uploaded_text) > 0

    def run(self, ctx: DocumentContext) -> DocumentContext:
        text = ctx.uploaded_text or ""
        ctx.log("inspect_upload", f"uploaded_text={len(text)} chars")

        # Extract abstract from uploaded text if available
        abstract = _extract_abstract(text)
        if abstract:
            ctx.abstract = abstract

        return ctx


class CheckSizeNode(Node):
    """Check file size and set page_range heuristic."""
    name = "check_size"

    def should_run(self, ctx: DocumentContext) -> bool:
        return ctx.local_path is not None

    def run(self, ctx: DocumentContext) -> DocumentContext:
        path = Path(ctx.local_path)
        if path.exists():
            ctx.file_size = path.stat().st_size
        ctx.log("check_size", f"size={ctx.file_size}")
        return ctx


class PageRangeNode(Node):
    """Determine which pages to process based on question and TOC."""
    name = "page_range"

    def should_run(self, ctx: DocumentContext) -> bool:
        return ctx.page_count is not None and ctx.page_count > 0

    def run(self, ctx: DocumentContext) -> DocumentContext:
        if ctx.page_range is not None:
            ctx.log("page_range", f"user-specified: {ctx.page_range}")
            return ctx

        # Default: all pages
        ctx.page_range = list(range(1, ctx.page_count + 1))
        ctx.log("page_range", f"all {ctx.page_count} pages")
        return ctx


class PlumberCharsNode(Node):
    """Run pdfplumber to extract char-level data (generates .chars.json)."""
    name = "plumber_chars"

    def should_run(self, ctx: DocumentContext) -> bool:
        return ctx.local_path is not None and Path(ctx.local_path).exists()

    def run(self, ctx: DocumentContext) -> DocumentContext:
        import json
        import pdfplumber

        path = Path(ctx.local_path)
        pages_data = []

        with pdfplumber.open(path) as pdf:
            page_range = ctx.page_range or list(range(1, len(pdf.pages) + 1))
            for page_num in page_range:
                if page_num < 1 or page_num > len(pdf.pages):
                    continue
                page = pdf.pages[page_num - 1]
                pages_data.append({
                    "page_number": page_num,
                    "width": float(page.width),
                    "height": float(page.height),
                    "chars": page.chars,
                })

        # Save chars.json alongside the PDF
        chars_path = path.with_suffix(".chars.json")
        with open(chars_path, "w", encoding="utf-8") as f:
            json.dump(
                {"source": path.name, "total_pages": len(pages_data), "pages": pages_data},
                f, default=_json_default, ensure_ascii=False,
            )

        ctx.log("plumber_chars", f"pages={len(pages_data)} → {chars_path.name}")
        return ctx


def _json_default(obj):
    from decimal import Decimal
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Not serializable: {type(obj)}")


# ---------------------------------------------------------------------------
# Text extraction helpers
# ---------------------------------------------------------------------------

def _extract_abstract(text: str) -> str | None:
    """Try to find an abstract section in the text."""
    # Look for "Abstract" header followed by text
    m = re.search(r"(?i)abstract\s*\n(.*?)(?:\n\s*\n|\n\d+\s|\nIntroduction|\n1\s)",
                  text, re.DOTALL)
    if m:
        abstract = m.group(1).strip()
        if len(abstract) > 30:
            return abstract
    return None


def _extract_toc(text: str) -> list[str] | None:
    """Try to find table of contents entries."""
    # Look for numbered section patterns
    toc_entries = re.findall(r"^(\d+(?:\.\d+)*\s+[A-Z].*?)$", text, re.MULTILINE)
    if len(toc_entries) >= 3:
        return toc_entries[:20]
    return None
