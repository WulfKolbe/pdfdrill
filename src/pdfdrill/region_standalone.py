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

import os
import re
import shutil
import subprocess
from pathlib import Path

#: Content that must NOT be wrapped in math mode.
_ENV_BODY = re.compile(
    r"\\begin\{(tikzpicture|tikzcd|tabular|tabularx|longtable|array\*|"
    r"lstlisting|verbatim|minipage|itemize|enumerate|axis|groupplot|"
    r"figure|center|comment|scope|pgfonlayer)\}")

#: Appended whether or not the author's preamble already has them: a region may
#: use tikz-cd or listings even when the source document did not load them, and
#: a duplicate \usepackage of the same package is a no-op.
_GUARDED_PKGS = (
    "\\IfFileExists{tikz.sty}{\\usepackage{tikz}}{}\n"
    "\\IfFileExists{tikz-cd.sty}{\\usepackage{tikz-cd}}{}\n"
    "\\IfFileExists{pgfplots.sty}{\\usepackage{pgfplots}}{}\n"
    "\\IfFileExists{listings.sty}{\\usepackage{listings}}{}\n"
    "\\IfFileExists{graphicx.sty}{\\usepackage{graphicx}}{}\n"
    # 286 — \adjustbox is how several documents scale a figure inside a
    # tikzpicture node; without it every such region fails "Undefined control
    # sequence" no matter whose preamble is in force (2512.15098v4, 0 of 21).
    "\\IfFileExists{adjustbox.sty}{\\usepackage{adjustbox}}{}\n"
    "\\IfFileExists{xcolor.sty}{\\usepackage{xcolor}}{}\n"
)

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


def document(latex: str, unicode_decls: str = "",
             author_preamble: str = "", graphics_dir: "Path | None" = None) -> str:
    r"""The standalone document for one region.

    286 — the author's OWN preamble goes in when we have it. Without it, 69 of
    207 sampled regions failed on two things a generic preamble cannot supply:

        ! Undefined control sequence.                 (\<v|, \>  — their macros)
        ! LaTeX Error: File `figures/ch1/concept2' not found.

    `latex_source.standalone_preamble()` already extracts exactly what a cropped
    diagram needs from a document's preamble — packages minus the page-layout
    ones, tikz libraries, the full macro bodies, \definecolor, 	ikzset,
    \pgfplotsset — and `injectlatex` has already stored it on the model as
    `meta.latex_preamble.standalone`. The figure files are in the e-print
    beside it, so `\graphicspath` points there.

    The author's preamble REPLACES the generic head (it brings its own
    \documentclass) and our guarded packages are appended, because a region may
    use tikz-cd or listings whether or not the author's document did.
    """
    body = (latex or "").strip()
    inner = ("$\\displaystyle %s$" % body) if needs_math_wrapper(body) else body
    gpath = ""
    if graphics_dir is not None:
        d = str(graphics_dir).replace("\\", "/").rstrip("/")
        gpath = "\\graphicspath{{%s/}{%s/figures/}}\n" % (d, d)
    if author_preamble.strip():
        head = author_preamble.rstrip() + "\n" + _GUARDED_PKGS
    else:
        head = PREAMBLE
    return (head + gpath + unicode_decls + "\\begin{document}\n"
            + inner + "\n\\end{document}\n")


def render(ident: str, latex: str, out_dir: Path, dpi: int = 400,
           timeout: int = 90, author_preamble: str = "",
           graphics_dir: "Path | None" = None,
           texinputs: "Path | None" = None) -> tuple:
    r"""Compile one region, the author's preamble FIRST and the generic one as
    a fallback.

    286 measured why both are needed. Injecting the author's preamble alone
    took a 10-document sample from 66.7% to 52.2%: it rescued the documents
    whose regions use the author's macros and figure files (2004.05631, 3/25
    -> 21/25; 2210.06079, 16/25 -> 25/25) and destroyed three whose extracted
    preamble does not stand alone —

        2208.01506  ! LaTeX Error: Missing egin{document}.
        2602.23211  ! Illegal parameter number in definition of \hgnodea.

    Both are imperfections in the preamble EXTRACTION, not in the region, and
    both documents compile fine generically. So neither preamble is right for
    every document and the choice cannot be made in advance — it is made by
    trying, which costs a second compile only on rows that fail the first.
    """
    return _render_with_fallback(ident, latex, out_dir, dpi, timeout,
                                 author_preamble, graphics_dir, texinputs)


def _render_with_fallback(ident, latex, out_dir, dpi, timeout,
                          author_preamble, graphics_dir, texinputs) -> tuple:
    if author_preamble.strip():
        png, err = _render_once(ident, latex, out_dir, dpi, timeout,
                                author_preamble, graphics_dir, texinputs)
        if png is not None:
            return png, None
        png2, err2 = _render_once(ident, latex, out_dir, dpi, timeout,
                                  "", graphics_dir, texinputs)
        if png2 is not None:
            return png2, None
        # report the AUTHOR-preamble error: it is the more informative of the
        # two, and the generic retry failing as well means the region itself
        # is the problem
        return None, err
    return _render_once(ident, latex, out_dir, dpi, timeout,
                        "", graphics_dir, texinputs)


def _render_once(ident: str, latex: str, out_dir: Path, dpi: int = 400,
                 timeout: int = 90, author_preamble: str = "",
                 graphics_dir: "Path | None" = None,
                 texinputs: "Path | None" = None) -> tuple:
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

    tex.write_text(document(latex, decls, author_preamble, graphics_dir),
                   encoding="utf-8")
    env = dict(os.environ)
    if texinputs is not None:
        # the author's local .sty/.cls live beside their sources; without this a
        # preamble that loads `tufte-book-tai.cls` cannot find it
        env["TEXINPUTS"] = "%s//:%s" % (str(texinputs), env.get("TEXINPUTS", ""))
    try:
        p = subprocess.run(["xelatex", "-interaction=nonstopmode",
                            "-halt-on-error", tex.name],
                           cwd=out_dir, capture_output=True, text=True,
                           timeout=timeout, env=env)
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
