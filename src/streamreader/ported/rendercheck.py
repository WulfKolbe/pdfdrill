# Moved into pdfdrill from pdf2mmd2 (github.com/PDFDRILL/pdf2mmd2) at 5190249,
# T-0045. pdfdrill holds the reader from here on; pdf2mmd2 does not follow
# pdfdrill's later changes. This line is the ONLY difference from the source
# file at that commit — strip it and the bytes match (tests/test_streamreader_provenance.py).
"""Does a reconstructed formula typeset to the same pixels as its source?

Derived from psred (fixtures/math/build.py `compile_formula`, convert.py
`render`, at origin/master 344c27d). psred renders through ps2write; here
both PDFs go straight to Ghostscript's grey raster, which compares the same
thing without the detour.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

PRE = ("\\documentclass{article}\\pagestyle{empty}\\begin{document}\n"
       "\\[ %s \\]\n\\end{document}\n")


def compile_formula(tex: str, stem: str, outdir) -> bool:
    """Typeset `tex` as a display with psred's fixture preamble."""
    outdir = Path(outdir)
    (outdir / f"{stem}.tex").write_text(PRE % tex)
    r = subprocess.run(["pdflatex", "-interaction=batchmode",
                        "-halt-on-error", f"{stem}.tex"],
                       cwd=outdir, capture_output=True)
    for ext in (".aux", ".log"):
        (outdir / f"{stem}{ext}").unlink(missing_ok=True)
    return r.returncode == 0


def render(pdf, dpi: int = 150) -> bytes:
    """Page 1 as a raw grey raster, no anti-aliasing."""
    r = subprocess.run(
        ["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=pgmraw",
         f"-r{dpi}", "-dTextAlphaBits=1", "-dGraphicsAlphaBits=1",
         "-dFirstPage=1", "-dLastPage=1", "-sOutputFile=-", str(pdf)],
        capture_output=True)
    if r.returncode or not r.stdout:
        raise RuntimeError(r.stderr.decode(errors="replace")[-800:])
    return r.stdout


def identical(pdf_a, pdf_b, dpi: int = 150) -> bool:
    return render(pdf_a, dpi) == render(pdf_b, dpi)
