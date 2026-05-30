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
)


def tools_available() -> bool:
    """True if both `latex` and `dvisvgm` are on PATH."""
    return bool(shutil.which("latex")) and bool(shutil.which("dvisvgm"))


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
    if not tools_available():
        return {"ok": False, "svg": "", "ratio": "",
                "error": "latex/dvisvgm not on PATH"}
    pre = preamble or _DEFAULT_PREAMBLE
    # Ensure the standalone class + tikz are present even if a doc preamble was
    # passed without them.
    if "\\documentclass" not in pre:
        pre = _DEFAULT_PREAMBLE
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
                cwd=d, capture_output=True, text=True, timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            return {"ok": False, "svg": "", "ratio": "", "error": "latex timeout"}
        dvi = os.path.join(d, base + ".dvi")
        if not os.path.exists(dvi):
            tail = (r.stdout or "")[-400:]
            return {"ok": False, "svg": "", "ratio": "", "error": f"no DVI: {tail}"}
        try:
            rs = subprocess.run(
                ["dvisvgm", "-n", "--exact-bbox", base + ".dvi", "-o", base + ".svg"],
                cwd=d, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"ok": False, "svg": "", "ratio": "", "error": "dvisvgm timeout"}
        svg_path = os.path.join(d, base + ".svg")
        if not os.path.exists(svg_path):
            return {"ok": False, "svg": "", "ratio": "",
                    "error": f"no SVG: {(rs.stderr or '')[-300:]}"}
        svg = open(svg_path, encoding="utf-8", errors="replace").read()
        return {"ok": True, "svg": svg, "ratio": _graphic_ratio(rs.stderr or ""),
                "error": ""}
