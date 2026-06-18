"""
OpenAI GPT-4o vision client — extract LaTeX/TikZ/gnuplot from an image crop
that OCR (MathPix) left unresolved.

Python port of the proven `~/MX/mathpix_images` flow (llmUtils.js / imagetester.js
+ prompt.txt): send a base64 image to `gpt-4o` with a structured-JSON schema, get
back a `selector` (empty | math | commutative_diagram | gnuplot | tikzpicture |
tensor) plus the corresponding code. Stdlib only (urllib) — no `openai` package.

Credentials: `OPENAI_API_KEY` from the environment / git-ignored `.env`
(see `pdfdrill.env`). The key NEVER enters version control. This is the third
competing provenance alongside MathPix and MathPix-Snip; results attach to the
docmodel as a `provenance="openai"` `latex_candidate` realization.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from typing import Any, Optional

from . import net
from .env import get

API_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-2024-08-06"

# The classification prompt (ported verbatim from mathpix_images/prompt.txt).
DEFAULT_PROMPT = """You are given a base64-encoded image crop that an OCR service could NOT resolve and left as a raw image. Identify what it contains and return a JSON object with this structure:

{
  "selector": "text|handwriting|table|math|chemical_equation|chemical_structure|commutative_diagram|gnuplot|tikzpicture|tensor|diagram|chart|photo|logo|empty",
  "text": "verbatim transcription of printed OR handwritten text",
  "table": "LaTeX tabular for a data table",
  "math": "LaTeX math expression",
  "mhchem": "mhchem \\\\ce{...} expression for a chemical formula/equation",
  "chemfig": "chemfig LaTeX code for a 2D molecular structure or reaction scheme",
  "commutative_diagram": "tikz-cd code",
  "gnuplot": "GnuPlot script reproducing a plot",
  "csv_data": "extracted plot data as CSV",
  "tikzpicture": "tikzpicture LaTeX code",
  "tensor": "tensor diagram LaTeX code",
  "description": "concise factual description for diagram/chart/photo/logo"
}

CLASSIFICATION RULES — fill ONLY the field named by selector.
- "text" - printed prose/labels/numbers/addresses. Transcribe verbatim into "text".
- "handwriting" - cursive or hand-printed writing. Transcribe your best reading into "text".
- "table" - rows/columns of text or numbers. Fill "table" with a \\begin{tabular}...\\end{tabular} reproducing every visible cell, row by row.
- "math" - a math expression. Fill "math" with LaTeX in $$ delimiters.
- "chemical_equation" - a chemical formula, ion, isotope, or reaction equation written as TEXT on one line (e.g. 2H2 + O2 -> 2H2O, SO4^2-, ^{227}_{90}Th, CrO4^2- <=> Cr2O7^2-). Fill "mhchem" with one \\ce{...} expression using mhchem v4 syntax: digits become subscripts automatically, charges as ^2- / ^+, arrows as ->, <-, <=>, states as (s)/(aq)/(g), precipitate v, gas ^, reaction conditions above arrows as ->[\\text{...}].
- "chemical_structure" - a DRAWN 2D molecular structure: skeletal/bond-line formula, ring system, Lewis structure, or a reaction scheme whose participants are drawn structures. Fill "chemfig" with chemfig code: bonds - = ~ and angle bonds like -[:30]; rings as *6(...) (e.g. benzene *6(-=-=-=)); branches in parentheses; charges as \\oplus/\\ominus or ^{+}/^{-} in atom labels; Lewis electron pairs via \\charge/\\Lewis. For a multi-structure reaction scheme wrap the whole thing in \\schemestart ... \\schemestop and connect structures with \\arrow (reagents above the arrow as \\arrow{->[reagent]}). Output only body code (no preamble, no \\documentclass).
- "commutative_diagram" - fill "commutative_diagram" with tikz-cd code.
- "gnuplot" - a data plot: fill "csv_data" with every readable data point (CSV, header row, x in column 1) AND "gnuplot" with a complete self-contained script reading 'data.csv'.
- "tikzpicture" - general TikZ-style line drawing. Fill "tikzpicture".
- "tensor" - tensor network diagram. Fill "tensor".
- "diagram" / "chart" / "photo" / "logo" - a picture with no transcribable text. Fill "description".
- "empty" - ONLY for a genuinely blank/featureless area.

CHEMISTRY DISAMBIGUATION: element symbols with stoichiometric subscripts, charges, or reaction arrows = "chemical_equation" (NOT "math"); any drawing with bond lines, rings, or wedge/dash bonds = "chemical_structure" (NOT "diagram" or "tikzpicture"). A subscripted variable like x_2 with no element symbols stays "math".

IMPORTANT: faint, low-contrast, light-grey, or cursive content is NOT empty. If you can perceive ANY strokes, glyphs, lines, or marks, classify and extract them (use "handwriting" or "text" for writing, "diagram" otherwise). Reserve "empty" for a truly blank crop.

Return ONLY the JSON object. No markdown fences, no explanation."""

# Targeted prompt for images whose caption/title names a graph/subgraph — these
# are vertex+edge drawings that reconstruct cleanly as TikZ (see cmd_vision,
# which selects this prompt when the owning object's caption matches).
GRAPH_TIKZ_PROMPT = """This image is a GRAPH or SUBGRAPH diagram (vertices and edges) that OCR could not resolve. Reconstruct it as a faithful, standalone TikZ picture:
- place every vertex (node) in roughly its observed position;
- draw every edge between the correct vertices;
- preserve colour/emphasis (e.g. a red or highlighted complete-bipartite subgraph) using the matching TikZ colour;
- transcribe any vertex/edge labels you can read.
Return a JSON object: {"selector":"tikzpicture","tikzpicture":"\\\\begin{tikzpicture} ... \\\\end{tikzpicture}"} with ONLY the tikzpicture field filled. No markdown fences, no explanation."""

# Targeted prompt for images whose caption/context names a molecule/compound/
# reaction — drawn structures reconstruct cleanly as chemfig (see cmd_vision,
# which selects this prompt when the owning object's caption matches).
CHEM_STRUCTURE_PROMPT = """This image is a CHEMICAL STRUCTURE or REACTION SCHEME that OCR could not resolve. Reconstruct it as faithful chemfig LaTeX code:
- skeletal/bond-line formulas with chemfig bond syntax (- single, = double, ~ triple, angled bonds -[:30], branches in parentheses);
- ring systems with the *n(...) ring syntax (benzene: *6(-=-=-=), fused rings by chaining);
- preserve every heteroatom, charge (\\oplus / ^{+}), wedge/dash stereo bonds (< / <:), and substituent label exactly as drawn;
- if the image is a reaction scheme with several drawn structures, wrap everything in \\schemestart ... \\schemestop and connect the structures with \\arrow, placing reagents/conditions above the arrow as \\arrow{->[\\chemname{}{reagent}]} or ->[text];
- if instead the content is only a line formula / reaction EQUATION in plain text (no drawn bonds), return selector "chemical_equation" with an mhchem \\ce{...} expression in "mhchem".
Return a JSON object: {"selector":"chemical_structure","chemfig":"\\\\chemfig{...}"} (or the chemical_equation/mhchem pair) with ONLY that field filled. Body code only — no preamble. No markdown fences, no explanation."""

# --------------------------------------------------------------------------- #
# Full-page MathPix-replacement prompt.
#
# tesseract (the keyless OCR fallback) produces a plain-text layer with NO LaTeX,
# so equations never become `{{…||FO}}` transclusions and the whole transclusion
# model collapses. When there is no MathPix key, the only way to recover the math
# is a multimodal model reading the RENDERED page and re-emitting MathPix-quality
# Markdown — inline `\( … \)`, display `$$ … $$` on their own lines — which
# `markdown_source` ingests into real Equation objects. This is the prompt for
# that "rebuild the MathPix .md, or honestly give up" task (see `pdfdrill remath`).
# --------------------------------------------------------------------------- #
GIVE_UP_SENTINEL = "PDFDRILL_CANNOT_RECONSTRUCT"

MATHPIX_MD_PROMPT = (
    "You are standing in for MathPix on ONE rendered page of a document. A keyless "
    "OCR pass produced a plain-text layer with NO LaTeX, which breaks downstream "
    "math transclusion. Read the page IMAGE and re-emit it as MathPix-quality "
    "GitHub Markdown so the LaTeX is recovered. Rules:\n"
    "- EVERY mathematical expression must be LaTeX. Inline math: \\( … \\). "
    "Display/standalone equations: a line containing only `$$`, then the LaTeX, "
    "then a line containing only `$$`. NEVER write math as plain text or unicode "
    "(no 'lambda', '√', '½', '≤' — use \\lambda, \\sqrt{}, \\frac{1}{2}, \\leq).\n"
    "- PRESERVE the 2-D layout as LaTeX — do NOT linearise it. Subscripts/"
    "superscripts become _{} / ^{}, fractions \\frac{}{}, never separate visual "
    "fragments. WRONG (flattened): `M = m a (F + j ) (B65)` then `n` then `0` on "
    "later lines. RIGHT: `M = m_a (F + j_0) \\tag{B65}` as one display equation. "
    "Keep each whole equation on its own; never split one formula across lines.\n"
    "- Keep a printed equation number as a trailing \\tag{N} inside the display "
    "math (or '(N)' at the end of the line).\n"
    "- Headings: #/##/### by level. Lists: '-' or '1.'. Tables: GitHub Markdown "
    "(or a LaTeX tabular inside $$ if the table is heavily mathematical).\n"
    "- Reproduce the page's text and structure FAITHFULLY in reading order. Do "
    "NOT summarise, translate, add, or omit content. Skip running headers/footers, "
    "page numbers, and watermarks.\n"
    "- Output ONLY the Markdown for this one page. No commentary, and do NOT wrap "
    "the whole page in a code fence.\n"
    f"- If you cannot reconstruct it faithfully (illegible, a photo/figure with no "
    f"recoverable text, or you are not confident the math is correct), output "
    f"EXACTLY the single token {GIVE_UP_SENTINEL} and nothing else. Never guess or "
    f"hallucinate mathematics — an invented equation is far worse than giving up."
)

# json_schema enforcing the response shape.
_SCHEMA = {
    "name": "img_repl",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "selector": {"type": "string"},
            "text": {"type": "string"},
            "table": {"type": "string"},
            "math": {"type": "string"},
            "mhchem": {"type": "string"},
            "chemfig": {"type": "string"},
            "commutative_diagram": {"type": "string"},
            "gnuplot": {"type": "string"},
            "csv_data": {"type": "string"},
            "tikzpicture": {"type": "string"},
            "tensor": {"type": "string"},
            "description": {"type": "string"},
        },
        "additionalProperties": False,
    },
}


def available() -> bool:
    return bool(get("OPENAI_API_KEY", ""))


def _api_key() -> str:
    key = get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError(
            "OpenAI credentials missing. Set OPENAI_API_KEY in the environment "
            "or copy .env.example to .env and fill it in "
            "(https://platform.openai.com/api-keys)."
        )
    return key


def _image_bytes(image: str, timeout: float) -> bytes:
    """Load image bytes from a local path or an http(s)/data URL."""
    if image.startswith("data:"):
        return base64.b64decode(image.split(",", 1)[1])
    if image.startswith(("http://", "https://")):
        with net.urlopen(image, timeout=timeout) as resp:
            return resp.read()
    with open(image, "rb") as f:
        return f.read()


def analyze_image(
    image: str,
    *,
    prompt: str = DEFAULT_PROMPT,
    model: str = DEFAULT_MODEL,
    timeout: float = 90.0,
) -> dict[str, Any]:
    """Send one image (path / URL / data URI) to GPT-4o vision; return the
    parsed result dict (selector + math/tikzpicture/gnuplot/csv_data/...)."""
    b64 = base64.b64encode(_image_bytes(image, timeout)).decode("ascii")
    payload = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
        }],
        "response_format": {"type": "json_schema", "json_schema": _SCHEMA},
        "max_tokens": 2000,
        "temperature": 0,
    }
    req = urllib.request.Request(
        API_ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {_api_key()}",
                 "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with net.urlopen(req, timeout=timeout, host="api.openai.com") as resp:
            envelope = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError(f"OpenAI HTTP {e.code}: {body}") from e
    content = envelope["choices"][0]["message"]["content"]
    return json.loads(content)


# Map a vision result to a (kind, latex) pair for the model. `kind` mirrors the
# selector so downstream code can decide rendering (KaTeX vs TikZ→SVG vs table).
_FIELD_BY_SELECTOR = {
    "text": "text",
    "handwriting": "text",
    "table": "table",
    "math": "math",
    "chemical_equation": "mhchem",
    "chemical_structure": "chemfig",
    "commutative_diagram": "commutative_diagram",
    "tikzpicture": "tikzpicture",
    "tensor": "tensor",
    "gnuplot": "gnuplot",
    "diagram": "description",
    "chart": "description",
    "photo": "description",
    "logo": "description",
}


_MD_FENCE_RE = re.compile(r"^\s*(?:```|~~~)[^\n]*\n?|\n?(?:```|~~~)\s*$")


def _strip_fences(code: str) -> str:
    """Drop markdown code fences the model sometimes adds despite instructions."""
    return _MD_FENCE_RE.sub("", code).strip()


def _normalize_mhchem(code: str) -> str:
    """Normalize a chemical_equation result to a bare ``\\ce{...}`` expression.

    The model may return ``$\\ce{...}$``, ``\\ce{...}``, or the raw formula
    (``2H2 + O2 -> 2H2O``). Strip math delimiters; wrap in ``\\ce{}`` when the
    command is missing — mhchem's \\ce works in text and math mode alike, so
    the bare command compiles directly in the standalone SVG snippet AND
    renders in KaTeX (mhchem extension) when wrapped by the report pages.
    """
    code = _strip_fences(code).strip("$").strip()
    if not code:
        return ""
    # The model often writes the heat symbol over a reaction arrow as
    # \textDelta (textgreek package, NOT in the SVG preamble); math-mode
    # \Delta compiles everywhere mhchem does.
    code = re.sub(r"\\text\{\\textDelta\}|\\textDelta\b", r"$\\Delta$", code)
    if "\\ce{" in code or "\\ce {" in code:
        return code
    return "\\ce{" + code + "}"


def _normalize_chemfig(code: str) -> str:
    """Normalize a chemical_structure result to compilable chemfig body code.

    Accepts ``\\chemfig{...}``, a ``\\schemestart``/``chemfig`` reaction-scheme
    block, or a bare bond spec (``H_3C-CH_2-OH``) which gets wrapped in
    ``\\chemfig{}``. Output is body-only LaTeX, ready for the standalone
    latex->dvisvgm route (the preamble loads the chemfig package).
    """
    code = _strip_fences(code).strip("$").strip()
    if not code:
        return ""
    if ("\\chemfig" in code or "\\schemestart" in code
            or "\\begin{chemfig}" in code):
        return code
    return "\\chemfig{" + code + "}"


def result_to_latex(result: dict[str, Any]) -> tuple[str, str]:
    """Return (selector, latex_or_code) from a vision result.

    For math the surrounding ``$$`` are stripped (the model stores bare LaTeX).
    For gnuplot the script is returned (csv_data stays on the raw result).
    chemical_equation is normalized to a bare ``\\ce{...}`` (mhchem) and
    chemical_structure to ``\\chemfig{...}``/``\\schemestart...`` body code, so
    both are directly compilable by the TikZ/table SVG route (svg.py).
    """
    selector = (result.get("selector") or "").strip()
    field = _FIELD_BY_SELECTOR.get(selector)
    code = (result.get(field) or "").strip() if field else ""
    if selector == "math":
        code = code.strip("$").strip()
    elif selector == "chemical_equation":
        code = _normalize_mhchem(code)
    elif selector == "chemical_structure":
        code = _normalize_chemfig(code)
    return selector, code
