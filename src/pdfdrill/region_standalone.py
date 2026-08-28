"""
284 — compile an image region's own LaTeX as its own document.

The report's image rows carry a region's LaTeX on the tiddler: 1,788 of 27,287
corpus rows have one (tikzpicture 762, tikzcd 658, lstlisting 323, math 40,
pgfplots and containers 62). Setting it INSIDE the report's longtable does not
work — a tikzcd uses `&` as its cell separator and so does the table, which
cost 239 errors and 239 glyphs into `nullfont` on 2208.01506 before the
`ampersand replacement` workaround, and a `\\matrix` node inside a tikzpicture
had no workaround at all.

Compiling it STANDALONE removes the problem rather than working around it: the
LaTeX is alone in its own document, `&` means what its own environment says it
means, and a failure costs one PNG instead of the report. `cmd_standalone` does
this for display equations already; this is the same shape for regions, minus
the `$\\displaystyle` wrapper that would be wrong for a picture.

Every kind is ATTEMPTED. A compile failure is a reportable outcome — 284 asks
for the count — and an allowlist would hide the cases nobody has looked at.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

#: Content that must NOT be wrapped in math mode.
_ENV_BODY = re.compile(
    r"\\begin\{(tikzpicture|tikzcd|tabular|tabularx|longtable|array\*|"
    r"lstlisting|verbatim|minipage|itemize|enumerate|axis|groupplot|"
    r"figure|center|comment|scope|pgfonlayer)\}")

PREAMBLE = (
    "\\documentclass[border=3pt]{standalone}\n"
    "\\usepackage{amsmath}\n\\usepackage{amssymb}\n"
    "\\usepackage{mathrsfs}\n\\usepackage{stmaryrd}\n"
    # Guarded exactly as the report preamble guards its fallback fonts (221):
    # an unguarded \usepackage for a package this machine lacks aborts the
    # compile and produces nothing, which is worse than the row it would set.
    "\\IfFileExists{tikz.sty}{\\usepackage{tikz}}{}\n"
    "\\IfFileExists{tikz-cd.sty}{\\usepackage{tikz-cd}}{}\n"
    "\\IfFileExists{pgfplots.sty}{\\usepackage{pgfplots}}{}\n"
    "\\IfFileExists{listings.sty}{\\usepackage{listings}}{}\n"
    "\\IfFileExists{array.sty}{\\usepackage{array}}{}\n"
)


def needs_math_wrapper(latex: str) -> bool:
    """True when the value is bare mathematics rather than an environment."""
    return not _ENV_BODY.search(latex or "")


def document(latex: str, unicode_decls: str = "") -> str:
    """The standalone document for one region."""
    body = (latex or "").strip()
    inner = ("$\\displaystyle %s$" % body) if needs_math_wrapper(body) else body
    return (PREAMBLE + unicode_decls + "\\begin{document}\n"
            + inner + "\n\\end{document}\n")


def render(ident: str, latex: str, out_dir: Path, dpi: int = 400,
           timeout: int = 90) -> tuple:
    """Compile one region to `<out_dir>/<ident>.png`.

    Returns `(png_path, None)` or `(None, reason)`. Ghostscript at >=400 dpi is
    the only rasterizer here, as everywhere else in pdfdrill.
    """
    if shutil.which("xelatex") is None:
        return None, "xelatex not installed"
    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{ident}.png"
    tex = out_dir / f"{ident}.tex"
    try:
        from .commands import rt_unicode_preamble as _uni
        decls = _uni(latex)          # 092: the same glyph rescue the report
    except Exception:                #      preamble carries, so a standalone
        decls = ""                   #      render never silently omits a glyph

    tex.write_text(document(latex, decls), encoding="utf-8")
    try:
        p = subprocess.run(["xelatex", "-interaction=nonstopmode",
                            "-halt-on-error", tex.name],
                           cwd=out_dir, capture_output=True, text=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        _clean(tex)
        return None, "timeout"
    pdf_out = tex.with_suffix(".pdf")
    if p.returncode != 0 or not pdf_out.is_file():
        err = ""
        log = tex.with_suffix(".log")
        if log.is_file():
            for line in log.read_text(errors="replace").splitlines():
                if line.startswith("!"):
                    err = line[:120]
                    break
        _clean(tex)
        return None, err or f"xelatex rc={p.returncode}"
    try:
        g = subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH",
                            "-sDEVICE=png16m", "-r%d" % dpi,
                            f"-sOutputFile={png.name}", pdf_out.name],
                           cwd=out_dir, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        _clean(tex, pdf_out)
        return None, "ghostscript timeout"
    _clean(tex, pdf_out)
    if g.returncode != 0 or not png.is_file():
        return None, "ghostscript rasterization failed"
    return png, None


def _clean(tex: Path, *extra: Path) -> None:
    for j in (tex, tex.with_suffix(".pdf"), tex.with_suffix(".log"),
              tex.with_suffix(".aux")) + tuple(extra):
        try:
            j.unlink(missing_ok=True)
        except Exception:
            pass
