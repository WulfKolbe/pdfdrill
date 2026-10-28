# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Whole-page JPEG via Ghostscript, in MathPix's 250-dpi pixel space."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


class RenderError(RuntimeError):
    pass


def render_page(pdf: Path, page: int, out_jpg: Path, dpi: int = 250) -> Path:
    out_jpg = Path(out_jpg)
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    # Ghostscript reads `%` in -o as a format specifier, so it writes to a
    # fixed relative name inside a temp dir and the result is moved.
    with tempfile.TemporaryDirectory(dir=str(out_jpg.parent)) as td:
        proc = subprocess.run(
            ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER",
             "-sDEVICE=jpeg", "-dJPEGQ=90", f"-r{dpi}",
             f"-dFirstPage={page}", f"-dLastPage={page}",
             "-o", "page.jpg", "-f", str(Path(pdf).resolve())],
            cwd=td, capture_output=True)
        tmp = Path(td) / "page.jpg"
        if proc.returncode != 0 or not tmp.exists():
            msg = proc.stderr.decode("utf-8", "replace").strip()
            raise RenderError(f"gs failed on {Path(pdf).name} p{page}: {msg}")
        os.replace(tmp, out_jpg)
    return out_jpg
