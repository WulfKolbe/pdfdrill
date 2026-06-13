"""
LaTeX → DVI → SVG via the `latex` + `dvisvgm` pipeline.

KaTeX cannot render TikZ pictures or full LaTeX tables, but SVG embeds cleanly
in HTML — so for `Diagram`/`Table` objects (which carry `latex_code`) we
compile each snippet against a `standalone` preamble and convert the DVI to
SVG with dvisvgm. Ported from the LATW `latexCompiler.ts` pipeline
(`latex -interaction=nonstopmode … && dvisvgm -n --exact-bbox …`).

`tools_available()` lets callers degrade gracefully when TeX Live / dvisvgm
aren't installed (e.g. the Claude.ai sandbox has them; some do not).
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile

_DEFAULT_PREAMBLE = (
    "\\documentclass[border=2pt]{standalone}\n"
    "\\usepackage{amsmath,amssymb}\n"
    "\\usepackage{tikz}\n"
    "\\usetikzlibrary{calc,positioning,arrows.meta,shapes,decorations.pathreplacing}\n"
    "\\usepackage{array,booktabs,multirow,multicol}\n"
    "\\usepackage{chemfig}\n"
    "\\usepackage[version=4]{mhchem}\n"
)


def tools_available() -> bool:
    """True if both `latex` and `dvisvgm` are on PATH."""
    return bool(shutil.which("latex")) and bool(shutil.which("dvisvgm"))


_MD_FENCE = re.compile(r"^\s*(```|~~~)")
# A renderable graphic must contain a LaTeX environment, a `\tikz` command, or a
# TikZ drawing command. Raw source-code listings have none (so they're skipped,
# not compiled). The drawing-command set is curated rather than "any backslash"
# so a Julia left-division `A\b` isn't mistaken for a graphic.
_HAS_LATEX_GFX = re.compile(
    # Known graphic/table environments only — NOT any `\begin{...}` (so a math
    # `\begin{matrix}` in a code string isn't mistaken for a renderable graphic).
    r"\\begin\{(?:tikzpicture|tikzcd|circuitikz|forest|tabular\*?|tabularx"
    r"|longtable|pgfpicture|scope|qcircuit|chemfig)\}"
    r"|\\tikz\b"
    # Chemistry commands (vision 'chemical_structure'/'chemical_equation'
    # results arrive as bare \chemfig{...} / \schemestart blocks / \ce{...},
    # not as environments). \ce works in text mode, so the standalone snippet
    # compiles as-is with the mhchem package in the preamble.
    r"|\\(?:chemfig|schemestart|ce)\b"
    r"|\\(draw|node|fill|filldraw|shade|shadedraw|path|clip|coordinate"
    r"|foreach|pic|pgf[A-Za-z]*)\b")


def is_latex_graphic(latex_code: str) -> bool:
    """True if `latex_code` looks like a real LaTeX graphic worth compiling.

    False for empty bodies, markdown-fenced code listings (```/~~~), and any
    snippet with no LaTeX environment / `\\tikz` command (e.g. raw Julia or
    Python source captured as a `Diagram`). Used to hard-guard `compile_to_svg`
    so latex is never spawned on non-graphic content.
    """
    if not latex_code or not latex_code.strip():
        return False
    if _MD_FENCE.match(latex_code):
        return False
    return bool(_HAS_LATEX_GFX.search(latex_code))


_INCLUDEGFX = re.compile(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}")
_VEC_EXT = (".eps", ".ps")
_RASTER_EXT = (".png", ".jpg", ".jpeg", ".pdf", ".gif", ".bmp", ".tif", ".tiff")


def _nonvector_includegraphics(latex_code: str, resource_dir):
    """Return the first \\includegraphics target that the DVI route can't embed
    (a raster/PDF figure, or an extension-less name with no .eps/.ps beside the
    source), or None. EPS/PS targets and resolvable .eps return None."""
    import os
    for m in _INCLUDEGFX.finditer(latex_code or ""):
        name = m.group(1).strip()
        low = name.lower()
        if low.endswith(_VEC_EXT):
            continue
        if low.endswith(_RASTER_EXT):
            return name
        # no extension: DVI latex looks for <name>.eps/.ps — present beside src?
        found = False
        if resource_dir:
            for ext in _VEC_EXT:
                if os.path.exists(os.path.join(resource_dir, name + ext)):
                    found = True
                    break
        if not found:
            return name
    return None


def _graphic_ratio(dvisvgm_out: str) -> str:
    m = re.search(r"graphic size:\s*([0-9.]+)pt\s*x\s*([0-9.]+)pt", dvisvgm_out, re.I)
    if not m:
        return ""
    w, h = float(m.group(1)), float(m.group(2))
    return f"{100 * h / w:.2f}%" if w > 0 else ""


def compile_to_svg(latex_code: str, preamble: str | None = None,
                   timeout: float = 60.0, resource_dir: str | None = None) -> dict:
    """Compile one snippet to SVG. Returns {ok, svg, ratio, error}.

    Writes a temp standalone .tex wrapping `latex_code`, runs latex→DVI then
    dvisvgm→SVG. Never raises — failures come back as {ok: False, error: …}.

    `resource_dir` (the document's own folder) is prepended to TEXINPUTS so a
    project preamble's local `\\usepackage{mystyle}` / tkz-* styles resolve.
    """
    # See _nonvector_includegraphics below (defined at module scope).
    # Hard guard: never feed non-graphic content (empty, a markdown code fence,
    # or raw source with no LaTeX env / \tikz) to latex — it would always fail.
    if not is_latex_graphic(latex_code):
        return {"ok": False, "svg": "", "ratio": "", "skipped": True,
                "error": "not a LaTeX graphic (skipped)"}
    # A TikZ snippet that \includegraphics an external RASTER/PDF figure cannot
    # render on the latex->dvips->dvisvgm (DVI) route, which embeds EPS/PS only.
    # Skip with a clear reason (the bitmap itself is recoverable via
    # `pdfdrill extractimages`/`embedimages`), unless the referenced file
    # resolves to an .eps/.ps next to the source.
    nonvec = _nonvector_includegraphics(latex_code, resource_dir)
    if nonvec:
        return {"ok": False, "svg": "", "ratio": "", "skipped": True,
                "error": f"embeds external bitmap/PDF figure ({nonvec}); the "
                         f"latex->dvisvgm route renders vector graphics only — "
                         f"recover it via `pdfdrill extractimages`"}
    if not tools_available():
        return {"ok": False, "svg": "", "ratio": "",
                "error": "latex/dvisvgm not on PATH"}
    pre = preamble or _DEFAULT_PREAMBLE
    # Ensure the standalone class + tikz are present even if a doc preamble was
    # passed without them.
    if "\\documentclass" not in pre:
        pre = _DEFAULT_PREAMBLE
    # Chemistry code (vision-adopted \chemfig/\schemestart/\ce) may arrive with
    # a DOCUMENT-derived preamble that doesn't load chemfig/mhchem — inject the
    # missing package so the snippet compiles.
    if re.search(r"\\(?:chemfig|schemestart)\b", latex_code) and "chemfig" not in pre:
        pre += "\\usepackage{chemfig}\n"
    if re.search(r"\\ce\b", latex_code) and "mhchem" not in pre:
        pre += "\\usepackage[version=4]{mhchem}\n"
    src = f"{pre}\\begin{{document}}\n{latex_code}\n\\end{{document}}\n"

    # Let latex find the project's local .sty files (style/, the dir itself).
    env = dict(os.environ)
    if resource_dir:
        rd = os.path.abspath(resource_dir)
        extra = os.pathsep.join([rd, os.path.join(rd, "style"),
                                 os.path.join(rd, "styles"), ""])
        env["TEXINPUTS"] = extra + os.pathsep + env.get("TEXINPUTS", "")

    with tempfile.TemporaryDirectory() as d:
        base = "snippet"
        tex = os.path.join(d, base + ".tex")
        with open(tex, "w", encoding="utf-8") as f:
            f.write(src)
        try:
            r = subprocess.run(
                ["latex", "-interaction=nonstopmode", "-halt-on-error", base + ".tex"],
                cwd=d, capture_output=True, encoding="utf-8", errors="replace",
                timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            return {"ok": False, "svg": "", "ratio": "", "error": "latex timeout"}
        dvi = os.path.join(d, base + ".dvi")
        if not os.path.exists(dvi):
            tail = (r.stdout or "")[-400:]
            return {"ok": False, "svg": "", "ratio": "", "error": f"no DVI: {tail}"}
        try:
            rs = subprocess.run(
                ["dvisvgm", "-n", "--exact-bbox", base + ".dvi", "-o", base + ".svg"],
                cwd=d, capture_output=True, encoding="utf-8", errors="replace",
                timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"ok": False, "svg": "", "ratio": "", "error": "dvisvgm timeout"}
        svg_path = os.path.join(d, base + ".svg")
        if not os.path.exists(svg_path):
            return {"ok": False, "svg": "", "ratio": "",
                    "error": f"no SVG: {(rs.stderr or '')[-300:]}"}
        svg = open(svg_path, encoding="utf-8", errors="replace").read()
        return {"ok": True, "svg": svg, "ratio": _graphic_ratio(rs.stderr or ""),
                "error": ""}
